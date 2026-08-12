"""
F0054-S1 — backend Step build hooks + GuiService graph split.

- Step.build_action / has_tabular_result / produces_relation par type
- GuiService expose toujours graph/build
- renatus.gui.services.GraphOps importable
- schema_helpers reexporte depuis engine
"""

from __future__ import annotations

import inspect

from renatus.pipeline.steps import (
    DataframeStep,
    ExecuteStep,
    IterationStep,
    TableStep,
    ViewStep,
    ZoneStep,
    create_step,
)
from renatus.gui.service import GuiService
from renatus.gui.services import GraphOps
from renatus.gui.services.graph_ops import GraphOps as GraphOpsDirect


def test_build_action_relation_types():
    cases = [
        ("df", {"type": "dataframe", "file": "a.csv"}, "p_table_view", True, True),
        (
            "t",
            {"type": "table", "sql": "SELECT 1"},
            "p_table_view",
            True,
            True,
        ),
        (
            "v",
            {"type": "view", "sql": "SELECT 1"},
            "p_table_view",
            True,
            True,
        ),
    ]
    for step_id, config, action, tabular, produces in cases:
        step = create_step(step_id, config)
        assert step.build_action() == action
        assert step.has_tabular_result() is tabular
        assert step.produces_relation() is produces
        assert isinstance(step, (DataframeStep, TableStep, ViewStep))


def test_build_action_iteration():
    step = create_step(
        "it",
        {
            "type": "iteration",
            "target": "t",
            "scenarios": "s",
            "step_view": "sv",
        },
    )
    assert isinstance(step, IterationStep)
    assert step.build_action() == "p_iteration"
    assert step.has_tabular_result() is False
    assert step.produces_relation() is False


def test_build_action_zone():
    step = create_step("z1", {"type": "zone", "label": "Zone A"})
    assert isinstance(step, ZoneStep)
    # F0058: zone multi-build (vide => zone_build) ; legacy zone_noop accepte
    assert step.build_action() in {"zone_noop", "zone_build"}
    assert step.has_tabular_result() is False
    assert step.produces_relation() is False


def test_build_action_execute():
    step = create_step("ex", {"type": "execute_sql", "sql": "DELETE FROM t"})
    assert isinstance(step, ExecuteStep)
    assert step.build_action() == "process_with_requires"
    assert step.has_tabular_result() is False
    assert step.produces_relation() is False


def test_gui_service_has_graph_and_build():
    assert hasattr(GuiService, "graph")
    assert hasattr(GuiService, "build")
    assert callable(GuiService.graph)
    assert callable(GuiService.build)
    # signatures stables (tab / name)
    gsig = inspect.signature(GuiService.graph)
    assert "tab" in gsig.parameters
    bsig = inspect.signature(GuiService.build)
    assert "name" in bsig.parameters


def test_gui_services_imports():
    assert GraphOps is GraphOpsDirect
    assert hasattr(GraphOps, "build")
    # GraphOps construit avec un gui (TYPE_CHECKING only)
    assert callable(GraphOps.build)


def test_schema_helpers_reexported_from_engine():
    from renatus.pipeline import schema_helpers
    from renatus.pipeline.engine import (
        ensure_table_schema,
        relation_schema,
    )

    assert relation_schema is schema_helpers.relation_schema
    assert ensure_table_schema is schema_helpers.ensure_table_schema
