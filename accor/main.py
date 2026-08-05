from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd
import yaml


@dataclass(frozen=True)
class ParallelismConfig:
    bucket_count: int
    max_workers: int
    reserved_cpus: int
    duckdb_threads_per_worker: int


class ConnectionUtils:
    def __init__(
        self,
        db_con_str: str | Path,
        read_only: bool = False,
    ):
        self.db_path = Path(db_con_str).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(
            str(self.db_path),
            read_only=read_only,
        )

    def close(self) -> None:
        self.con.close()

    def table_exists(self, name: str) -> bool:
        return bool(
            self.con.execute(
                """
                SELECT COUNT(*) > 0
                FROM information_schema.tables
                WHERE table_catalog = current_database()
                  AND table_schema = current_schema()
                  AND table_name = ?
                  AND table_type = 'BASE TABLE'
                """,
                [name],
            ).fetchone()[0]
        )

    def view_exists(self, name: str) -> bool:
        return bool(
            self.con.execute(
                """
                SELECT COUNT(*) > 0
                FROM information_schema.views
                WHERE table_catalog = current_database()
                  AND table_schema = current_schema()
                  AND table_name = ?
                """,
                [name],
            ).fetchone()[0]
        )

    def relation_exists(self, name: str) -> bool:
        return self.table_exists(name) or self.view_exists(name)

    def table_view(self, name: str):
        return self.con.sql(
            f'SELECT * FROM "{name}"'
        )

    def create_relation(
        self,
        name: str,
        sql: str,
        relation_type: str,
        mode: str,
    ) -> None:
        relation_type = relation_type.upper()
        sql = sql.strip().rstrip(";")

        if relation_type not in {"TABLE", "VIEW"}:
            raise ValueError(
                f"Type non supporte : {relation_type}"
            )

        if mode == "create_if_not_exists":
            self.con.sql(
                f'CREATE {relation_type} IF NOT EXISTS '
                f'"{name}" AS ({sql})'
            )
            return

        if mode == "create_or_replace":
            self.con.sql(
                f'CREATE OR REPLACE {relation_type} '
                f'"{name}" AS ({sql})'
            )
            return

        raise ValueError(
            f"Mode non supporte : {mode}"
        )


class DependencyTree:
    def __init__(
        self,
        pipeline: dict[str, dict[str, Any]],
    ):
        self.pipeline = pipeline

    def stable_frontier(
        self,
        target: str,
    ) -> list[str]:
        frontier: set[str] = set()
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise ValueError(
                    f"Dependance cyclique detectee autour de {name}"
                )

            config = self.pipeline[name]
            object_type = config["type"]
            mode = config.get(
                "mode",
                "create_if_not_exists",
            )

            if (
                object_type in {"table", "view"}
                and mode == "create_if_not_exists"
            ):
                frontier.add(name)
                return

            visiting.add(name)

            for dependency in config.get(
                "requires",
                [],
            ):
                visit(dependency)

            visiting.remove(name)

        visit(target)

        return sorted(frontier)


