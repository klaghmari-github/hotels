"""
Runtime pipeline : connexion DuckDB, prerequis, parallelisation.

Package renatus.pipeline — API publique du moteur de pipeline.
"""

from .connection import PipelineFactory
from .connection_utils import ConnectionUtils
from .dependency import DependencyTree
from .engine import (
    ConnectionPipeline,
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
# F0053-S7: engine re-exporte aussi ces symboles pour
# `from renatus.pipeline.engine import ...`
from .iteration_parallel import (
    ParallelismConfig,
    ParallelIterationManager,
    resolve_parallelism,
    run_iteration_bucket,
    scenario_bucket,
)
from .steps import (
    REGISTRY,
    Step,
    StepFactory,
    allowed_types,
    create_step,
    tools_catalog,
)
from .paths import Paths, find_project_root, release_root
from .workspace import (
    looks_like_duckdb,
    looks_like_yaml_file,
    normalize_db_and_pipeline,
    prepare_workspace,
)
from .project import RenatusProject, is_project_file
from .project_git import ProjectGit, work_branch_name
from .scope import (
    EXCLUDED_HOTEL_CODES,
    PILOT_HOTEL_CODES,
    is_excluded,
    sql_excluded_hotels_list,
    sql_hotel_not_excluded,
)

__all__ = [
    "Paths",
    "find_project_root",
    "release_root",
    "looks_like_duckdb",
    "looks_like_yaml_file",
    "normalize_db_and_pipeline",
    "prepare_workspace",
    "RenatusProject",
    "is_project_file",
    "ProjectGit",
    "work_branch_name",
    "PipelineFactory",
    "ParallelismConfig",
    "ConnectionUtils",
    "DependencyTree",
    "ConnectionPipeline",
    "ParallelIterationManager",
    "Step",
    "StepFactory",
    "REGISTRY",
    "create_step",
    "allowed_types",
    "tools_catalog",
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
]
