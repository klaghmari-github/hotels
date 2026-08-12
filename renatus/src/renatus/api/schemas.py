"""Schemas de reponse JSON pour l'API renatus (dataclasses)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def as_json_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Objet non serialisable: {type(obj)}")


@dataclass
class HealthResponse:
    """
    Sante du service.

    Champs doubles pour compat des deux contrats de tests :
      status: "up" (RenatusService) ou "ok" (RenatusApiRuntime)
      pipeline_path et pipelines_dir (alias)
    """

    ok: bool = True
    status: str = "up"
    db_path: str = ""
    pipeline_path: str = ""
    pipelines_dir: str = ""
    read_only: bool = False
    step_count: int = 0


@dataclass
class PipelineStepInfo:
    name: str
    type: str
    requires: list[str] = field(default_factory=list)
    mode: str | None = None


@dataclass
class PipelineListResponse:
    """Liste des etapes (list_pipeline / list_steps)."""

    ok: bool = True
    steps: list[PipelineStepInfo] = field(default_factory=list)
    count: int = 0


# Alias de nom pour export / clarte
PipelineStepsResponse = PipelineListResponse


@dataclass
class PipelineStepDetailResponse:
    ok: bool = True
    name: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationInfoResponse:
    """Existence + kind (relation_info / relation_exists)."""

    ok: bool = True
    name: str = ""
    exists: bool = False
    kind: str | None = None


RelationExistsResponse = RelationInfoResponse


@dataclass
class RelationDataResponse:
    ok: bool = True
    name: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    limit: int | None = None
    # F0123: pagination View (datasets)
    offset: int = 0
    total_rows: int | None = None
    page: int | None = None
    page_size: int | None = None
    total_pages: int | None = None


@dataclass
class ActionResponse:
    ok: bool = True
    action: str = ""
    name: str = ""
    message: str = ""
