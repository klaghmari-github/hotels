"""
Chemins stables de la release.

Tout part de la racine release_1_0_0/ pour rester portable.
"""

from __future__ import annotations

from pathlib import Path


class Paths:
    def __init__(self, release_root: str | Path | None = None):
        if release_root is None:
            # src/pipeline/paths.py → release root = parents[2]
            release_root = Path(__file__).resolve().parents[2]
        self.root = Path(release_root).expanduser().resolve()

        self.data = self.root / "data"
        self.files = self.data / "files"
        self.input = self.files / "input"
        self.output = self.files / "output"
        self.output_sim_v1 = self.output / "sim_v1"
        self.output_sim_v2 = self.output / "sim_v2"
        self.output_ml = self.output / "ml"
        self.output_common = self.output / "common"

        self.duckdb = self.data / "duckdb"
        self.duckdb_main = self.duckdb / "main"
        self.duckdb_workers = self.duckdb / "workers"
        self.main_db = self.duckdb_main / "main.duckdb"

        self.pipeline = self.root / "pipeline"
        self.pipeline_common = self.pipeline / "common"
        self.pipeline_sim_v1 = self.pipeline / "sim_v1"
        self.pipeline_sim_v2 = self.pipeline / "sim_v2"
        self.pipeline_ml = self.pipeline / "ml"

        self.models = self.root / "models"
        self.models_catboost = self.models / "catboost"
        self.doc = self.root / "doc"
        self.src = self.root / "src"

    def ensure(self) -> "Paths":
        for path in (
            self.input,
            self.output_sim_v1,
            self.output_sim_v2,
            self.output_ml,
            self.output_common,
            self.duckdb_main,
            self.duckdb_workers,
            self.models_catboost,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def input_file(self, name: str) -> Path:
        return self.input / name

    def out_sim_v1(self, name: str) -> Path:
        return self.output_sim_v1 / name

    def out_sim_v2(self, name: str) -> Path:
        return self.output_sim_v2 / name

    def out_ml(self, name: str) -> Path:
        return self.output_ml / name
