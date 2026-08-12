"""
F0052 — composant Zone (organisationnel).

- type zone accepte par le moteur (no-op)
- palette / tools_catalog
- creation zone = YAML + dossier
- imbrication de zones
- double-clic = ouvrir onglet (API activate)
- fermer onglet sauf main
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
FEATURES = REPO / "gestion_projet" / "features.csv"


def _client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "zone.duckdb"
    return TestClient(create_gui_app(db, pipe)), pipe


def test_feature_f0052_registered():
    text = FEATURES.read_text(encoding="utf-8")
    assert "F0052" in text


def test_tools_catalog_has_zone():
    from renatus.gui.service import GuiService

    types = {t["type"] for t in GuiService.tools_catalog()}
    assert "zone" in types


def test_engine_accepts_zone_noop(tmp_path: Path):
    from renatus.pipeline.engine import ConnectionPipeline

    pipe = tmp_path / "p"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default" / "z1.yaml").write_text(
        "z1:\n  type: zone\n  label: Zone A\n",
        encoding="utf-8",
    )
    db = tmp_path / "t.duckdb"
    cp = ConnectionPipeline(str(db), str(pipe))
    assert "z1" in cp.pipeline
    assert cp.pipeline["z1"]["type"] == "zone"
    assert cp.should_process("z1") is False
    cp.process("z1")  # no-op, pas d exception


def test_create_zone_step_makes_folder_and_yaml(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "zone_sales",
                "tab": "default",
                "config": {"type": "zone", "label": "Sales"},
            },
        )
        assert r.status_code == 200, r.text
        assert (pipe / "default" / "zone_sales.yaml").is_file()
        assert (pipe / "default" / "zone_sales").is_dir()
        body = yaml.safe_load(
            (pipe / "default" / "zone_sales.yaml").read_text(encoding="utf-8")
        )
        assert body["zone_sales"]["type"] == "zone"
        assert body["zone_sales"]["label"] == "Sales"

        g = client.get("/gui/graph?tab=default").json()
        nodes = {n["id"]: n for n in g["nodes"]}
        assert "zone_sales" in nodes
        assert nodes["zone_sales"]["type"] == "zone"
        assert nodes["zone_sales"]["zone_path"] == "default/zone_sales"


def test_nested_zone_and_content(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "zone_a",
                    "tab": "default",
                    "config": {"type": "zone", "label": "A"},
                },
            ).status_code
            == 200
        )
        # ouvrir zone_a (F0144: chemin sous default/)
        act = client.post("/gui/tabs/zone_a/activate")
        assert act.status_code == 200, act.text
        assert act.json()["active_tab"] == "default/zone_a"

        # composant dans la zone
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "t_inside",
                    "tab": "zone_a",
                    "config": {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "sql": "SELECT 1 AS x",
                    },
                },
            ).status_code
            == 200
        )
        assert (pipe / "default" / "zone_a" / "t_inside.yaml").is_file()

        # sous-zone
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "zone_b",
                    "tab": "zone_a",
                    "config": {"type": "zone", "label": "B"},
                },
            ).status_code
            == 200
        )
        assert (pipe / "default" / "zone_a" / "zone_b.yaml").is_file()
        assert (pipe / "default" / "zone_a" / "zone_b").is_dir()

        g_a = client.get("/gui/graph?tab=zone_a").json()
        ids_a = {n["id"] for n in g_a["nodes"]}
        assert ids_a == {"t_inside", "zone_b"}

        # ouvrir sous-zone (path converter accepte le slash)
        act2 = client.post("/gui/tabs/zone_a/zone_b/activate")
        assert act2.status_code == 200, act2.text
        assert act2.json()["active_tab"] == "default/zone_a/zone_b"
        assert (pipe / "default" / "zone_a" / "zone_b").is_dir()


def test_close_tab_not_main(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "zone_x",
                "tab": "default",
                "config": {"type": "zone", "label": "X"},
            },
        )
        client.post("/gui/tabs/zone_x/activate")
        tabs = client.get("/gui/tabs").json()
        ids = [t["id"] for t in tabs["tabs"]]
        assert "default" in ids
        assert "default/zone_x" in ids or "zone_x" in ids
        # default non fermable
        bad = client.post("/gui/tabs/default/close")
        assert bad.status_code >= 400
        # fermer zone_x (API: revient a default; zone reste listable F0125/F0126)
        ok = client.post("/gui/tabs/zone_x/close")
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["active_tab"] == "default"
        ids2 = [t["id"] for t in body["tabs"]]
        assert "default" in ids2
        # F0125: selecteur liste toutes les zones disque (pas seulement open)
        assert "default/zone_x" in ids2 or "zone_x" in ids2
        # open_tabs: zone_x retiree si expose
        open_ids = body.get("open_tabs") or []
        if open_ids:
            assert "zone_x" not in open_ids
            assert "default/zone_x" not in open_ids
        # zone toujours sur disque
        assert (pipe / "default" / "zone_x").is_dir()
        assert (pipe / "default" / "zone_x.yaml").is_file()


def test_create_tab_dialog_creates_zone_step(tmp_path: Path):
    """Bouton + Nouvelle zone cree dossier + step type zone."""
    client, pipe = _client(tmp_path)
    with client:
        r = client.post("/gui/tabs", json={"name": "etl"})
        assert r.status_code == 200, r.text
        assert (pipe / "default" / "etl").is_dir()
        assert (pipe / "default" / "etl.yaml").is_file()
        data = yaml.safe_load((pipe / "default" / "etl.yaml").read_text(encoding="utf-8"))
        assert data["etl"]["type"] == "zone"


def test_build_zone_noop(tmp_path: Path):
    client, _pipe = _client(tmp_path)
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "zone_z",
                "config": {"type": "zone", "label": "Z"},
            },
        )
        r = client.post("/gui/build/zone_z")
        assert r.status_code == 200, r.text
        # F0058: zone build multi-objets (objects vide => zone_build)
        assert r.json()["action"] in {"zone_noop", "zone_build"}


def test_ui_zone_palette_and_close():
    js = read_all_js()
    html = INDEX.read_text(encoding="utf-8")
    assert "type === \"zone\"" in js or 'type === "zone"' in js
    assert "openZoneTab" in js
    # F0126: croix UI retiree; closePipelineTab API peut rester (delete zone)
    assert "closePipelineTab" in js
    assert 'data-testid="flow-zone-close"' not in html
    assert 'value="zone"' in html
    assert "zone:" in js or "zone:" in js  # icon paths