class ConnectionPipeline(ConnectionUtils):
    RESERVED_KEYS = {
        "type",
        "mode",
        "requires",
        "file",
        "sql",
        "target",
        "scenarios",
        "step_view",
        "order_by",
        "completed_table",
        "completed_key",
        "completed_group_key",
        "expected_count_table",
        "execution",
        "tasks",
        "reserved_cpus",
        "max_workers",
        "duckdb_threads_per_worker",
        "worker_database_pattern",
        "result_table",
    }

    def __init__(
        self,
        db_con_str: str | Path,
        pipeline_path: str | Path,
        read_only: bool = False,
    ):
        super().__init__(
            db_con_str,
            read_only=read_only,
        )
        self.pipeline_path = (
            Path(pipeline_path)
            .expanduser()
            .resolve()
        )
        self.pipeline = self.load_pipeline()
        self.tree = DependencyTree(self.pipeline)

    @property
    def project_dir(self) -> Path:
        if self.pipeline_path.is_file():
            return self.pipeline_path.parent.parent
        return self.pipeline_path.parent

    def resolve_project_path(
        self,
        value: str | Path,
    ) -> Path:
        path = Path(value).expanduser()

        if path.is_absolute():
            return path.resolve()

        return (
            self.project_dir
            / path
        ).resolve()

    def load_pipeline(
        self,
    ) -> dict[str, dict[str, Any]]:
        path = self.pipeline_path

        yaml_files = (
            [path]
            if path.is_file()
            else sorted(
                [
                    *path.rglob("*.yaml"),
                    *path.rglob("*.yml"),
                ]
            )
        )

        if not yaml_files:
            raise FileNotFoundError(
                f"Aucun fichier YAML trouve dans {path}"
            )

        merged: dict[str, dict[str, Any]] = {}
        origins: dict[str, Path] = {}

        for yaml_file in yaml_files:
            content = (
                yaml.safe_load(
                    yaml_file.read_text(
                        encoding="utf-8"
                    )
                )
                or {}
            )

            if not isinstance(content, dict):
                raise ValueError(
                    f"Contenu YAML invalide : {yaml_file}"
                )

            for name, config in content.items():
                if name in merged:
                    raise ValueError(
                        f"Objet {name} defini dans "
                        f"{origins[name]} et {yaml_file}"
                    )

                merged[name] = config
                origins[name] = yaml_file

        self.validate_pipeline(merged)
        return merged

    @staticmethod
    def validate_pipeline(
        pipeline: dict[str, dict[str, Any]],
    ) -> None:
        allowed = {
            "dataframe",
            "table",
            "view",
            "execute",
            "iteration",
        }

        for name, config in pipeline.items():
            object_type = config.get("type")

            if object_type not in allowed:
                raise ValueError(
                    f"Type invalide pour {name}: "
                    f"{object_type}"
                )

            for dependency in config.get(
                "requires",
                [],
            ):
                if dependency not in pipeline:
                    raise ValueError(
                        f"Dependance absente pour "
                        f"{name}: {dependency}"
                    )

    def df_from_file(
        self,
        file: str | Path,
        **kwargs,
    ) -> pd.DataFrame:
        path = self.resolve_project_path(file)
        suffix = path.suffix.lower()

        if suffix in {
            ".xlsx",
            ".xls",
            ".xlsm",
        }:
            return pd.read_excel(
                path,
                **kwargs,
            )

        if suffix == ".csv":
            return pd.read_csv(
                path,
                **kwargs,
            )

        if suffix == ".tsv":
            return pd.read_csv(
                path,
                sep="\t",
                **kwargs,
            )

        if suffix == ".json":
            return pd.read_json(
                path,
                **kwargs,
            )

        if suffix == ".parquet":
            return pd.read_parquet(
                path,
                **kwargs,
            )

        raise ValueError(
            f"Extension non supportee : {suffix}"
        )

    def should_process(
        self,
        name: str,
    ) -> bool:
        config = self.pipeline[name]
        object_type = config["type"]
        mode = config.get(
            "mode",
            "create_if_not_exists",
        )

        if object_type in {
            "execute",
            "iteration",
        }:
            return True

        if object_type == "dataframe":
            return not self.relation_exists(name)

        if mode == "create_or_replace":
            return True

        return not self.relation_exists(name)

    def process(
        self,
        name: str,
    ) -> None:
        config = self.pipeline[name]
        object_type = config["type"]

        if object_type == "dataframe":
            kwargs = {
                key: value
                for key, value in config.items()
                if key not in self.RESERVED_KEYS
            }

            self.con.register(
                name,
                self.df_from_file(
                    config["file"],
                    **kwargs,
                ),
            )
            return

        if object_type in {
            "table",
            "view",
        }:
            self.create_relation(
                name,
                config["sql"],
                object_type,
                config.get(
                    "mode",
                    "create_if_not_exists",
                ),
            )
            return

        if object_type == "execute":
            self.con.sql(
                config["sql"]
                .strip()
                .rstrip(";")
            )
            return

        if object_type == "iteration":
            self.process_iteration(name)
            return

    def process_with_requires(
        self,
        name: str,
        processed: set[str] | None = None,
    ) -> None:

        logging.info(f"process with requires : {name}")
        
        if name not in self.pipeline:
            raise KeyError(
                f"Objet absent du pipeline : {name}"
            )

        if processed is None:
            processed = set()

        if (
            name in processed
            or not self.should_process(name)
        ):
            return

        for dependency in self.pipeline[name].get(
            "requires",
            [],
        ):
            self.process_with_requires(
                dependency,
                processed,
            )

        self.process(name)
        processed.add(name)

    def p_table_view(
        self,
        name: str,
    ):
        if self.pipeline[name]["type"] in {
            "execute",
            "iteration",
        }:
            raise TypeError(
                f"{name} n est pas une table ou une vue"
            )

        self.process_with_requires(name)
        return self.table_view(name)

    def p_iteration(
        self,
        name: str,
    ) -> None:
        if self.pipeline[name]["type"] != "iteration":
            raise TypeError(
                f"{name} n est pas une iteration"
            )

        self.process_with_requires(name)

    @staticmethod
    def sql_literal(value: Any) -> str:
        if value is None:
            return "NULL"

        if hasattr(value, "tolist") and not isinstance(value, str):
            value = value.tolist()

        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"

        if isinstance(value, int):
            return str(value)

        if isinstance(value, float):
            if math.isnan(value):
                return "NULL"
            return repr(value)

        if isinstance(value, (list, tuple, set)):
            values = list(value)
            items = ", ".join(
                ConnectionPipeline.sql_literal(item)
                for item in values
            )
            if not values or all(
                isinstance(item, str)
                for item in values
            ):
                return f"[{items}]::VARCHAR[]"
            return f"[{items}]"

        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    def replace_step_view(
        self,
        step_view: str,
        row: dict[str, Any],
    ) -> None:
        if not row:
            raise ValueError(
                "Une iteration doit fournir au moins une colonne"
            )

        columns = []

        for column_name, value in row.items():
            literal = self.sql_literal(value)
            columns.append(
                f'{literal} AS "{column_name}"'
            )

        select_sql = ",\n                ".join(columns)

        self.con.sql(
            f"""
            CREATE OR REPLACE TEMP VIEW
                "{step_view}"
            AS
            SELECT
                {select_sql}
            """
        )

    def process_iteration(
        self,
        name: str,
    ) -> None:
        config = self.pipeline[name]
        execution = config.get(
            "execution",
            "sequential",
        )

        if execution == "parallel":
            raise RuntimeError(
                "Une iteration parallele doit etre "
                "lancee par ParallelIterationManager"
            )

        self.process_iteration_sequential(
            name,
        )

    def process_iteration_sequential(
        self,
        name: str,
    ) -> None:
        config = self.pipeline[name]
        scenarios_name = config["scenarios"]
        step_view = config["step_view"]
        target = config["target"]
        order_by = config.get(
            "order_by",
            [],
        )

        order_sql = (
            " ORDER BY "
            + ", ".join(order_by)
            if order_by
            else ""
        )

        scenarios = self.con.sql(
            f'SELECT * FROM "{scenarios_name}"'
            f"{order_sql}"
        ).df()

        total = len(scenarios)
        logging.info(
            "Scenarios a simuler dans cette base : %s",
            total,
        )

        started = time.perf_counter()

        for index, row in enumerate(
            scenarios.to_dict(
                orient="records",
            ),
            start=1,
        ):
            scenario_started = time.perf_counter()
            # LOO hotel : hotel_code ; simulation assortiment : scenario_id
            scenario_id = str(
                row.get("scenario_id")
                or row.get("hotel_code")
                or index
            )

            logging.info(
                "Scenario %s/%s | id=%s | debut",
                index,
                total,
                scenario_id[:12],
            )

            self.replace_step_view(
                step_view,
                row,
            )

            self.process_with_requires(
                target,
                processed=set(),
            )

            duration = (
                time.perf_counter()
                - scenario_started
            )
            elapsed = (
                time.perf_counter()
                - started
            )
            remaining = (
                elapsed
                / index
                * (total - index)
                if index
                else 0
            )

            logging.info(
                "Scenario %s/%s | id=%s | "
                "duree=%.1fs | reste_estime=%.1fs",
                index,
                total,
                scenario_id[:12],
                duration,
                remaining,
            )

    def refresh_scenarios(
        self,
        scenarios_df: pd.DataFrame,
    ) -> None:
        name = "__scenarios_refresh"

        try:
            self.con.unregister(name)
        except Exception:
            pass

        self.con.register(
            name,
            scenarios_df,
        )
        self.con.sql(
            "DROP TABLE IF EXISTS t_scenarios"
        )
        self.con.sql(
            f"""
            CREATE TABLE t_scenarios AS
            SELECT
                CAST(scenario_id AS VARCHAR)
                    AS scenario_id,
                FROM_JSON(
                    scenario_removed_natures_json,
                    '["VARCHAR"]'
                ) AS scenario_removed_natures
            FROM {name}
            ORDER BY scenario_id
            """
        )


