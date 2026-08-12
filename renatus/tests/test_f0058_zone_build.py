"""
F0058 — Build d une zone = build de tous ses objects.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0058_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0058" in text


def test_zone_build_action():
    from renatus.pipeline.steps import create_step

    z = create_step("z", {"type": "zone", "label": "Z", "objects": {}})
    assert z.build_action() == "zone_build"


def test_zone_build_all_objects(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "t_a",
                "config": {
                    "type": "table",
                    "label": "A",
                    "name": "t_a",  # relation SQL
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "v_b",
                "config": {
                    "type": "view",
                    "label": "B",
                    "name": "v_b",
                    "mode": "create_or_replace",
                    "requires": ["t_a"],
                    "sql": "SELECT n FROM t_a",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "zone_pack",
                "config": {
                    "type": "zone",
                    "label": "Pack",
                    "objects": {"t_a": {}, "v_b": {}},
                    # F0116: root_to_leaves = build tous les membres (compat F0058)
                    "workers": "queue",
                    "renatus_mode": "root_to_leaves",
                },
            },
        )
        r = client.post("/gui/build/zone_pack?limit=5")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["action"] == "zone_build"
        assert body["ok"] is True
        built_ids = [b["id"] for b in body.get("built") or []]
        assert "t_a" in built_ids
        assert "v_b" in built_ids
        # ordre topo: t_a avant v_b
        assert built_ids.index("t_a") < built_ids.index("v_b")
        assert all(b.get("ok") for b in body["built"])



def test_zone_build_empty_objects(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "e.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "zone_empty",
                "config": {"type": "zone", "label": "Empty", "objects": {}},
            },
        )
        r = client.post("/gui/build/zone_empty")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["action"] == "zone_build"
        assert body["built"] == []
        assert "aucun objet" in body["message"].lower() or "0/" in body["message"]


def test_ui_mentions_zone_build():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "zone_build" in js
