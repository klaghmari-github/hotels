"""
Point d'entree de compatibilite (API historique).

La logique systeme n'est plus implementee ici : elle vit dans src/.
Ce module reexporte les symboles pour les notebooks / scripts existants.

    from main import ConnectionPipeline, ScenarioGenerator, main
"""

from __future__ import annotations

import sys
from pathlib import Path

# Racine release dans le path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# --- Runtime pipeline ---
from src.pipeline.engine import (  # noqa: E402,F401
    ConnectionPipeline,
    ConnectionUtils,
    DependencyTree,
    ParallelismConfig,
    ParallelIterationManager,
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
    resolve_parallelism,
    run_iteration_bucket,
    scenario_bucket,
    schemas_match,
    seed_backing_table_name,
    source_fingerprint,
    worker_metadata_matches,
    write_worker_metadata,
)
from src.pipeline.paths import Paths, release_root  # noqa: E402,F401

# --- Metier sim_v2 ---
from src.sim_v2.loo import run_leave_one_out  # noqa: E402,F401
from src.sim_v2.modeling import main, run_modeling_simulation  # noqa: E402,F401
from src.sim_v2.restitution import (  # noqa: E402,F401
    normalized_mix_name,
    replace_restitution_input_views,
    run_restitution,
)
from src.sim_v2.scenarios import ScenarioGenerator  # noqa: E402,F401

__all__ = [
    "release_root",
    "Paths",
    "ParallelismConfig",
    "ConnectionUtils",
    "DependencyTree",
    "ConnectionPipeline",
    "ScenarioGenerator",
    "ParallelIterationManager",
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
    "normalized_mix_name",
    "replace_restitution_input_views",
    "run_restitution",
    "run_leave_one_out",
    "run_modeling_simulation",
    "main",
]


if __name__ == "__main__":
    simulation = main()
    print(simulation["stats"])