class ScenarioGenerator:
    GROUPS = {
        "categorie": (
            "t_rank_nature_by_categorie",
            "t_rank_categorie",
            "categorie",
        ),
        "gamme": (
            "t_rank_nature_by_gamme",
            "t_rank_gamme",
            "gamme",
        ),
        "type": (
            "t_rank_nature_by_type",
            "t_rank_type",
            "type",
        ),
        "marque": (
            "t_rank_nature_by_marque",
            "t_rank_marque",
            "marque",
        ),
        "fournisseur": (
            "t_rank_nature_by_fournisseur",
            "t_rank_fournisseur",
            "fournisseur",
        ),
    }

    def __init__(
        self,
        cp: ConnectionPipeline,
        output_excel_path: str | Path = (
            "data/scenarios.xlsx"
        ),
    ):
        self.cp = cp
        self.output_excel_path = (
            Path(output_excel_path)
            .expanduser()
            .resolve()
        )
        self.output_excel_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._scenarios: set[
            tuple[str, ...]
        ] = {()}

    @staticmethod
    def canonical_natures(
        values: Iterable[Any],
    ) -> tuple[str, ...]:
        clean = {
            str(value).strip()
            for value in values
            if value is not None
            and not pd.isna(value)
            and str(value).strip()
        }

        return tuple(
            sorted(
                clean,
                key=lambda value: (
                    value.casefold(),
                    value,
                ),
            )
        )

    @staticmethod
    def scenario_hash(
        values: tuple[str, ...],
    ) -> str:
        payload = json.dumps(
            list(values),
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    def add(
        self,
        values: Iterable[Any],
    ) -> None:
        self._scenarios.add(
            self.canonical_natures(values)
        )

    def add_cumulative(
        self,
        values: list[str],
        include_full_removal: bool,
    ) -> None:
        stop = (
            len(values)
            if include_full_removal
            else max(
                0,
                len(values) - 1,
            )
        )

        for size in range(
            1,
            stop + 1,
        ):
            self.add(
                values[:size]
            )

    def generate_rank_scenarios(
        self,
        include_full_removal: bool = True,
    ) -> None:
        global_df = self.cp.p_table_view(
            "t_rank_nature"
        ).df()

        for _, hotel_df in global_df.groupby(
            "hotel_code",
            sort=True,
        ):
            ordered = (
                hotel_df
                .sort_values(
                    [
                        "rang_nature",
                        "nature",
                    ]
                )["nature"]
                .tolist()
            )

            self.add_cumulative(
                ordered,
                include_full_removal,
            )

        for (
            group_name,
            (
                nature_table,
                group_table,
                group_column,
            ),
        ) in self.GROUPS.items():
            nature_df = self.cp.p_table_view(
                nature_table
            ).df()

            for _, group_df in nature_df.groupby(
                [
                    "hotel_code",
                    group_column,
                ],
                sort=True,
                dropna=False,
            ):
                ordered = (
                    group_df
                    .sort_values(
                        [
                            "rang_nature",
                            "nature",
                        ]
                    )["nature"]
                    .tolist()
                )

                self.add_cumulative(
                    ordered,
                    include_full_removal,
                )

            ranked_groups = self.cp.p_table_view(
                group_table
            ).df()

            for _, hotel_df in ranked_groups.groupby(
                "hotel_code",
                sort=True,
            ):
                cumulative: list[str] = []
                rows = (
                    hotel_df
                    .sort_values(
                        [
                            f"rang_{group_name}",
                            group_column,
                        ]
                    )
                    .to_dict(
                        orient="records",
                    )
                )

                stop = (
                    len(rows)
                    if include_full_removal
                    else max(
                        0,
                        len(rows) - 1,
                    )
                )

                for row in rows[:stop]:
                    cumulative.extend(
                        list(
                            row["natures"]
                        )
                    )
                    self.add(cumulative)

    def dataframe(
        self,
    ) -> pd.DataFrame:
        ordered = sorted(
            self._scenarios,
            key=lambda values: (
                len(values),
                tuple(
                    value.casefold()
                    for value in values
                ),
                values,
            ),
        )

        return pd.DataFrame(
            {
                "scenario_id": [
                    self.scenario_hash(values)
                    for values in ordered
                ],
                "scenario_removed_natures_json": [
                    json.dumps(
                        list(values),
                        ensure_ascii=False,
                    )
                    for values in ordered
                ],
            }
        )

    def write_excel(
        self,
    ) -> pd.DataFrame:
        dataframe = self.dataframe()
        dataframe.to_excel(
            self.output_excel_path,
            index=False,
        )
        return dataframe


def resolve_parallelism(
    tasks: int | str,
    reserved_cpus: int = 2,
    duckdb_threads_per_worker: int = 1,
) -> ParallelismConfig:
    logical_cpus = os.cpu_count() or 1
    worker_capacity = max(
        1,
        logical_cpus - reserved_cpus,
    )

    if isinstance(
        tasks,
        str,
    ):
        if tasks.lower() != "auto":
            raise ValueError(
                "tasks doit etre un entier "
                "strictement positif ou auto"
            )
        bucket_count = worker_capacity
    else:
        bucket_count = int(tasks)

        if bucket_count <= 0:
            raise ValueError(
                "tasks doit etre strictement positif"
            )

    max_workers = min(
        bucket_count,
        worker_capacity,
    )

    return ParallelismConfig(
        bucket_count=bucket_count,
        max_workers=max_workers,
        reserved_cpus=reserved_cpus,
        duckdb_threads_per_worker=(
            duckdb_threads_per_worker
        ),
    )


def scenario_bucket(
    scenario_id: str,
    bucket_count: int,
) -> int:
    return (
        int(
            scenario_id[:16],
            16,
        )
        % bucket_count
    )



def relation_type(
    connection: duckdb.DuckDBPyConnection,
    relation_name: str,
) -> str | None:
    row = connection.execute(
        """
        SELECT relation_type
        FROM (
            SELECT
                table_name AS relation_name,
                'table' AS relation_type
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'

            UNION ALL

            SELECT
                table_name AS relation_name,
                'view' AS relation_type
            FROM information_schema.views
        )
        WHERE relation_name = ?
        LIMIT 1
        """,
        [relation_name],
    ).fetchone()

    if row is None:
        return None

    return str(row[0])


def drop_relation_if_exists(
    connection: duckdb.DuckDBPyConnection,
    relation_name: str,
) -> None:
    current_type = relation_type(
        connection,
        relation_name,
    )

    if current_type == "view":
        connection.sql(
            f'DROP VIEW "{relation_name}"'
        )
    elif current_type == "table":
        connection.sql(
            f'DROP TABLE "{relation_name}"'
        )


def ensure_varchar_column(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    column_name: str,
) -> None:
    current_type = relation_type(
        connection,
        table_name,
    )

    if current_type != "table":
        raise TypeError(
            f"{table_name} doit etre une table pour modifier "
            f"le type de {column_name}"
        )

    row = connection.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = ?
          AND column_name = ?
        LIMIT 1
        """,
        [table_name, column_name],
    ).fetchone()

    if row is None:
        raise KeyError(
            f"Colonne absente : {table_name}.{column_name}"
        )

    data_type = str(row[0]).upper()

    if data_type in {"VARCHAR", "TEXT", "STRING"}:
        return

    connection.sql(
        f'ALTER TABLE "{table_name}" '
        f'ALTER COLUMN "{column_name}" TYPE VARCHAR '
        f'USING CAST("{column_name}" AS VARCHAR)'
    )




def ensure_varchar_array_column(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    column_name: str,
) -> None:
    current_type = relation_type(
        connection,
        table_name,
    )

    if current_type != "table":
        raise TypeError(
            f"{table_name} doit etre une table pour modifier "
            f"le type de {column_name}"
        )

    row = connection.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = ?
          AND column_name = ?
        LIMIT 1
        """,
        [table_name, column_name],
    ).fetchone()

    if row is None:
        raise KeyError(
            f"Colonne absente : {table_name}.{column_name}"
        )

    data_type = str(row[0]).upper()

    if data_type in {"VARCHAR[]", "VARCHAR ARRAY"}:
        return

    if data_type.endswith("[]") or data_type.endswith(" ARRAY"):
        using_sql = (
            f'CASE WHEN "{column_name}" IS NULL '
            f'THEN []::VARCHAR[] '
            f'ELSE CAST("{column_name}" AS VARCHAR[]) END'
        )
    else:
        using_sql = (
            f'CASE WHEN "{column_name}" IS NULL '
            f'THEN []::VARCHAR[] '
            f'ELSE [CAST("{column_name}" AS VARCHAR)]::VARCHAR[] END'
        )

    connection.sql(
        f'ALTER TABLE "{table_name}" '
        f'ALTER COLUMN "{column_name}" TYPE VARCHAR[] '
        f'USING {using_sql}'
    )


