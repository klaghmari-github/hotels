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

from src.pipeline.engine import ConnectionPipeline


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


