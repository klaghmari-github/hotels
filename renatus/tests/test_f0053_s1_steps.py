"""
F0053-S1 — package pipeline.steps (ABC + factory + types).

- factory cree chaque type
- zone should_process False
- dataframe relation_name
- tools_catalog a zone + dataframe
- ConnectionPipeline delegue process / should_process / relation_name

Note F0055: REGISTRY inclut aussi execute_python (teste en detail dans
test_f0055_execute_python.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from renatus.pipeline.steps import (
    REGISTRY,
    DataframeStep,
    ExecutePythonStep,
    ExecuteShellStep,
    ExecuteStep,
    IterationStep,
    StepFactory,
    TableStep,
    ViewStep,
    ZoneStep,
    allowed_types,
    create_step,
    tools_catalog,
)


def test_registry_has_core_types():
    expected = {
        "dataframe",
        "table",
        "view",
        "execute_sql",
        "execute_python",
        "execute_shell",
        "iterate",
        "zone",
        # F0128
        "allzone",
        "flatzone",
        "backzone",
        "forzone",
        "bidzone",
        # F0136
        "notebook",
    }
    assert set(REGISTRY.keys()) == expected
    assert allowed_types() == expected
    assert StepFactory.allowed_types() == expected


def test_factory_creates_each_type():
    cases = [
        ("df1", {"type": "dataframe", "file": "a.csv"}, DataframeStep),
        (
            "t1",
            {
                "type": "table",
                "sql": "SELECT 1",
                "mode": "create_or_replace",
            },
            TableStep,
        ),
        (
            "v1",
            {"type": "view", "sql": "SELECT 1", "mode": "create_if_not_exists"},
            ViewStep,
        ),
        ("e1", {"type": "execute_sql", "sql": "SELECT 1"}, ExecuteStep),
        (
            "py1",
            {"type": "execute_python", "script": "print(1)"},
            ExecutePythonStep,
        ),
        (
            "sh1",
            {"type": "execute_shell", "script": "echo 1"},
            ExecuteShellStep,
        ),
        (
            "i1",
            {
                "type": "iteration",
                "target": "t1",
                "scenarios": "s",
                "step_view": "sv",
            },
            IterationStep,
        ),
        ("z1", {"type": "zone", "label": "Zone A"}, ZoneStep),
    ]
    for step_id, config, cls in cases:
        step = create_step(step_id, config)
        assert isinstance(step, cls)
        assert step.id == step_id
        # type canonique (iteration → iterate)
        expected_type = (
            "iterate" if config["type"] == "iteration" else config["type"]
        )
        assert step.type == expected_type
        # round-trip config
        out = step.to_config()
        assert out["type"] == expected_type


def test_factory_rejects_unknown_type():
    with pytest.raises(ValueError, match="Type invalide"):
        create_step("x", {"type": "unknown_widget"})


def test_zone_should_process_false():
    step = create_step("z1", {"type": "zone", "label": "A"})
    assert step.should_process(None) is False
    assert step.relation_name() is None
    step.process(None)  # no-op


def test_dataframe_relation_name():
    # name explicite
    s1 = create_step(
        "df_step",
        {"type": "dataframe", "name": "df_sales", "file": "x.csv"},
    )
    assert s1.relation_name() == "df_sales"

    # fallback label
    s2 = create_step(
        "df_step",
        {"type": "dataframe", "label": "MaTable", "file": "x.csv"},
    )
    assert s2.relation_name() == "MaTable"

    # fallback id
    s3 = create_step(
        "df_step",
        {"type": "dataframe", "file": "x.csv"},
    )
    assert s3.relation_name() == "df_step"


def test_execute_iteration_no_relation():
    e = create_step("ex", {"type": "execute_sql", "sql": "SELECT 1"})
    assert e.relation_name() is None
    assert e.should_process(None) is True

    it = create_step(
        "it",
        {
            "type": "iteration",
            "target": "t",
            "scenarios": "s",
            "step_view": "sv",
        },
    )
    assert it.relation_name() is None
    assert it.should_process(None) is True


def test_tools_catalog_has_zone_and_dataframe():
    catalog = tools_catalog()
    types = {t["type"] for t in catalog}
    assert "zone" in types
    assert "dataframe" in types
    # champs GUI attendus
    for entry in catalog:
        assert "id" in entry
        assert "label" in entry
        assert "type" in entry
        assert "description" in entry
        assert "icon" in entry
        assert "fields" in entry

    # GuiService reutilise le meme catalogue
    from renatus.gui.service import GuiService

    gui = GuiService.tools_catalog()
    assert {t["type"] for t in gui} == types
    assert gui == catalog


def test_table_view_stable_frontier():
    t_if = create_step(
        "t",
        {
            "type": "table",
            "sql": "SELECT 1",
            "mode": "create_if_not_exists",
        },
    )
    t_or = create_step(
        "t2",
        {
            "type": "table",
            "sql": "SELECT 1",
            "mode": "create_or_replace",
        },
    )
    assert t_if.is_stable_frontier() is True
    assert t_or.is_stable_frontier() is False
    assert create_step("z", {"type": "zone"}).is_stable_frontier() is False


def test_validate_requires_missing():
    step = create_step(
        "child",
        {
            "type": "table",
            "sql": "SELECT 1",
            "requires": ["missing_dep"],
        },
    )
    with pytest.raises(ValueError, match="Dependance absente"):
        step.validate({"child"})


def test_engine_delegates_zone_and_relation(tmp_path: Path):
    """ConnectionPipeline process/should_process/relation_name via Steps."""
    from renatus.pipeline.engine import ConnectionPipeline

    pipe = tmp_path / "p"
    pipe.mkdir()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "steps.yaml").write_text(
        yaml.dump(
            {
                "z1": {"type": "zone", "label": "Zone A"},
                "df_step": {
                    "type": "dataframe",
                    "name": "df_sales",
                    "file": "input/x.csv",
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    # fichier pour eventuel process dataframe
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "x.csv").write_text("a\n1\n", encoding="utf-8")

    db = tmp_path / "t.duckdb"
    cp = ConnectionPipeline(str(db), str(pipe))
    try:
        assert cp.should_process("z1") is False
        cp.process("z1")  # no-op
        assert cp.relation_name("df_step") == "df_sales"
        assert cp.relation_name("z1") == "z1"
        step = cp.get_step("df_step")
        assert isinstance(step, DataframeStep)
    finally:
        cp.close()


def test_engine_validate_uses_registry(tmp_path: Path):
    from renatus.pipeline.engine import ConnectionPipeline

    pipe = tmp_path / "p"
    pipe.mkdir()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "bad.yaml").write_text(
        "x:\n  type: not_a_type\n",
        encoding="utf-8",
    )
    db = tmp_path / "b.duckdb"
    with pytest.raises(ValueError, match="Type invalide"):
        ConnectionPipeline(str(db), str(pipe))
