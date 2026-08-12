"""
F0041 — dependances inverses calculees (utilise par).

- Non stockees dans le YAML (seul requires est ecrit)
- Calculees: steps dont requires contient l id courant
- UI: liste lecture seule + liens vers les composants
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


def test_feature_f0041_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0041" in features


def test_ui_dependents_readonly():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-testid="field-dependents"' in html
    assert 'data-testid="cfg-dependents"' in html
    assert "Required by" in html

    js = read_all_js()
    assert "renderDependents" in js
    assert "data.dependents" in js
    assert "dependent-chip" in js

    css = CSS.read_text(encoding="utf-8")
    assert "dependent-chip" in css


def test_get_step_returns_dependents_not_in_config(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "src_a",
                "config": {
                    "type": "table",
                    "label": "Source A",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "child_b",
                "config": {
                    "type": "table",
                    "label": "Child B",
                    "mode": "create_or_replace",
                    "requires": ["src_a"],
                    "sql": "SELECT n FROM src_a",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "child_c",
                "config": {
                    "type": "view",
                    "label": "Child C",
                    "mode": "create_or_replace",
                    "requires": ["src_a"],
                    "sql": "SELECT n FROM src_a",
                },
            },
        )

        src = client.get("/gui/step/src_a").json()
        assert "dependents" in src
        dep_ids = {d["id"] for d in src["dependents"]}
        assert dep_ids == {"child_b", "child_c"}
        # hors config YAML
        assert "dependents" not in (src.get("config") or {})
        assert src["dependents_count"] == 2

        # labels presents
        by_id = {d["id"]: d for d in src["dependents"]}
        assert by_id["child_b"]["label"] == "Child B"
        assert by_id["child_c"]["type"] == "view"

        # YAML source sans reverse deps (F0082: sous main/)
        raw = yaml.safe_load(
            (pipe / "default" / "src_a.yaml").read_text(encoding="utf-8")
        )
        assert "dependents" not in raw["src_a"]
        assert "required_by" not in raw["src_a"]

        # put avec dependents injecte → ignore, pas ecrit
        r = client.put(
            "/gui/step/src_a",
            json={
                "config": {
                    "type": "table",
                    "label": "Source A",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                    "dependents": [{"id": "fake"}],
                    "required_by": ["x"],
                }
            },
        )
        assert r.status_code == 200, r.text
        raw2 = yaml.safe_load(
            (pipe / "default" / "src_a.yaml").read_text(encoding="utf-8")
        )
        assert "dependents" not in raw2["src_a"]
        assert "required_by" not in raw2["src_a"]


def test_dependents_empty_when_unused(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "e.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "lonely",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1",
                },
            },
        )
        s = client.get("/gui/step/lonely").json()
        assert s["dependents"] == []
        assert s["dependents_count"] == 0
