"""
F0039 — requires multi-onglets.

Un composant (table/view/execute/iteration) peut referencer en requires
une step d un autre onglet (ex. source dans main, transformation dans etl).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


def _client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    return TestClient(create_gui_app(tmp_path / "x.duckdb", pipe)), pipe


def test_feature_f0039_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0039" in features


def test_ui_uses_catalog_for_requires():
    js = read_all_js()
    assert "allSteps" in js
    assert "catalog" in js
    # F0095: zones via dropdown (onglets / catalog), plus listes multi-onglets a cocher
    assert "listRequireZones" in js or "requires-zone-select" in js
    assert "openRequiresEditor" in js
    css = CSS.read_text(encoding="utf-8")
    assert "node-external" in css
    assert "requires-edit" in css or "requires-zone" in css


def test_graph_catalog_lists_all_tabs(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "src_main",
                "tab": "default",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS id",
                },
            },
        )
        client.post("/gui/tabs", json={"name": "etl"})
        client.post(
            "/gui/steps",
            json={
                "name": "t_etl",
                "tab": "etl",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 2 AS id",
                },
            },
        )
        g = client.get("/gui/graph?tab=etl").json()
        # noeuds de l onglet etl seulement (+ pas encore d external)
        ids = {n["id"] for n in g["nodes"] if not n.get("external")}
        assert ids == {"t_etl"}
        # catalogue global
        cat_ids = {n["id"] for n in g.get("catalog") or []}
        assert "src_main" in cat_ids
        assert "t_etl" in cat_ids
        tabs = {n["id"]: n.get("tab") for n in g["catalog"]}
        assert tabs["src_main"] == "default"
        assert tabs["t_etl"] in {"etl", "default/etl"}


def test_cross_tab_require_saved_and_ghost_node(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "df_src",
                "tab": "default",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                    "label": "source",
                },
            },
        )
        client.post("/gui/tabs", json={"name": "etl"})
        r = client.post(
            "/gui/steps",
            json={
                "name": "t_use_src",
                "tab": "etl",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["df_src"],
                    "sql": "SELECT n FROM df_src",
                    "label": "use src",
                },
            },
        )
        assert r.status_code == 200, r.text

        # fichier etl contient requires
        yml = (pipe / "default" / "etl" / "t_use_src.yaml").read_text(encoding="utf-8")
        assert "df_src" in yml

        g = client.get("/gui/graph?tab=etl").json()
        nodes = {n["id"]: n for n in g["nodes"]}
        assert "t_use_src" in nodes
        assert nodes["t_use_src"].get("external") is False
        # ghost de df_src
        assert "df_src" in nodes
        assert nodes["df_src"].get("external") is True
        assert nodes["df_src"].get("tab") == "default"
        pairs = {
            (e.get("from") or e.get("from_"), e["to"]) for e in g["edges"]
        }
        assert ("df_src", "t_use_src") in pairs

        # put update requires depuis etl
        r2 = client.put(
            "/gui/step/t_use_src",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["df_src"],
                    "sql": "SELECT n * 2 AS n FROM df_src",
                    "label": "use src",
                }
            },
        )
        assert r2.status_code == 200, r2.text
        step = client.get("/gui/step/t_use_src").json()
        assert "df_src" in (step["config"].get("requires") or [])


def test_build_with_cross_tab_require(tmp_path: Path):
    """Le moteur resout les requires inter-onglets (pipeline global)."""
    client, _ = _client(tmp_path)
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "base_t",
                "tab": "default",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 42 AS v",
                },
            },
        )
        client.post("/gui/tabs", json={"name": "etl"})
        client.post(
            "/gui/steps",
            json={
                "name": "v_from_base",
                "tab": "etl",
                "config": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": ["base_t"],
                    "sql": "SELECT v FROM base_t",
                },
            },
        )
        b = client.post("/gui/build/v_from_base?limit=3")
        assert b.status_code == 200, b.text
        body = b.json()
        assert body.get("ok") is True
