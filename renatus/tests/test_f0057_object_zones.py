"""
F0057 — property zones calculee (inverse de zone.objects).

- Non stockee dans le YAML
- main/default toujours present (home)
- membership multi-zones via objects
- chips GUI + click openZoneTab
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0057_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0057" in text


def test_zones_of_home_and_membership(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "t.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "view_shared",
                "tab": "default",
                "config": {
                    "type": "view",
                    "label": "label_view1",
                    "name": "v_shared",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1",
                },
            },
        )
        # home only = main
        st = client.get("/gui/step/view_shared").json()
        assert "zones" in st
        assert "zones" not in (st.get("config") or {})
        zids = [z["id"] for z in st["zones"]]
        assert "default" in zids
        assert st["zones"][0]["kind"] == "home"

        # zone reference l objet
        client.post(
            "/gui/steps",
            json={
                "name": "zone1",
                "tab": "default",
                "config": {
                    "type": "zone",
                    "label": "Zone 1",
                    "objects": {"view_shared": {}},
                },
            },
        )
        st2 = client.get("/gui/step/view_shared").json()
        zids2 = {z["id"]: z for z in st2["zones"]}
        assert "default" in zids2
        assert "zone1" in zids2
        assert zids2["zone1"]["zone_path"] in {"zone1", "default/zone1"}
        assert zids2["zone1"]["kind"] == "member"

        # YAML de l objet ne contient pas zones (F0082: sous flow/default/)
        raw = yaml.safe_load(
            (pipe / "default" / "view_shared.yaml").read_text(encoding="utf-8")
        )
        assert "zones" not in raw["view_shared"]

        # deuxieme zone
        client.post(
            "/gui/steps",
            json={
                "name": "zone2",
                "tab": "default",
                "config": {
                    "type": "zone",
                    "label": "Zone 2",
                    "objects": {"view_shared": {}},
                },
            },
        )
        st3 = client.get("/gui/step/view_shared").json()
        ids3 = {z["id"] for z in st3["zones"]}
        assert ids3 == {"default", "zone1", "zone2"}


def test_put_strips_zones_from_yaml(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "t2.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "t1",
                "config": {
                    "type": "table",
                    "label": "T1",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1",
                    "zones": ["should_not_persist"],
                },
            },
        )
        raw = yaml.safe_load(
            (pipe / "default" / "t1.yaml").read_text(encoding="utf-8")
        )
        assert "zones" not in raw["t1"]


def test_ui_zones_field_and_render():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="field-zones"' in html
    assert 'data-testid="cfg-zones"' in html
    js = read_all_js()
    assert "renderZones" in js
    assert "openZoneTab" in js
    assert "zone-chip" in js
