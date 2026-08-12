"""Schemas de reponse JSON pour Renatus GUI."""

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
class GuiConnectResponse:
    ok: bool = True
    status: str = "up"
    db_path: str = ""
    pipeline_path: str = ""
    pipelines_dir: str = ""
    read_only: bool = False
    step_count: int = 0


@dataclass
class GraphNode:
    id: str
    type: str
    mode: str | None = None
    file_origin: str | None = None


@dataclass
class GraphEdge:
    """from = dependance requise, to = etape dependante."""

    # "from" est un mot reserve Python : stocke en attribut `from_`
    # et serialise sous la cle "from".
    from_: str
    to: str

    def to_dict(self) -> dict[str, str]:
        return {"from": self.from_, "to": self.to}


@dataclass
class GuiGraphResponse:
    ok: bool = True
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)


@dataclass
class GuiStepResponse:
    ok: bool = True
    name: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    file_origin: str | None = None


@dataclass
class GuiSaveResponse:
    ok: bool = True
    name: str = ""
    file_origin: str | None = None
    message: str = ""


@dataclass
class GuiBuildResponse:
    ok: bool = True
    name: str = ""
    action: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    has_result: bool = False
    limit: int | None = None
    message: str = ""
