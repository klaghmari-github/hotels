"""
Moteur pipeline DuckDB : ConnectionPipeline + reexports helpers.

F0053-S7: ConnectionUtils, DependencyTree et ParallelIterationManager
sont dans des modules dedies ; reexportes ici pour stabilite des imports.
F0054-S1: helpers relation/schema dans schema_helpers.py (reexportes).
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from renatus.pipeline.connection_utils import ConnectionUtils
from renatus.pipeline.dependency import DependencyTree


class ConnectionPipeline(ConnectionUtils):
    RESERVED_KEYS = {
        "type",
        "mode",
        "requires",
        "file",
        "sql",
        "script",  # F0055 execute_python
        "venv",  # F0055 execute_python
        "timeout",  # F0055 execute_python
        "session",  # F0136 session python persistante
        "fresh",  # F0136 process one-shot
        "name",
        "label",  # F0031: nom affiche, pas un param fichier
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
        # F0136: noyaux Python persistants (session notebook)
        from .python_kernel import PythonKernelRegistry

        self._python_kernels = PythonKernelRegistry()

    def get_python_kernel(
        self,
        python_exe: str | Path,
        *,
        cwd: str | Path | None = None,
        env: dict | None = None,
    ):
        """
        F0136: noyau Python persistant pour cet interpreteur + cwd.

        Variables / imports conserves entre execute_python tant que la
        ConnectionPipeline (session de travail) reste ouverte.
        """
        work = Path(cwd) if cwd is not None else self.project_dir
        return self._python_kernels.get(python_exe, cwd=work, env=env)

    def close(self) -> None:
        """Ferme DuckDB + noyaux Python de session (F0136)."""
        try:
            reg = getattr(self, "_python_kernels", None)
            if reg is not None:
                reg.shutdown_all()
        except Exception:
            pass
        super().close()

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

        # Pipeline vide autorise (gui / demarrage projet neuf, A0003)
        if not yaml_files:
            if path.is_dir() or not path.exists():
                return {}
            raise FileNotFoundError(
                f"Aucun fichier YAML trouve : {path}"
            )

        # F0060: meme id peut apparaitre dans plusieurs dossiers (copies).
        # RAM = une seule config (premiere vue); les copies doivent etre sync.
        # F0101: id = shortname fichier (stem), jamais chemin parent / extension.
        from renatus.gui.yaml_store import YamlStepStore

        merged: dict[str, dict[str, Any]] = {}
        origins: dict[str, Path] = {}
        # path, step_id, config — reecrire cle dans fichier deja nomme <id>.yaml
        key_heals: list[tuple[Path, str, dict[str, Any]]] = []
        # path_src, step_id, config — renommer fichier mal nomme → <id>.yaml
        rename_heals: list[tuple[Path, str, dict[str, Any]]] = []

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

            keys = list(content.keys())
            # F0101:
            # - monocomposant: id = stem fichier ; si cle != stem, reecrire cle
            #   (fichier doit s appeler <id>.yaml — residus multi-cles extraits
            #   a la save via _remove_step_from_multikey)
            # - multi-cles: chaque cle normalisee (sans path/extension)
            if len(keys) == 1:
                old_key = YamlStepStore.normalize_step_id(str(keys[0]))
                try:
                    stem = YamlStepStore.step_id_from_yaml_path(yaml_file)
                except ValueError:
                    stem = old_key
                config = content[keys[0]]
                # Fichier nomme exactement <stem>.yaml → id = stem (invariant)
                if yaml_file.name in {f"{stem}.yaml", f"{stem}.yml"}:
                    step_id = stem
                    if old_key != step_id:
                        key_heals.append((yaml_file, step_id, config))
                    items = [(step_id, config)]
                else:
                    # nom de fichier non standard: id = cle, renommer si besoin
                    step_id = old_key
                    if yaml_file.name not in {
                        f"{step_id}.yaml",
                        f"{step_id}.yml",
                    }:
                        rename_heals.append((yaml_file, step_id, config))
                    items = [(step_id, config)]
            else:
                items = []
                for name, config in content.items():
                    try:
                        step_id = YamlStepStore.normalize_step_id(
                            str(name)
                        )
                    except ValueError as exc:
                        raise ValueError(
                            f"id invalide dans {yaml_file}: {name!r} ({exc})"
                        ) from exc
                    items.append((step_id, config))

            for step_id, config in items:
                if step_id not in merged:
                    # F0067/F0078: normalise script + type des le load
                    if isinstance(config, dict):
                        from renatus.pipeline.steps.base import (
                            normalize_script_key,
                        )
                        from renatus.pipeline.steps.factory import (
                            normalize_step_type,
                        )

                        config = normalize_script_key(config)
                        if "type" in config:
                            config["type"] = normalize_step_type(
                                config.get("type")
                            )
                    merged[step_id] = config
                    origins[step_id] = yaml_file
                # sinon: copie multi-zone, on ignore le doublon en RAM

        # F0101: reecrire monocomposants <id>.yaml dont la cle YAML etait fausse
        for yaml_file, step_id, cfg in key_heals:
            if not isinstance(cfg, dict):
                continue
            try:
                yaml_file.write_text(
                    yaml.dump(
                        {step_id: cfg},
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                origins[step_id] = yaml_file
            except OSError:
                pass

        # F0101: renommer fichier mal nomme → <id>.yaml (residu multi-cles)
        for src, step_id, cfg in rename_heals:
            if not isinstance(cfg, dict):
                continue
            dest = src.parent / f"{step_id}.yaml"
            if dest.resolve() == src.resolve():
                continue
            try:
                if dest.exists():
                    # deja un monocomposant: jeter le residu
                    src.unlink(missing_ok=True)
                    origins[step_id] = dest
                    continue
                dest.write_text(
                    yaml.dump(
                        {step_id: cfg},
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
                src.unlink(missing_ok=True)
                origins[step_id] = dest
            except OSError:
                pass

        # A0010: requires orphelins (objet supprime) → retire + reecrit YAML
        healed = self.heal_missing_requires(merged)
        if healed:
            self._persist_healed_requires(merged, origins, healed)

        self.validate_pipeline(merged)
        return merged

    @staticmethod
    def heal_missing_requires(
        pipeline: dict[str, dict[str, Any]],
    ) -> list[tuple[str, str]]:
        """
        A0010: retire les requires qui ne referent plus un id existant.

        Retourne la liste (step_id, dep_absente) retires.
        Modifie pipeline en place.
        """
        keys = set(pipeline.keys())
        removed: list[tuple[str, str]] = []
        for name, config in pipeline.items():
            if not isinstance(config, dict):
                continue
            reqs = config.get("requires")
            if not isinstance(reqs, list) or not reqs:
                continue
            kept: list[Any] = []
            for r in reqs:
                rid = str(r)
                if rid in keys:
                    kept.append(r)
                else:
                    removed.append((str(name), rid))
            if len(kept) != len(reqs):
                config["requires"] = kept
        return removed

    @staticmethod
    def _persist_healed_requires(
        pipeline: dict[str, dict[str, Any]],
        origins: dict[str, Path],
        healed: list[tuple[str, str]],
    ) -> None:
        """Reecrit les YAML des steps dont requires a ete heale."""
        import yaml

        dirty = {step_id for step_id, _ in healed}
        for step_id in dirty:
            path = origins.get(step_id)
            cfg = pipeline.get(step_id)
            if path is None or not isinstance(cfg, dict):
                continue
            try:
                # monocomposant <id>.yaml attendu
                if path.name in {f"{step_id}.yaml", f"{step_id}.yml"}:
                    path.write_text(
                        yaml.dump(
                            {step_id: cfg},
                            default_flow_style=False,
                            allow_unicode=True,
                            sort_keys=False,
                        ),
                        encoding="utf-8",
                    )
                else:
                    # multi-cles legacy: maj la cle
                    prev = yaml.safe_load(
                        path.read_text(encoding="utf-8")
                    ) or {}
                    if isinstance(prev, dict) and step_id in prev:
                        prev[step_id] = cfg
                        path.write_text(
                            yaml.dump(
                                prev,
                                default_flow_style=False,
                                allow_unicode=True,
                                sort_keys=False,
                            ),
                            encoding="utf-8",
                        )
            except OSError:
                pass

    @staticmethod
    def validate_pipeline(
        pipeline: dict[str, dict[str, Any]],
    ) -> None:
        # F0053-S1: types autorises = REGISTRY steps
        from renatus.pipeline.steps import create_step

        keys = set(pipeline.keys())
        for name, config in pipeline.items():
            step = create_step(name, config)
            step.validate(keys)

    def df_from_file(
        self,
        file: str | Path,
        **kwargs,
    ) -> pd.DataFrame:
        if file is None or not str(file).strip():
            raise ValueError(
                "Fichier source non renseigne "
                "(config.file vide). Choisissez un fichier "
                "puis enregistrez la step avant Build."
            )

        path = self.resolve_project_path(file)
        if not path.is_file():
            raise FileNotFoundError(
                f"Fichier introuvable : {path} "
                f"(config.file={file!r}, project_dir={self.project_dir})"
            )

        suffix = path.suffix.lower()

        if suffix in {
            ".xlsx",
            ".xls",
            ".xlsm",
        }:
            try:
                return pd.read_excel(path, **kwargs)
            except ImportError as exc:
                raise ImportError(
                    "Lecture Excel (.xlsx) impossible : installez openpyxl "
                    '(pip install "renatus[excel]" ou openpyxl).'
                ) from exc

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
            f"Extension non supportee : {suffix or '(aucune)'} "
            f"pour le fichier {path.name!r}. "
            "Formats: .csv, .tsv, .json, .parquet, .xlsx, .xls, .xlsm"
        )

    def get_step(self, step_name: str):
        """Instancie le Step OOP pour une cle pipeline (F0053-S1)."""
        from renatus.pipeline.steps import create_step

        if step_name not in self.pipeline:
            raise KeyError(
                f"Objet absent du pipeline : {step_name}"
            )
        return create_step(step_name, self.pipeline[step_name])

    def relation_name(self, step_name: str) -> str:
        """
        Nom de la relation en base pour une step pipeline (F0016 / F0048).

        Pour dataframe / table / view :
          config['name'] si renseigne, sinon config['label'], sinon id step.
        Pour execute / execute_python / iteration / zone : id de la step
        (pas de relation).

        - label = nom du composant (UI)
        - name  = entite physique/logique en base (SQL, register)
        """
        step = self.get_step(step_name)
        rel = step.relation_name()
        # Compat API : toujours une str (id si pas de relation)
        return rel if rel is not None else step_name

    def should_process(
        self,
        name: str,
    ) -> bool:
        # F0053-S1: delegue au Step (zone False, execute True, etc.)
        return self.get_step(name).should_process(self)

    def process(
        self,
        name: str,
    ) -> None:
        # F0053-S1: delegue au Step.process(pipeline_obj)
        self.get_step(name).process(self)

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
        from renatus.pipeline.steps.factory import normalize_step_type

        t = normalize_step_type((self.pipeline[name] or {}).get("type"))
        if t in {
            "execute",
            "execute_sql",
            "execute_python",
            "notebook",
            "execute_shell",
            "iterate",
            "iteration",
            "zone",
        }:
            raise TypeError(
                f"{name} n est pas une table ou une vue"
            )

        self.process_with_requires(name)
        # SELECT sur le nom de relation en base (config.name ou id step)
        return self.table_view(self.relation_name(name))

    def p_iteration(
        self,
        name: str,
    ) -> None:
        from renatus.pipeline.steps.factory import normalize_step_type

        step_type = normalize_step_type(
            (self.pipeline[name] or {}).get("type")
        )
        if step_type not in {"iterate", "iteration"}:
            raise TypeError(
                f"{name} n est pas un iterate (type={step_type!r})"
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


# --- F0054-S1 re-exports schema helpers (public API inchange) -------------
from renatus.pipeline.schema_helpers import (  # noqa: E402
    create_empty_table_from_schema,
    drop_relation_if_exists,
    ensure_table_schema,
    ensure_varchar_array_column,
    ensure_varchar_column,
    normalize_duckdb_type,
    pipeline_fingerprint,
    register_dataframe_as_relation,
    relation_schema,
    relation_type,
    schemas_match,
    seed_backing_table_name,
    source_fingerprint,
    worker_metadata_matches,
    write_worker_metadata,
)

# --- F0053-S7 re-exports (public API inchange) -----------------------------
from renatus.pipeline.iteration_parallel import (  # noqa: E402
    ParallelIterationManager,
    ParallelismConfig,
    resolve_parallelism,
    run_iteration_bucket,
    scenario_bucket,
)

__all__ = [
    "ConnectionUtils",
    "DependencyTree",
    "ConnectionPipeline",
    "ParallelIterationManager",
    "ParallelismConfig",
    "resolve_parallelism",
    "scenario_bucket",
    "relation_type",
    "drop_relation_if_exists",
    "ensure_varchar_column",
    "ensure_varchar_array_column",
    "relation_schema",
    "normalize_duckdb_type",
    "schemas_match",
    "create_empty_table_from_schema",
    "ensure_table_schema",
    "seed_backing_table_name",
    "register_dataframe_as_relation",
    "pipeline_fingerprint",
    "source_fingerprint",
    "worker_metadata_matches",
    "write_worker_metadata",
    "run_iteration_bucket",
]
