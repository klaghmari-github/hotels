"""
StepFactory / REGISTRY — type YAML string -> classe Step (F0053-S1).
"""

from __future__ import annotations

from typing import Any, Type

from .base import Step
from .control import IterationStep
from .auto_zone import (
    AllZoneStep,
    AutoZoneStep,
    BackZoneStep,
    BidZoneStep,
    FlatZoneStep,
    ForZoneStep,
)
from .org import ZoneStep
from .python_action import ExecutePythonStep, NotebookStep
from .relation import DataframeStep, TableStep, ViewStep
from .shell_action import ExecuteShellStep
from .sql_action import ExecuteStep

# Mapping type string YAML -> classe
REGISTRY: dict[str, Type[Step]] = {
    DataframeStep.type: DataframeStep,
    TableStep.type: TableStep,
    ViewStep.type: ViewStep,
    ExecuteStep.type: ExecuteStep,
    ExecutePythonStep.type: ExecutePythonStep,
    NotebookStep.type: NotebookStep,
    ExecuteShellStep.type: ExecuteShellStep,
    IterationStep.type: IterationStep,
    ZoneStep.type: ZoneStep,
    # F0128/F0139: templates d init (legacy types encore chargeables)
    FlatZoneStep.type: FlatZoneStep,
    AllZoneStep.type: AllZoneStep,
    BackZoneStep.type: BackZoneStep,
    ForZoneStep.type: ForZoneStep,
    BidZoneStep.type: BidZoneStep,
}

# F0078: alias legacy execute → execute_sql
# F0093: alias legacy iteration → iterate
# F0139: allzone → flatzone (template)
TYPE_ALIASES: dict[str, str] = {
    "execute": "execute_sql",
    "iteration": "iterate",
    "allzone": "flatzone",
    "all": "flatzone",
    "flat": "flatzone",
}


def normalize_step_type(type_name: str | None) -> str:
    """Normalise le type YAML (alias legacy inclus)."""
    raw = str(type_name or "").strip()
    return TYPE_ALIASES.get(raw, raw)


def create_step(step_id: str, config: dict[str, Any]) -> Step:
    """Instancie le Step approprie depuis config['type']."""
    if not isinstance(config, dict):
        raise ValueError(
            f"Config invalide pour {step_id}: dict attendu"
        )
    cfg = dict(config)
    object_type = normalize_step_type(cfg.get("type"))
    if object_type != cfg.get("type"):
        cfg["type"] = object_type
    if object_type not in REGISTRY:
        raise ValueError(
            f"Type invalide pour {step_id}: {object_type or config.get('type')}"
        )
    cls = REGISTRY[str(object_type)]
    return cls.from_config(step_id, cfg)


def allowed_types() -> set[str]:
    """Ensemble des types YAML acceptes par le moteur."""
    return set(REGISTRY.keys())


# F0075: regions palette Outils
TOOL_REGIONS: list[dict[str, Any]] = [
    {
        "id": "datasets",
        "label": "Datasets",
        "types": ("dataframe", "table", "view"),
    },
    {
        "id": "execute",
        "label": "Execute",
        "types": (
            "execute_sql",
            "execute_python",
            "notebook",
            "execute_shell",
        ),
    },
    {
        "id": "flow",
        "label": "Flow",
        "types": ("iterate", "zone"),
    },
    {
        "id": "auto",
        "label": "Auto",
        "types": ("flatzone", "backzone", "forzone", "bidzone"),
    },
]


def tools_catalog() -> list[dict[str, Any]]:
    """
    Catalogue palette GUI — memes champs que GuiService.tools_catalog.

    F0075: ordre par regions Datasets / Execute / Flow.
    """
    order: list[str] = []
    for region in TOOL_REGIONS:
        order.extend(region["types"])
    catalog: list[dict[str, Any]] = []
    for key in order:
        if key not in REGISTRY:
            continue
        meta = dict(REGISTRY[key].tool_meta())
        # region id pour le front
        for region in TOOL_REGIONS:
            if key in region["types"]:
                meta["region"] = region["id"]
                meta["region_label"] = region["label"]
                break
        catalog.append(meta)
    return catalog


def tools_regions() -> list[dict[str, Any]]:
    """Metadonnees des regions palette (F0075)."""
    return [dict(r) for r in TOOL_REGIONS]


class StepFactory:
    """Facade OO autour du REGISTRY (create / allow-list / palette)."""

    registry = REGISTRY

    @staticmethod
    def create(step_id: str, config: dict[str, Any]) -> Step:
        return create_step(step_id, config)

    @staticmethod
    def allowed_types() -> set[str]:
        return allowed_types()

    @staticmethod
    def tools_catalog() -> list[dict[str, Any]]:
        return tools_catalog()
