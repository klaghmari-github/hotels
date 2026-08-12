"""
Fabrique de ConnectionPipeline pour la release.

Une seule base main.duckdb sert sim_v1, sim_v2 et ml.
Les YAML sont charges depuis pipeline/ (sous-dossiers inclus).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .engine import ConnectionPipeline
from .paths import Paths


class PipelineFactory:
    def __init__(self, paths: Paths | None = None):
        self.paths = (paths or Paths()).ensure()

    def open(
        self,
        *,
        read_only: bool = False,
        rebuild: bool = False,
    ) -> ConnectionPipeline:
        db = self.paths.main_db
        db.parent.mkdir(parents=True, exist_ok=True)

        if rebuild and db.exists() and not read_only:
            for suffix in ("", ".wal"):
                candidate = Path(str(db) + suffix) if suffix else db
                if candidate.exists():
                    candidate.unlink()

        try:
            return ConnectionPipeline(
                db,
                self.paths.pipeline,
                read_only=read_only,
            )
        except Exception as first_error:
            if read_only:
                raise first_error
            # Copie de travail si lock concurrent (UI, serve, autre process).
            # Attention : les écritures partent alors dans main_work.duckdb,
            # pas dans main.duckdb (que l'UI attache par défaut).
            work = self.paths.duckdb_main / "main_work.duckdb"
            if db.exists():
                shutil.copy2(db, work)
            else:
                raise first_error
            import sys

            print(
                f"WARN PipelineFactory: {db.name} verrouillée "
                f"→ fallback {work.name}\n"
                f"  (les créations de tables/vues n'apparaîtront PAS dans "
                f"main.duckdb / DuckDB UI tant que le lock reste actif)\n"
                f"  cause: {first_error}",
                file=sys.stderr,
            )
            return ConnectionPipeline(
                work,
                self.paths.pipeline,
                read_only=False,
            )
