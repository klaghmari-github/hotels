"""
Runtime pipeline : connexion DuckDB, prerequis, parallelisation.

La logique metier sim_v2 (scenarios, restitution, LOO) vit dans src.sim_v2.
"""

from .connection import PipelineFactory
from .engine import (
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
from .paths import Paths, release_root

__all__ = [
    "Paths",
    "release_root",
    "PipelineFactory",
    "ParallelismConfig",
    "ConnectionUtils",
    "DependencyTree",
    "ConnectionPipeline",
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
]
