"""F0093 — renatus_time calcule + type iterate (alias iteration)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.pipeline.steps.factory import create_step, normalize_step_type

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0093_registered():
    assert "F0093" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_iteration_alias_to_iterate():
    assert normalize_step_type("iteration") == "iterate"
    step = create_step(
        "i1",
        {
            "type": "iteration",
            "requires": [],
            "target": "t",
            "scenarios": "s",
            "step_view": "v",
        },
    )
    assert step.type == "iterate"


def test_ui_renatus_time_and_iterate():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="field-renatus-time"' in html
    assert 'value="iterate"' in html
    js = read_all_js()
    assert "renderRenatusTime" in js
    assert "renatus_time" in js
    assert 'super("iterate")' in js or 'type: "iterate"' in js


def test_build_sets_renatus_time(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "rt.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "t1",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                },
            },
        )
        st0 = client.get("/gui/step/t1").json()
        assert st0.get("renatus_time") is None

        b = client.post("/gui/build/t1")
        assert b.status_code == 200, b.text
        body = b.json()
        assert "renatus_time" in body
        assert body["renatus_time"] is not None
        assert body["renatus_time"] >= 0

        st = client.get("/gui/step/t1").json()
        assert st.get("renatus_time") is not None
        assert st["renatus_time"] >= 0
        assert "renatus_time" not in (st.get("config") or {})

        # pas dans YAML
        raw = yaml.safe_load(
            (pipe / "default" / "t1.yaml").read_text(encoding="utf-8")
        )
        assert "renatus_time" not in raw["t1"]
        assert "renatus-time" not in raw["t1"]


def test_tools_catalog_has_iterate():
    from renatus.gui.service import GuiService

    types = {t["type"] for t in GuiService.tools_catalog()}
    assert "iterate" in types
    assert "iteration" not in types  # canonique = iterate
