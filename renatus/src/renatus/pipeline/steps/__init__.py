"""
Package pipeline.steps — hierarchie OOP des types de composants.

Step (ABC)
  RelationStep → DataframeStep, TableStep, ViewStep
  SqlActionStep → ExecuteStep
  PythonActionStep → ExecutePythonStep
  ShellActionStep → ExecuteShellStep
  ControlStep → IterationStep
  OrgStep → ZoneStep
  AutoZoneStep → AllZoneStep, BackZoneStep, ForZoneStep, BidZoneStep (F0128)

Registry + palette : factory.REGISTRY / TOOL_REGIONS (datasets, execute, flow, auto).
"""

from .auto_zone import (
    AUTO_TAB,
    AUTO_ZONE_TYPES,
    AllZoneStep,
    AutoZoneStep,
    BackZoneStep,
    BidZoneStep,
    FlatZoneStep,
    ForZoneStep,
    auto_zone_id_for,
    compute_auto_zone_members,
    is_auto_zone_type,
    normalize_auto_kind,
    recursive_dependents,
    recursive_requires,
    recursive_zone_leaf_ids,
)
from .base import Step, normalize_script_key, script_text
from .control import ControlStep, IterationStep
from .factory import (
    REGISTRY,
    TOOL_REGIONS,
    TYPE_ALIASES,
    StepFactory,
    allowed_types,
    create_step,
    normalize_step_type,
    tools_catalog,
    tools_regions,
)
from .org import OrgStep, ZoneStep
from .python_action import (
    ExecutePythonStep,
    NotebookStep,
    PythonActionStep,
)
from .relation import DataframeStep, RelationStep, TableStep, ViewStep
from .shell_action import ExecuteShellStep, ShellActionStep
from .sql_action import ExecuteStep, SqlActionStep

__all__ = [
    "Step",
    "normalize_script_key",
    "script_text",
    "RelationStep",
    "DataframeStep",
    "TableStep",
    "ViewStep",
    "SqlActionStep",
    "ExecuteStep",
    "PythonActionStep",
    "ExecutePythonStep",
    "NotebookStep",
    "ShellActionStep",
    "ExecuteShellStep",
    "ControlStep",
    "IterationStep",
    "OrgStep",
    "ZoneStep",
    "AutoZoneStep",
    "AllZoneStep",
    "FlatZoneStep",
    "BackZoneStep",
    "ForZoneStep",
    "BidZoneStep",
    "AUTO_TAB",
    "AUTO_ZONE_TYPES",
    "is_auto_zone_type",
    "normalize_auto_kind",
    "auto_zone_id_for",
    "compute_auto_zone_members",
    "recursive_requires",
    "recursive_dependents",
    "recursive_zone_leaf_ids",
    "REGISTRY",
    "TOOL_REGIONS",
    "TYPE_ALIASES",
    "StepFactory",
    "create_step",
    "normalize_step_type",
    "allowed_types",
    "tools_catalog",
    "tools_regions",
]
