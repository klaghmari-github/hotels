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

from src.pipeline.engine import (
    ConnectionPipeline,
    ParallelIterationManager,
)
from src.pipeline.paths import release_root
from src.sim_v2.scenarios import ScenarioGenerator


def main(
    db_con_str: str | Path | None = None,
    pipeline_path: str | Path | None = None,
    scenarios_excel_path: str | Path | None = None,
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

    root = release_root()

    # Chemins release par defaut
    if db_con_str is None:
        db_con_str = (
            root / "data" / "duckdb" / "main" / "main.duckdb"
        )
    if pipeline_path is None:
        # dossier pipeline/ (charge tous les YAML sim_v1/v2/ml)
        pipeline_path = root / "pipeline"
    if scenarios_excel_path is None:
        scenarios_excel_path = (
            root
            / "data"
            / "files"
            / "input"
            / "scenarios.xlsx"
        )

    def _resolve(path: str | Path) -> Path:
        path = Path(path).expanduser()
        if not path.is_absolute():
            path = root / path
        return path.resolve()

    pipeline_path = _resolve(pipeline_path)
    db_con_str = _resolve(db_con_str)
    scenarios_excel_path = _resolve(scenarios_excel_path)
    db_con_str.parent.mkdir(parents=True, exist_ok=True)

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




run_modeling_simulation = main