def relation_schema(
    connection: duckdb.DuckDBPyConnection,
    relation_name: str,
) -> list[tuple[str, str]]:
    rows = connection.execute(
        """
        SELECT
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = ?
        ORDER BY ordinal_position
        """,
        [relation_name],
    ).fetchall()

    if not rows:
        raise KeyError(
            f"Schema introuvable pour la relation : {relation_name}"
        )

    return [
        (str(column_name), str(data_type))
        for column_name, data_type in rows
    ]


def normalize_duckdb_type(data_type: str) -> str:
    return " ".join(
        str(data_type).upper().replace(" ARRAY", "[]").split()
    )


def schemas_match(
    left: list[tuple[str, str]],
    right: list[tuple[str, str]],
) -> bool:
    if len(left) != len(right):
        return False

    return all(
        left_name == right_name
        and normalize_duckdb_type(left_type)
        == normalize_duckdb_type(right_type)
        for (left_name, left_type), (right_name, right_type)
        in zip(left, right)
    )


def create_empty_table_from_schema(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    schema: list[tuple[str, str]],
    replace: bool = False,
) -> None:
    if replace:
        drop_relation_if_exists(
            connection,
            table_name,
        )

    columns_sql = ",\n                ".join(
        f'"{column_name}" {data_type}'
        for column_name, data_type in schema
    )

    connection.sql(
        f"""CREATE TABLE IF NOT EXISTS "{table_name}" (
                {columns_sql}
            )"""
    )


def ensure_table_schema(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    expected_schema: list[tuple[str, str]],
) -> None:
    current_type = relation_type(
        connection,
        table_name,
    )

    if current_type is None:
        create_empty_table_from_schema(
            connection,
            table_name,
            expected_schema,
        )
        return

    if current_type != "table":
        drop_relation_if_exists(
            connection,
            table_name,
        )
        create_empty_table_from_schema(
            connection,
            table_name,
            expected_schema,
        )
        return

    current_schema = relation_schema(
        connection,
        table_name,
    )

    if schemas_match(
        current_schema,
        expected_schema,
    ):
        return

    row_count = connection.sql(
        f'SELECT COUNT(*) FROM "{table_name}"'
    ).fetchone()[0]

    if int(row_count) != 0:
        raise RuntimeError(
            f"Le schema de {table_name} est incompatible avec "
            "le schema partage et la table contient deja des donnees. "
            "La base worker doit etre reconstruite."
        )

    create_empty_table_from_schema(
        connection,
        table_name,
        expected_schema,
        replace=True,
    )

def seed_backing_table_name(
    relation_name: str,
) -> str:
    digest = hashlib.sha1(
        relation_name.encode("utf-8")
    ).hexdigest()[:12]

    return f"__seed_data_{digest}"


def register_dataframe_as_relation(
    connection: duckdb.DuckDBPyConnection,
    relation_name: str,
    dataframe: pd.DataFrame,
    relation_kind: str,
    replace: bool,
) -> None:
    relation_kind = relation_kind.lower()

    if relation_kind not in {"table", "view"}:
        raise ValueError(
            f"Type de relation non supporte : {relation_kind}"
        )

    registered_name = (
        "__seed_buffer_"
        + hashlib.sha1(
            relation_name.encode("utf-8")
        ).hexdigest()[:12]
    )

    try:
        connection.unregister(
            registered_name
        )
    except Exception:
        pass

    connection.register(
        registered_name,
        dataframe,
    )

    if replace:
        drop_relation_if_exists(
            connection,
            relation_name,
        )

    if relation_kind == "table":
        connection.sql(
            f'CREATE TABLE IF NOT EXISTS '
            f'"{relation_name}" AS '
            f'SELECT * FROM "{registered_name}"'
        )
        return

    backing_table = seed_backing_table_name(
        relation_name
    )

    if replace:
        connection.sql(
            f'DROP TABLE IF EXISTS "{backing_table}"'
        )

    connection.sql(
        f'CREATE TABLE IF NOT EXISTS '
        f'"{backing_table}" AS '
        f'SELECT * FROM "{registered_name}"'
    )

    connection.sql(
        f'CREATE OR REPLACE VIEW '
        f'"{relation_name}" AS '
        f'SELECT * FROM "{backing_table}"'
    )


