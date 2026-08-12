"""F0096 — Flux: menu deroulant des zones + graphe filtre."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0096_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0096" in features


def test_html_flow_zone_select():
    html = read_index()
    assert 'data-testid="flow-zone-select"' in html
    assert 'id="flow-zone-select"' in html
    assert 'data-testid="pipeline-tabs"' in html
    assert "flow-zone-bar" in html or "flow-zone-select" in html


def test_js_renders_zone_dropdown_and_switch():
    js = read_all_js()
    assert "flowZoneSelect" in js or "flow-zone-select" in js
    assert "wireFlowZoneSelect" in js
    assert "renderPipelineTabs" in js
    assert "switchTab" in js
    # options portees par le select (zones disponibles)
    assert "flowZoneSelect" in js or 'flow-zone-select' in js


def test_css_flow_zone_bar():
    css = read_css()
    assert "flow-zone-select" in css
    assert "flow-zone-bar" in css


def test_select_zone_filters_graph(tmp_path: Path):
    """API: activer une zone change le graphe affiche (contenu de la zone)."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "z.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "a_main",
                "tab": "default",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                },
            },
        )
        client.post("/gui/tabs", json={"name": "etl"})
        client.post(
            "/gui/steps",
            json={
                "name": "b_etl",
                "tab": "etl",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 2 AS n",
                },
            },
        )
        # graphe main
        client.post("/gui/tabs/default/activate")
        g_main = client.get("/gui/graph?tab=main").json()
        ids_main = {n["id"] for n in g_main["nodes"] if not n.get("external")}
        assert "a_main" in ids_main
        assert "b_etl" not in ids_main

        # graphe etl
        client.post("/gui/tabs/etl/activate")
        g_etl = client.get("/gui/graph?tab=etl").json()
        ids_etl = {n["id"] for n in g_etl["nodes"] if not n.get("external")}
        assert "b_etl" in ids_etl
        assert "a_main" not in ids_etl

        tabs = client.get("/gui/tabs").json()
        tab_ids = {t["id"] for t in tabs["tabs"]}
        assert "default" in tab_ids
        assert "default/etl" in tab_ids
