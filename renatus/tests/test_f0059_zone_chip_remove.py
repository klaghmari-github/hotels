"""
F0059 — chips Zones: selection + retirer membership + double-clic ouvrir.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0059_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0059" in text


def test_ui_zone_chip_remove_and_dblclick():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="field-zones"' in html
    js = read_all_js()
    assert "removeObjectFromZone" in js
    assert "zone-chip-remove" in js
    assert "dblclick" in js
    assert "is-selected" in js


def test_remove_membership_via_put(tmp_path: Path):
    """Retirer un objet de zone.objects via PUT (logique sous-jacente au chip)."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "z.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "obj1",
                "config": {
                    "type": "table",
                    "label": "Obj",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "zone_a",
                "config": {
                    "type": "zone",
                    "label": "ZA",
                    "objects": {"obj1": {}},
                },
            },
        )
        st = client.get("/gui/step/obj1").json()
        assert any(z["id"] == "zone_a" for z in st["zones"])

        # retire membership
        r = client.put(
            "/gui/step/zone_a",
            json={
                "config": {
                    "type": "zone",
                    "label": "ZA",
                    "objects": {},
                }
            },
        )
        assert r.status_code == 200, r.text
        raw = yaml.safe_load((pipe / "default" / "zone_a.yaml").read_text(encoding="utf-8"))
        assert raw["zone_a"].get("objects") == {} or not raw["zone_a"].get(
            "objects"
        )

        st2 = client.get("/gui/step/obj1").json()
        assert not any(z["id"] == "zone_a" for z in st2["zones"])
        # main/home reste
        assert any(z["id"] == "default" for z in st2["zones"])
