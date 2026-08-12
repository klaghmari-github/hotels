"""
F0027 — onglets multi-pipeline dans le graphe GUI.

Chaque sous-dossier de pipelines/ est un onglet (pack).
L onglet main = YAML a la racine. Graphe filtre par onglet.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js


def _client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "tabs.duckdb"
    return TestClient(create_gui_app(db, pipe)), pipe


def _edge_pairs(edges):
    return {
        (e.get("from") or e.get("from_"), e["to"]) for e in edges
    }


def test_feature_f0027_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0027" in features


def test_default_tab_main_and_create_tab(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        r = client.get("/gui/tabs")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["active_tab"] == "default"
        ids = [t["id"] for t in data["tabs"]]
        assert "default" in ids

        r2 = client.post("/gui/tabs", json={"name": "etl"})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["id"] == "default/etl"
        assert body["active_tab"] == "default/etl"
        assert (pipe / "default" / "etl").is_dir()
        ids2 = [t["id"] for t in body["tabs"]]
        assert "default/etl" in ids2
        assert "default" in ids2


def test_steps_isolated_per_tab_graph(tmp_path: Path):
    """
    df_a dans main, df_b dans etl : chaque graphe ne voit que son onglet.
    """
    client, pipe = _client(tmp_path)
    with client:
        assert client.post(
            "/gui/steps",
            json={
                "name": "df_main",
                "config": {"type": "dataframe", "file": "input/a.csv"},
                "tab": "default",
            },
        ).status_code == 200
        assert client.post("/gui/tabs", json={"name": "etl"}).status_code == 200
        assert client.post(
            "/gui/steps",
            json={
                "name": "df_etl",
                "config": {"type": "dataframe", "file": "input/b.csv"},
                "tab": "etl",
            },
        ).status_code == 200

        # fichiers places correctement (F0082: main → flow/default/)
        assert (pipe / "default" / "df_main.yaml").is_file()
        assert (pipe / "default" / "etl" / "df_etl.yaml").is_file()

        g_main = client.get("/gui/graph?tab=main").json()
        ids_main = {n["id"] for n in g_main["nodes"]}
        # F0052: create_tab cree aussi un nœud type zone "etl" en main
        assert "df_main" in ids_main
        assert "etl" in ids_main or ids_main == {"df_main"}
        assert g_main["tab"] == "default"

        g_etl = client.get("/gui/graph?tab=etl").json()
        ids_etl = {n["id"] for n in g_etl["nodes"]}
        assert ids_etl == {"df_etl"}
        assert g_etl["tab"] == "default/etl"

        # graphe complet
        g_all = client.get("/gui/graph?tab=*").json()
        all_ids = {n["id"] for n in g_all["nodes"]}
        assert "df_main" in all_ids and "df_etl" in all_ids


def test_chain_edges_within_tab_only(tmp_path: Path):
    """
    Chaine df -> table dans etl ; pas d arete visible dans main.
    """
    client, pipe = _client(tmp_path)
    with client:
        client.post("/gui/tabs", json={"name": "sales"})
        client.post(
            "/gui/steps",
            json={
                "name": "df_s",
                "tab": "sales",
                "config": {"type": "dataframe", "file": "input/s.csv"},
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "t_s",
                "tab": "sales",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["df_s"],
                    "sql": "SELECT 1 AS id",
                },
            },
        )
        # step isolee dans main
        client.post(
            "/gui/steps",
            json={
                "name": "df_other",
                "tab": "default",
                "config": {"type": "dataframe", "file": "input/o.csv"},
            },
        )

        g = client.get("/gui/graph?tab=sales").json()
        assert {n["id"] for n in g["nodes"]} == {"df_s", "t_s"}
        assert ("df_s", "t_s") in _edge_pairs(g["edges"])

        g_main = client.get("/gui/graph?tab=main").json()
        # F0052: nœud zone "sales" visible en main + df_other
        ids_main = {n["id"] for n in g_main["nodes"]}
        assert "df_other" in ids_main
        assert "sales" in ids_main
        assert g_main["edges"] == []


def test_activate_tab_and_create_uses_active(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        client.post("/gui/tabs", json={"name": "report"})
        act = client.post("/gui/tabs/report/activate")
        assert act.status_code == 200
        assert act.json()["active_tab"] == "default/report"

        # sans tab explicite : utilise active
        r = client.post(
            "/gui/steps",
            json={
                "name": "v_rep",
                "config": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS x",
                },
            },
        )
        assert r.status_code == 200, r.text
        assert (pipe / "default" / "report" / "v_rep.yaml").is_file()
        g = client.get("/gui/graph").json()  # active = report
        assert {n["id"] for n in g["nodes"]} == {"v_rep"}


def test_delete_empty_tab(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        client.post("/gui/tabs", json={"name": "tmp"})
        assert (pipe / "default" / "tmp").is_dir()
        r = client.delete("/gui/tabs/tmp")
        assert r.status_code == 200, r.text
        assert not (pipe / "default" / "tmp").exists()
        assert r.json()["active_tab"] == "default"


def test_delete_nonempty_tab_fails(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        client.post("/gui/tabs", json={"name": "full"})
        client.post(
            "/gui/steps",
            json={
                "name": "df_f",
                "tab": "full",
                "config": {"type": "dataframe", "file": "input/x.csv"},
            },
        )
        r = client.delete("/gui/tabs/full")
        assert r.status_code == 400
        assert (pipe / "default" / "full").is_dir()


def test_cannot_delete_main(tmp_path: Path):
    client, _ = _client(tmp_path)
    with client:
        r = client.delete("/gui/tabs/main")
        assert r.status_code == 400


def test_invalid_tab_name(tmp_path: Path):
    client, _ = _client(tmp_path)
    with client:
        r = client.post("/gui/tabs", json={"name": "bad name!"})
        assert r.status_code == 400
        r2 = client.post("/gui/tabs", json={"name": "default"})
        assert r2.status_code == 400


def test_build_still_works_across_loaded_pipeline(tmp_path: Path):
    """
    Build materialise meme si on regarde un autre onglet :
    le moteur charge tout le dossier pipelines.
    """
    client, pipe = _client(tmp_path)
    with client:
        client.post("/gui/tabs", json={"name": "job"})
        client.post(
            "/gui/steps",
            json={
                "name": "t_one",
                "tab": "job",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 42 AS answer",
                },
            },
        )
        # bascule UI sur main
        client.post("/gui/tabs/default/activate")
        b = client.post("/gui/build/t_one?limit=3")
        assert b.status_code == 200, b.text
        data = b.json()
        assert data["ok"] is True
        assert data["rows"] == [[42]]


def test_two_parallel_pipelines_full_scenario(tmp_path: Path):
    """
    Scenario metier: deux pipelines paralleles (ingest + reporting).
    """
    client, pipe = _client(tmp_path)
    with client:
        # zones de premier niveau: revenir en main avant chaque creation
        client.post("/gui/tabs/default/activate")
        client.post("/gui/tabs", json={"name": "ingest"})
        client.post("/gui/tabs/default/activate")
        client.post("/gui/tabs", json={"name": "reporting"})

        # ingest: df -> table
        client.post(
            "/gui/steps",
            json={
                "name": "df_raw",
                "tab": "ingest",
                "config": {"type": "dataframe", "file": "input/raw.csv"},
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "t_clean",
                "tab": "ingest",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["df_raw"],
                    "sql": "SELECT 1 AS id",
                },
            },
        )

        # reporting: table seule (source SQL)
        client.post(
            "/gui/steps",
            json={
                "name": "t_kpi",
                "tab": "reporting",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 'ok' AS status",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "v_kpi",
                "tab": "reporting",
                "config": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": ["t_kpi"],
                    "sql": "SELECT status FROM t_kpi",
                },
            },
        )

        tabs = client.get("/gui/tabs").json()["tabs"]
        by_id = {t["id"]: t for t in tabs}
        assert by_id["default/ingest"]["step_count"] == 2
        assert by_id["default/reporting"]["step_count"] == 2
        # F0052: main contient les 2 nœuds zone (ingest, reporting)
        assert by_id["default"]["step_count"] == 2

        gi = client.get("/gui/graph?tab=ingest").json()
        assert {n["id"] for n in gi["nodes"]} == {"df_raw", "t_clean"}
        assert ("df_raw", "t_clean") in _edge_pairs(gi["edges"])

        gr = client.get("/gui/graph?tab=reporting").json()
        assert {n["id"] for n in gr["nodes"]} == {"t_kpi", "v_kpi"}
        assert ("t_kpi", "v_kpi") in _edge_pairs(gr["edges"])

        # build reporting independant
        b = client.post("/gui/build/v_kpi?limit=3").json()
        assert b["ok"] is True
        assert b["rows"] == [["ok"]]


def test_ui_has_tab_bar():
    html = (
        REPO / "src" / "renatus" / "gui" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert 'data-testid="pipeline-tabs"' in html
    # F0080: + retire de Flux — creation zone via palette Composant
    assert 'data-testid="pipeline-tabs"' in html
    js = read_all_js()
    assert "refreshTabs" in js
    assert "switchTab" in js
    assert "/gui/tabs" in js
    assert "activeTab" in js


def test_yaml_step_store_tab_of(tmp_path: Path):
    from renatus.gui.service import YamlStepStore

    pipe = tmp_path / "flow"
    pipe.mkdir()
    # F0101: id = stem fichier (df_a.yaml / df_b.yaml)
    (pipe / "default").mkdir()
    (pipe / "default" / "df_a.yaml").write_text(
        "df_a:\n  type: dataframe\n  file: x.csv\n", encoding="utf-8"
    )
    (pipe / "default" / "etl").mkdir()
    (pipe / "default" / "etl" / "df_b.yaml").write_text(
        "df_b:\n  type: dataframe\n  file: y.csv\n", encoding="utf-8"
    )
    store = YamlStepStore(pipe)
    assert store.tab_of("df_a") == "default"
    assert store.tab_of("df_b") == "default/etl"
    assert store.steps_in_tab("default") == {"df_a"}
    assert store.steps_in_tab("default/etl") == {"df_b"}
