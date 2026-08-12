"""
renatus — moteur de pipeline DuckDB.

Reexporte l'API publique de renatus.pipeline.
"""

from __future__ import annotations

# F0046: filtrer warnings pandas/numexpr/bottleneck AVANT tout import moteur
# (sinon renatus-gui affiche du bruit au demarrage)
import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Pandas requires version .* of '(numexpr|bottleneck)'",
    category=UserWarning,
)

from renatus.pipeline import (
    EXCLUDED_HOTEL_CODES,
    PILOT_HOTEL_CODES,
    ConnectionPipeline,
    ConnectionUtils,
    DependencyTree,
    ParallelIterationManager,
    ParallelismConfig,
    Paths,
    PipelineFactory,
    create_empty_table_from_schema,
    drop_relation_if_exists,
    ensure_table_schema,
    ensure_varchar_array_column,
    ensure_varchar_column,
    find_project_root,
    is_excluded,
    normalize_duckdb_type,
    pipeline_fingerprint,
    register_dataframe_as_relation,
    relation_schema,
    relation_type,
    release_root,
    resolve_parallelism,
    run_iteration_bucket,
    scenario_bucket,
    schemas_match,
    seed_backing_table_name,
    source_fingerprint,
    sql_excluded_hotels_list,
    sql_hotel_not_excluded,
    worker_metadata_matches,
    write_worker_metadata,
)

__version__ = "0.1.0"

__all__ = [
    "Paths",
    "find_project_root",
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
    "EXCLUDED_HOTEL_CODES",
    "PILOT_HOTEL_CODES",
    "is_excluded",
    "sql_excluded_hotels_list",
    "sql_hotel_not_excluded",
    "__version__",
]
