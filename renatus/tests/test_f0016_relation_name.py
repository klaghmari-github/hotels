"""
F0016 — property name optionnelle pour steps table/view.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _write_pipeline(pipeline_dir: Path, name: str, content: dict) -> Path:
    """F0101: un fichier <id>.yaml par step."""
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    for sid, cfg in content.items():
        path = pipeline_dir / f"{sid}.yaml"
        path.write_text(
            yaml.dump(
                {sid: cfg}, default_flow_style=False, allow_unicode=True
            ),
            encoding="utf-8",
        )
    return pipeline_dir


def _open(db_path: Path, pipeline_dir: Path):
    from renatus.pipeline import ConnectionPipeline

    return ConnectionPipeline(db_path, pipeline_dir, read_only=False)


def test_relation_name_defaults_to_step_id(tmp_path: Path):
    pipe = _write_pipeline(
        tmp_path / "p",
        "one",
        {
            "t_sales": {
                "type": "table",
                "mode": "create_or_replace",
                "sql": "SELECT 1 AS id",
            }
        },
    )
    cp = _open(tmp_path / "a.duckdb", pipe)
    try:
        assert cp.relation_name("t_sales") == "t_sales"
        cp.p_table_view("t_sales")
        assert cp.table_exists("t_sales")
    finally:
        cp.close()


def test_relation_name_explicit_differs_from_step(tmp_path: Path):
    """
    Step YAML id = step_sales, relation en base = t_sales.
    """
    pipe = _write_pipeline(
        tmp_path / "p",
        "named",
        {
            "step_sales": {
                "type": "table",
                "name": "t_sales",
                "mode": "create_or_replace",
                "sql": "SELECT 7 AS amount",
            },
            "v_from_alias": {
                "type": "view",
                "name": "v_amounts",
                "mode": "create_or_replace",
                "requires": ["step_sales"],
                "sql": "SELECT amount * 2 AS amount FROM t_sales",
            },
        },
    )
    cp = _open(tmp_path / "b.duckdb", pipe)
    try:
        assert cp.relation_name("step_sales") == "t_sales"
        assert cp.relation_name("v_from_alias") == "v_amounts"

        rel = cp.p_table_view("v_from_alias")
        rows = rel.fetchall()
        assert rows == [(14,)]

        assert cp.table_exists("t_sales")
        assert not cp.table_exists("step_sales")
        assert cp.view_exists("v_amounts")
        assert not cp.view_exists("v_from_alias")
    finally:
        cp.close()


def test_empty_name_rejected(tmp_path: Path):
    pipe = tmp_path / "p"
    pipe.mkdir()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "bad.yaml").write_text(
        yaml.dump(
            {
                "t_x": {
                    "type": "table",
                    "name": "   ",
                    "mode": "create_or_replace",
                    "sql": "SELECT 1 AS id",
                }
            }
        ),
        encoding="utf-8",
    )
    from renatus.pipeline import ConnectionPipeline

    with pytest.raises(ValueError, match="name invalide"):
        ConnectionPipeline(tmp_path / "c.duckdb", pipe, read_only=False)


def test_gui_graph_exposes_relation_name(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "s.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "step_sales",
                "config": {
                    "type": "table",
                    "name": "t_sales",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS id",
                },
            },
        )
        assert r.status_code == 200, r.text
        g = client.get("/gui/graph").json()
        node = next(n for n in g["nodes"] if n["id"] == "step_sales")
        assert node["relation_name"] == "t_sales"

        step = client.get("/gui/step/step_sales").json()
        assert step["relation_name"] == "t_sales"
        assert step["config"]["name"] == "t_sales"
