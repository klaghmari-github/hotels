"""
Package renatus.api — API HTTP JSON du moteur de pipeline.

Factory: create_app(db_path, pipelines_dir, read_only=False)
Service: RenatusService / PipelineApiService (alias)
Runtime: RenatusApiRuntime
CLI: renatus-api / python -m renatus.api
"""

from __future__ import annotations

from .app import RenatusApiApp, create_app, create_app_from_paths
from .schemas import (
    ActionResponse,
    HealthResponse,
    PipelineListResponse,
    PipelineStepDetailResponse,
    PipelineStepInfo,
    PipelineStepsResponse,
    RelationDataResponse,
    RelationExistsResponse,
    RelationInfoResponse,
)
from .service import (
    PipelineApiService,
    RelationSerializer,
    RenatusApiRuntime,
    RenatusService,
)

try:
    from .server import main
except ImportError:

    def main(argv=None):  # type: ignore[misc]
        raise SystemExit(
            'uvicorn/fastapi requis: pip install "renatus[api]"'
        )


__all__ = [
    "create_app",
    "create_app_from_paths",
    "RenatusApiApp",
    "RenatusApiRuntime",
    "RenatusService",
    "PipelineApiService",
    "RelationSerializer",
    "main",
    "HealthResponse",
    "PipelineStepInfo",
    "PipelineListResponse",
    "PipelineStepsResponse",
    "PipelineStepDetailResponse",
    "RelationInfoResponse",
    "RelationExistsResponse",
    "RelationDataResponse",
    "ActionResponse",
]
