"""
Helpers relation / schema DuckDB (F0054-S1).

Extrait de engine.py ; reexportes depuis engine pour stabilite des imports.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


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
    cp: Any,
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

