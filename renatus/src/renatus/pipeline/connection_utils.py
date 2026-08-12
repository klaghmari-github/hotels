"""
Utilitaires de connexion DuckDB partages (tables, vues, create_relation).
"""

from __future__ import annotations

from pathlib import Path

import duckdb


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
        # Inclut le catalogue temp (dataframes via con.register).
        return bool(
            self.con.execute(
                """
                SELECT COUNT(*) > 0
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = ?
                  AND table_type = 'BASE TABLE'
                  AND (
                    table_catalog = current_database()
                    OR table_catalog = 'temp'
                  )
                """,
                [name],
            ).fetchone()[0]
        )

    def view_exists(self, name: str) -> bool:
        # Inclut le catalogue temp (dataframes via con.register).
        return bool(
            self.con.execute(
                """
                SELECT COUNT(*) > 0
                FROM information_schema.views
                WHERE table_schema = current_schema()
                  AND table_name = ?
                  AND (
                    table_catalog = current_database()
                    OR table_catalog = 'temp'
                  )
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