def pipeline_fingerprint(
    pipeline_path: str | Path,
) -> str:
    path = (
        Path(pipeline_path)
        .expanduser()
        .resolve()
    )
    files = (
        [path]
        if path.is_file()
        else sorted(
            [
                *path.rglob("*.yaml"),
                *path.rglob("*.yml"),
            ]
        )
    )

    digest = hashlib.sha256()

    for file in files:
        digest.update(
            str(
                file.relative_to(
                    path.parent
                    if path.is_file()
                    else path
                )
            ).encode("utf-8")
        )
        digest.update(
            file.read_bytes()
        )

    return digest.hexdigest()


def source_fingerprint(
    cp: ConnectionPipeline,
) -> str:
    row = cp.con.sql(
        """
        SELECT
            COUNT(*) AS row_count,
            COALESCE(
                SUM(QUANTITE),
                0
            ) AS quantity_sum,
            MIN(DATE) AS min_date,
            MAX(DATE) AS max_date,
            COUNT(DISTINCT HOTEL_CODE)
                AS hotel_count,
            COUNT(DISTINCT NATURE_PRODUIT)
                AS nature_count
        FROM t_sales
        """
    ).fetchone()

    payload = json.dumps(
        [
            str(value)
            for value in row
        ],
        separators=(",", ":"),
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def worker_metadata_matches(
    connection: duckdb.DuckDBPyConnection,
    source_hash: str,
    pipeline_hash: str,
    bucket_count: int,
    bucket_id: int,
) -> bool:
    exists = connection.sql(
        """
        SELECT COUNT(*) > 0
        FROM information_schema.tables
        WHERE table_name = 't_worker_metadata'
          AND table_type = 'BASE TABLE'
        """
    ).fetchone()[0]

    if not exists:
        return False

    row = connection.sql(
        """
        SELECT
            source_fingerprint,
            pipeline_fingerprint,
            bucket_count,
            bucket_id
        FROM t_worker_metadata
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return False

    return (
        str(row[0]) == source_hash
        and str(row[1]) == pipeline_hash
        and int(row[2]) == bucket_count
        and int(row[3]) == bucket_id
    )


def write_worker_metadata(
    connection: duckdb.DuckDBPyConnection,
    source_hash: str,
    pipeline_hash: str,
    bucket_count: int,
    bucket_id: int,
) -> None:
    connection.sql(
        """
        DROP TABLE IF EXISTS t_worker_metadata
        """
    )
    connection.execute(
        """
        CREATE TABLE t_worker_metadata AS
        SELECT
            ?::VARCHAR AS source_fingerprint,
            ?::VARCHAR AS pipeline_fingerprint,
            ?::INTEGER AS bucket_count,
            ?::INTEGER AS bucket_id
        """,
        [
            source_hash,
            pipeline_hash,
            bucket_count,
            bucket_id,
        ],
    )


def run_iteration_bucket(
    worker_db_path: str,
    pipeline_path: str,
    iteration_name: str,
    duckdb_threads: int,
    bucket_id: int,
) -> dict[str, Any]:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            f"%(asctime)s | task {bucket_id:03d} | "
            "%(levelname)s | %(message)s"
        ),
        force=True,
    )

    cp = ConnectionPipeline(
        worker_db_path,
        pipeline_path,
    )

    cp.con.execute(
        f"SET threads = {int(duckdb_threads)}"
    )

    scenarios_name = cp.pipeline[
        iteration_name
    ]["scenarios"]

    cp.process_with_requires(
        scenarios_name,
        processed=set(),
    )

    scenarios_before = cp.con.sql(
        f"""
        SELECT COUNT(*)
        FROM "{scenarios_name}"
        """
    ).fetchone()[0]

    started = time.perf_counter()

    cp.process_iteration_sequential(
        iteration_name,
    )

    duration = (
        time.perf_counter()
        - started
    )

    result_count = cp.con.sql(
        """
        SELECT COUNT(*)
        FROM t_dataset_pivot
        """
    ).fetchone()[0]

    cp.close()

    return {
        "bucket_id": bucket_id,
        "scenario_count": scenarios_before,
        "result_count": result_count,
        "duration": duration,
        "worker_db_path": worker_db_path,
    }


class ParallelIterationManager:
    def __init__(
        self,
        shared_cp: ConnectionPipeline,
        iteration_name: str,
    ):
        self.shared_cp = shared_cp
        self.iteration_name = iteration_name
        self.config = shared_cp.pipeline[
            iteration_name
        ]

        parallelism = resolve_parallelism(
            self.config.get(
                "tasks",
                "auto",
            ),
            reserved_cpus=int(
                self.config.get(
                    "reserved_cpus",
                    2,
                )
            ),
            duckdb_threads_per_worker=int(
                self.config.get(
                    "duckdb_threads_per_worker",
                    1,
                )
            ),
        )

        self.parallelism = parallelism
        self.result_table = self.config.get(
            "result_table",
            self.config.get(
                "completed_table",
                "t_dataset_pivot",
            ),
        )
        self.pipeline_hash = pipeline_fingerprint(
            shared_cp.pipeline_path
        )
        self.source_hash = source_fingerprint(
            shared_cp
        )

    def worker_db_path(
        self,
        bucket_id: int,
    ) -> Path:
        pattern = self.config.get(
            "worker_database_pattern",
            "duckdb/workers/"
            "simulation_task_{task_id:03d}.duckdb",
        )

        relative = pattern.format(
            task_id=bucket_id,
        )

        return self.shared_cp.resolve_project_path(
            relative
        )

    def ensure_shared_result_table(
        self,
    ) -> None:
        if self.shared_cp.table_exists(
            self.result_table
        ):
            ensure_varchar_column(
                self.shared_cp.con,
                self.result_table,
                "scenario_id",
            )
            ensure_varchar_array_column(
                self.shared_cp.con,
                self.result_table,
                "scenario_removed_natures",
            )
            return

        step_view = self.config["step_view"]

        baseline = self.shared_cp.con.sql(
            """
            SELECT
                scenario_id,
                scenario_removed_natures
            FROM t_scenarios
            WHERE
                COALESCE(
                    LEN(scenario_removed_natures),
                    0
                ) = 0
            LIMIT 1
            """
        ).df()

        if baseline.empty:
            raise ValueError(
                "Le scenario initial avec une liste "
                "vide est absent de t_scenarios"
            )

        self.shared_cp.replace_step_view(
            step_view,
            baseline.iloc[0].to_dict(),
        )

        self.shared_cp.process_with_requires(
            self.result_table,
            processed=set(),
        )

        ensure_varchar_column(
            self.shared_cp.con,
            self.result_table,
            "scenario_id",
        )
        ensure_varchar_array_column(
            self.shared_cp.con,
            self.result_table,
            "scenario_removed_natures",
        )

    def merge_existing_worker_results(
        self,
    ) -> int:
        merged = 0

        for bucket_id in range(
            self.parallelism.bucket_count
        ):
            worker_path = self.worker_db_path(
                bucket_id
            )

            if not worker_path.exists():
                continue

            worker_connection = duckdb.connect(
                str(worker_path),
                read_only=True,
            )

            if not worker_metadata_matches(
                worker_connection,
                self.source_hash,
                self.pipeline_hash,
                self.parallelism.bucket_count,
                bucket_id,
            ):
                worker_connection.close()
                continue

            table_exists = worker_connection.sql(
                f"""
                SELECT COUNT(*) > 0
                FROM information_schema.tables
                WHERE table_name = '{self.result_table}'
                  AND table_type = 'BASE TABLE'
                """
            ).fetchone()[0]

            if not table_exists:
                worker_connection.close()
                continue

            dataframe = worker_connection.sql(
                f'SELECT * FROM "{self.result_table}"'
            ).df()
            worker_connection.close()

            if dataframe.empty:
                continue

            merged += self.merge_result_dataframe(
                dataframe
            )

        return merged

    def merge_result_dataframe(
        self,
        dataframe: pd.DataFrame,
    ) -> int:
        before = self.shared_cp.con.sql(
            f"""
            SELECT COUNT(*)
            FROM "{self.result_table}"
            """
        ).fetchone()[0]

        register_dataframe_as_relation(
            self.shared_cp.con,
            "__worker_result_buffer",
            dataframe,
            "table",
            replace=True,
        )

        self.shared_cp.con.sql(
            f"""
            INSERT INTO "{self.result_table}" BY NAME
            SELECT source.*
            FROM "__worker_result_buffer"
                AS source
            WHERE NOT EXISTS (
                SELECT 1
                FROM "{self.result_table}"
                    AS target
                WHERE
                    target.scenario_id
                        = source.scenario_id
                    AND target.hotel_code
                        = source.hotel_code
            )
            """
        )

        self.shared_cp.con.sql(
            """
            DROP TABLE IF EXISTS
                "__worker_result_buffer"
            """
        )

        after = self.shared_cp.con.sql(
            f"""
            SELECT COUNT(*)
            FROM "{self.result_table}"
            """
        ).fetchone()[0]

        return int(after - before)

    def stable_seed_frames(
        self,
    ) -> dict[str, dict[str, Any]]:
        target = self.config["target"]
        frontier = self.shared_cp.tree.stable_frontier(
            target
        )

        frames: dict[str, dict[str, Any]] = {}

        for name in frontier:
            if name in {
                "t_scenarios",
                self.result_table,
            }:
                continue

            self.shared_cp.process_with_requires(
                name,
                processed=set(),
            )
            frames[name] = {
                "dataframe": (
                    self.shared_cp
                    .table_view(name)
                    .df()
                ),
                "relation_type": (
                    self.shared_cp.pipeline[name]["type"]
                ),
            }

        return frames

    def pending_scenarios(
        self,
    ) -> pd.DataFrame:
        scenarios_name = self.config["scenarios"]

        self.shared_cp.process_with_requires(
            scenarios_name,
            processed=set(),
        )

        return self.shared_cp.table_view(
            scenarios_name
        ).df()

    def prepare_worker_databases(
        self,
        pending: pd.DataFrame,
        seed_frames: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        workers: list[dict[str, Any]] = []

        if pending.empty:
            return workers

        pending = pending.copy()
        pending["bucket_id"] = (
            pending["scenario_id"]
            .astype(str)
            .map(
                lambda value: scenario_bucket(
                    value,
                    self.parallelism.bucket_count,
                )
            )
        )

        result_schema = relation_schema(
            self.shared_cp.con,
            self.result_table,
        )

        for bucket_id, bucket_df in pending.groupby(
            "bucket_id",
            sort=True,
        ):
            worker_path = self.worker_db_path(
                int(bucket_id)
            )
            worker_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            existing_connection = None

            if worker_path.exists():
                existing_connection = duckdb.connect(
                    str(worker_path)
                )
                metadata_ok = worker_metadata_matches(
                    existing_connection,
                    self.source_hash,
                    self.pipeline_hash,
                    self.parallelism.bucket_count,
                    int(bucket_id),
                )
                existing_connection.close()

                if not metadata_ok:
                    worker_path.unlink()

            worker_connection = duckdb.connect(
                str(worker_path)
            )

            metadata_ok = worker_metadata_matches(
                worker_connection,
                self.source_hash,
                self.pipeline_hash,
                self.parallelism.bucket_count,
                int(bucket_id),
            )

            if not metadata_ok:
                for name, seed in seed_frames.items():
                    register_dataframe_as_relation(
                        worker_connection,
                        name,
                        seed["dataframe"],
                        seed["relation_type"],
                        replace=True,
                    )

                ensure_table_schema(
                    worker_connection,
                    self.result_table,
                    result_schema,
                )

                write_worker_metadata(
                    worker_connection,
                    self.source_hash,
                    self.pipeline_hash,
                    self.parallelism.bucket_count,
                    int(bucket_id),
                )
            else:
                for name, seed in seed_frames.items():
                    current_type = relation_type(
                        worker_connection,
                        name,
                    )

                    expected_type = str(
                        seed["relation_type"]
                    ).lower()

                    if current_type != expected_type:
                        register_dataframe_as_relation(
                            worker_connection,
                            name,
                            seed["dataframe"],
                            expected_type,
                            replace=True,
                        )

            ensure_table_schema(
                worker_connection,
                self.result_table,
                result_schema,
            )

            local_scenarios = bucket_df[
                [
                    "scenario_id",
                    "scenario_removed_natures",
                ]
            ].copy()
            local_scenarios["scenario_id"] = (
                local_scenarios["scenario_id"]
                .astype(str)
            )

            register_dataframe_as_relation(
                worker_connection,
                "t_scenarios",
                local_scenarios,
                "table",
                replace=True,
            )

            worker_connection.close()

            workers.append(
                {
                    "bucket_id": int(bucket_id),
                    "worker_db_path": str(
                        worker_path
                    ),
                }
            )

        return workers

    def execute(
        self,
    ) -> dict[str, Any]:
        self.ensure_shared_result_table()

        merged_before = (
            self.merge_existing_worker_results()
        )

        pending = self.pending_scenarios()

        logging.info(
            "Parallelisation : buckets=%s | "
            "workers=%s | cpu_reserves=%s | "
            "scenarios_restants=%s",
            self.parallelism.bucket_count,
            self.parallelism.max_workers,
            self.parallelism.reserved_cpus,
            len(pending),
        )

        if pending.empty:
            return {
                "bucket_count": (
                    self.parallelism.bucket_count
                ),
                "max_workers": (
                    self.parallelism.max_workers
                ),
                "pending_scenarios": 0,
                "completed_buckets": 0,
                "merged_rows_before": merged_before,
                "merged_rows_after": 0,
            }

        seed_frames = self.stable_seed_frames()
        worker_configs = (
            self.prepare_worker_databases(
                pending,
                seed_frames,
            )
        )

        self.shared_cp.close()

        completed: list[dict[str, Any]] = []
        started = time.perf_counter()

        with ProcessPoolExecutor(
            max_workers=(
                self.parallelism.max_workers
            )
        ) as pool:
            futures = {
                pool.submit(
                    run_iteration_bucket,
                    worker["worker_db_path"],
                    str(
                        self.shared_cp.pipeline_path
                    ),
                    self.iteration_name,
                    self.parallelism
                    .duckdb_threads_per_worker,
                    worker["bucket_id"],
                ): worker
                for worker in worker_configs
            }

            total_buckets = len(futures)

            for index, future in enumerate(
                as_completed(futures),
                start=1,
            ):
                result = future.result()
                completed.append(result)

                elapsed = (
                    time.perf_counter()
                    - started
                )
                remaining = (
                    elapsed
                    / index
                    * (total_buckets - index)
                    if index
                    else 0
                )

                logging.info(
                    "Bucket %s termine | %s/%s | "
                    "scenarios=%s | duree=%.1fs | "
                    "reste_estime=%.1fs",
                    result["bucket_id"],
                    index,
                    total_buckets,
                    result["scenario_count"],
                    result["duration"],
                    remaining,
                )

        self.shared_cp = ConnectionPipeline(
            self.shared_cp.db_path,
            self.shared_cp.pipeline_path,
        )

        merged_after = (
            self.merge_existing_worker_results()
        )

        return {
            "bucket_count": (
                self.parallelism.bucket_count
            ),
            "max_workers": (
                self.parallelism.max_workers
            ),
            "pending_scenarios": len(pending),
            "completed_buckets": len(completed),
            "merged_rows_before": merged_before,
            "merged_rows_after": merged_after,
            "workers": completed,
        }



def normalized_mix_name(
    family: str,
    value: str,
) -> str:
    clean = "".join(
        character.lower()
        if character.isalnum()
        else "_"
        for character in str(value)
    )
    clean = "_".join(
        part
        for part in clean.split("_")
        if part
    )
    return f"{family}_{clean}_part_natures"


def replace_restitution_input_views(
    cp: ConnectionPipeline,
    hotel_nb_chambres: float,
    hotel_to_annuel: float,
    hotel_guests_per_chambre: float,
    metres_lineaires: float,
    type_mix: dict[str, float],
    gamme_mix: dict[str, float],
) -> None:
    if hotel_nb_chambres <= 0:
        raise ValueError(
            "hotel_nb_chambres doit etre strictement positif"
        )
    if not 0 < hotel_to_annuel <= 1:
        raise ValueError(
            "hotel_to_annuel doit etre compris entre 0 et 1"
        )
    if hotel_guests_per_chambre <= 0:
        raise ValueError(
            "hotel_guests_per_chambre doit etre strictement positif"
        )
    if metres_lineaires <= 0:
        raise ValueError(
            "metres_lineaires doit etre strictement positif"
        )

    def validate_mix(
        name: str,
        values: dict[str, float],
    ) -> None:
        if not values:
            raise ValueError(
                f"Le mix {name} ne peut pas etre vide"
            )
        if any(value < 0 for value in values.values()):
            raise ValueError(
                f"Le mix {name} contient une part negative"
            )
        if not math.isclose(
            sum(values.values()),
            1.0,
            rel_tol=1e-6,
            abs_tol=1e-6,
        ):
            raise ValueError(
                f"La somme du mix {name} doit etre egale a 1"
            )

    validate_mix("type", type_mix)
    validate_mix("gamme", gamme_mix)

    cp.con.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW
            v_restitution_input_hotel
        AS
        SELECT
            {float(hotel_nb_chambres)}::DOUBLE
                AS hotel_nb_chambres,
            {float(hotel_to_annuel)}::DOUBLE
                AS hotel_to_annuel,
            {float(hotel_guests_per_chambre)}::DOUBLE
                AS hotel_guests_per_chambre,
            {float(metres_lineaires)}::DOUBLE
                AS metres_lineaires
        """
    )

    rows = []
    for group_value, part in type_mix.items():
        rows.append(
            (
                "type",
                normalized_mix_name("type", group_value),
                float(part),
            )
        )
    for group_value, part in gamme_mix.items():
        rows.append(
            (
                "gamme",
                normalized_mix_name("gamme", group_value),
                float(part),
            )
        )

    input_df = pd.DataFrame(
        rows,
        columns=[
            "variable_family",
            "variable_name",
            "target_part",
        ],
    )
    register_dataframe_as_relation(
        cp.con,
        "__restitution_input_mix_buffer",
        input_df,
        "table",
        replace=True,
    )
    cp.con.sql(
        """
        CREATE OR REPLACE TEMP VIEW
            v_restitution_input_mix
        AS
        SELECT *
        FROM __restitution_input_mix_buffer
        """
    )


def run_restitution(
    cp: ConnectionPipeline,
    hotel_nb_chambres: float = 100,
    hotel_to_annuel: float = 0.5,
    hotel_guests_per_chambre: float = 1.0,
    metres_lineaires: float = 10.0,
    type_mix: dict[str, float] | None = None,
    gamme_mix: dict[str, float] | None = None,
) -> pd.DataFrame:
    default_mix = cp.p_table_view(
        "v_restitution_default_input_mix"
    ).df()

    def family_rows(
        family: str,
        supplied: dict[str, float] | None,
    ) -> list[tuple[str, str, float]]:
        if supplied is None:
            family_default = default_mix[
                default_mix["variable_family"] == family
            ]
            return [
                (
                    family,
                    str(row.variable_name),
                    float(row.target_part),
                )
                for row in family_default.itertuples(index=False)
            ]

        if not supplied:
            raise ValueError(
                f"Le mix {family} ne peut pas etre vide"
            )
        if any(value < 0 for value in supplied.values()):
            raise ValueError(
                f"Le mix {family} contient une part negative"
            )
        if not math.isclose(
            sum(supplied.values()),
            1.0,
            rel_tol=1e-6,
            abs_tol=1e-6,
        ):
            raise ValueError(
                f"La somme du mix {family} doit etre egale a 1"
            )

        return [
            (
                family,
                normalized_mix_name(family, value),
                float(part),
            )
            for value, part in supplied.items()
        ]

    if hotel_nb_chambres <= 0:
        raise ValueError(
            "hotel_nb_chambres doit etre strictement positif"
        )
    if not 0 < hotel_to_annuel <= 1:
        raise ValueError(
            "hotel_to_annuel doit etre compris entre 0 et 1"
        )
    if hotel_guests_per_chambre <= 0:
        raise ValueError(
            "hotel_guests_per_chambre doit etre strictement positif"
        )
    if metres_lineaires <= 0:
        raise ValueError(
            "metres_lineaires doit etre strictement positif"
        )

    cp.con.sql(
        f"""
        CREATE OR REPLACE TEMP VIEW
            v_restitution_input_hotel
        AS
        SELECT
            {float(hotel_nb_chambres)}::DOUBLE
                AS hotel_nb_chambres,
            {float(hotel_to_annuel)}::DOUBLE
                AS hotel_to_annuel,
            {float(hotel_guests_per_chambre)}::DOUBLE
                AS hotel_guests_per_chambre,
            {float(metres_lineaires)}::DOUBLE
                AS metres_lineaires
        """
    )

    rows = [
        *family_rows("type", type_mix),
        *family_rows("gamme", gamme_mix),
    ]
    input_df = pd.DataFrame(
        rows,
        columns=[
            "variable_family",
            "variable_name",
            "target_part",
        ],
    )
    register_dataframe_as_relation(
        cp.con,
        "__restitution_input_mix_buffer",
        input_df,
        "table",
        replace=True,
    )
    cp.con.sql(
        """
        CREATE OR REPLACE TEMP VIEW
            v_restitution_input_mix
        AS
        SELECT *
        FROM __restitution_input_mix_buffer
        """
    )

    cp.process_with_requires(
        "v_restitution_prediction",
        processed=set(),
    )
    return cp.table_view(
        "v_restitution_prediction"
    ).df()


def run_leave_one_out(
    cp: ConnectionPipeline,
    rebuild: bool = True,
) -> dict[str, pd.DataFrame]:
    if rebuild:
        cp.con.sql(
            "DROP TABLE IF EXISTS t_loo_results"
        )

    cp.p_iteration(
        "i_loo_evaluation"
    )

    results = cp.table_view(
        "t_loo_results"
    ).df()
    metrics = cp.p_table_view(
        "v_loo_metrics"
    ).df()
    comparison = cp.p_table_view(
        "v_loo_method_comparison"
    ).df()

    return {
        "results": results,
        "metrics": metrics,
        "method_comparison": comparison,
    }

def main(
    db_con_str: str | Path = (
        "duckdb/pilotes/sim_v2/"
        "sim_v2.duckdb"
    ),
    pipeline_path: str | Path = "config",
    scenarios_excel_path: str | Path = (
        "data/scenarios.xlsx"
    ),
    include_full_removal: bool = True,
) -> dict[str, Any]:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(message)s"
        ),
        force=True,
    )

    module_dir = Path(__file__).resolve().parent

    pipeline_path = Path(
        pipeline_path
    ).expanduser()
    if not pipeline_path.is_absolute():
        pipeline_path = module_dir / pipeline_path
    pipeline_path = pipeline_path.resolve()

    db_con_str = Path(
        db_con_str
    ).expanduser()
    if not db_con_str.is_absolute():
        db_con_str = module_dir / db_con_str
    db_con_str = db_con_str.resolve()

    scenarios_excel_path = Path(
        scenarios_excel_path
    ).expanduser()
    if not scenarios_excel_path.is_absolute():
        scenarios_excel_path = (
            module_dir
            / scenarios_excel_path
        )
    scenarios_excel_path = (
        scenarios_excel_path.resolve()
    )

    logging.info(
        "Base DuckDB partagee : %s",
        db_con_str,
    )
    logging.info(
        "Dossier pipeline : %s",
        pipeline_path,
    )

    cp = ConnectionPipeline(
        db_con_str,
        pipeline_path,
    )

    generator = ScenarioGenerator(
        cp,
        scenarios_excel_path,
    )
    generator.generate_rank_scenarios(
        include_full_removal=(
            include_full_removal
        )
    )

    scenarios = generator.write_excel()
    cp.refresh_scenarios(scenarios)

    iteration_name = "i_iteration_scenario"
    iteration_config = cp.pipeline[
        iteration_name
    ]

    execution = iteration_config.get(
        "execution",
        "sequential",
    )

    if execution == "parallel":
        manager = ParallelIterationManager(
            cp,
            iteration_name,
        )
        iteration_stats = manager.execute()
        cp = manager.shared_cp
    else:
        cp.p_iteration(
            iteration_name
        )
        iteration_stats = {
            "execution": "sequential",
        }

    result = cp.table_view(
        "t_dataset_pivot"
    )

    return {
        "cp": cp,
        "scenario_generator": generator,
        "scenarios": scenarios,
        "result": result,
        "stats": {
            "scenario_count": len(
                scenarios
            ),
            "result_count": (
                result
                .count("*")
                .fetchone()[0]
            ),
            "iteration": iteration_stats,
        },
    }


if __name__ == "__main__":
    simulation = main()
    print(
        simulation["stats"]
    )
