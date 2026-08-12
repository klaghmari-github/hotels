"""F0104 / F0131 / F0139 — pas de tab all; flatzone cree une zone physique."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0104_registered():
    assert "F0104" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_ui_mentions_flatzone_or_allzone():
    js = read_all_js()
    assert "flatzone" in js or "allzone" in js


def test_flatzone_creates_zone_listed_in_selector(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "default" / "t1.yaml").write_text(
        yaml.dump(
            {
                "t1": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        assert client.post("/gui/tabs", json={"name": "z1"}).status_code == 200

        tabs = client.get("/gui/tabs").json()
        ids = [t["id"] for t in tabs["tabs"]]
        assert "default" in ids
        assert "z1" in ids
        assert "all" not in ids
        assert "auto" not in ids

        # F0139: flatzone → zone physique (pas vue logique allzone)
        r = client.post(
            "/gui/auto-zone",
            json={"type": "flatzone", "parent": "default", "name": "flat_default"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "flat_default"
        assert body.get("type") == "zone" or body["config"]["type"] == "zone"

        tabs2 = client.get("/gui/tabs").json()
        ids2 = [t["id"] for t in tabs2["tabs"]]
        assert "all" not in ids2
        # zone listee
        assert any("flat_default" in i for i in ids2)

        g = client.get("/gui/graph?tab=flat_default").json()
        node_ids = {n["id"] for n in g["nodes"] if not n.get("external")}
        assert "t1" in node_ids

        bad = client.post("/gui/tabs", json={"name": "all"})
        assert bad.status_code == 400


def test_cannot_close_all_legacy(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", pipe))
    with client:
        r = client.post("/gui/tabs/all/close")
        assert r.status_code in (200, 400)
