"""
F0056 — zone.objects multi-select par id (membership multi-zones).

- objects = dict {id: meta} (ou liste d ids normalisee)
- meme objet dans plusieurs zones
- graphe onglet zone = membres objects (+ FS)
- GUI: field multi-select + zone-objects
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0056_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0056" in text


def test_normalize_zone_objects():
    from renatus.pipeline.steps.org import normalize_zone_objects

    assert normalize_zone_objects(None) == {}
    assert normalize_zone_objects(["a", "b"]) == {"a": {}, "b": {}}
    assert normalize_zone_objects({"x": None, "y": {"k": 1}}) == {
        "x": {},
        "y": {"k": 1},
    }


def test_zone_step_objects_in_config():
    from renatus.pipeline.steps import create_step

    z = create_step(
        "zone_a",
        {
            "type": "zone",
            "label": "Zone A",
            "objects": ["view_1", "df_1"],
        },
    )
    assert z.objects == {"view_1": {}, "df_1": {}}
    cfg = z.to_config()
    assert cfg["objects"]["view_1"] == {}
    assert "requires" not in cfg or not cfg.get("requires")


def test_same_object_in_two_zones_and_graph(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "z.duckdb"
    client = TestClient(create_gui_app(db, pipe))
    with client:
        # objets
        assert (
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
                        "sql": "SELECT 1 AS n",
                    },
                },
            ).status_code
            == 200
        )
        # deux zones
        for zid, lab in (("zone1", "Zone 1"), ("zone2", "Zone 2")):
            r = client.post(
                "/gui/steps",
                json={
                    "name": zid,
                    "tab": "default",
                    "config": {
                        "type": "zone",
                        "label": lab,
                        "objects": {"view_shared": {}},
                    },
                },
            )
            assert r.status_code == 200, r.text

        # YAML zone contient objects par id
        z1 = yaml.safe_load((pipe / "default" / "zone1.yaml").read_text(encoding="utf-8"))
        assert "view_shared" in z1["zone1"]["objects"]
        z2 = yaml.safe_load((pipe / "default" / "zone2.yaml").read_text(encoding="utf-8"))
        assert "view_shared" in z2["zone2"]["objects"]

        # graphe zone1 voit view_shared
        g1 = client.get("/gui/graph?tab=zone1").json()
        ids1 = {n["id"] for n in g1["nodes"] if not n.get("external")}
        assert "view_shared" in ids1
        assert g1.get("zone_id") == "zone1"

        g2 = client.get("/gui/graph?tab=zone2").json()
        ids2 = {n["id"] for n in g2["nodes"] if not n.get("external")}
        assert "view_shared" in ids2

        # label change via put — id inchange, meme objet
        r = client.put(
            "/gui/step/view_shared",
            json={
                "config": {
                    "type": "view",
                    "label": "label_view10",
                    "name": "v_shared",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                }
            },
        )
        assert r.status_code == 200, r.text
        step = client.get("/gui/step/view_shared").json()
        assert step["id"] == "view_shared"
        assert step["label"] == "label_view10"
        assert step["config"]["label"] == "label_view10"

        # les zones referencent toujours l id
        z1b = yaml.safe_load((pipe / "default" / "zone1.yaml").read_text(encoding="utf-8"))
        assert "view_shared" in z1b["zone1"]["objects"]
        # catalog montre le nouveau label
        gall = client.get("/gui/graph?tab=*").json()
        node = next(n for n in gall["nodes"] if n["id"] == "view_shared")
        assert node["label"] == "label_view10"


def test_ui_zone_objects_field():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="field-zone-objects"' in html
    assert 'data-testid="cfg-zone-objects-picker"' in html
    js = read_all_js()
    assert "renderZoneObjectsPicker" in js
    assert "getSelectedZoneObjects" in js
    assert "zoneObjects" in js or "objects" in js
