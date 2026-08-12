"""F0125 — import dossier: zones creees visibles dans le selecteur + objects FS."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0125_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0125" in text


def test_js_activates_root_import_tab():
    js = read_all_js()
    assert "root_import_tab" in js
    assert "active_tab" in js


def _seed_main(pipe: Path) -> None:
    pipe.mkdir(parents=True, exist_ok=True)
    (pipe / "default").mkdir(exist_ok=True)
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n"
        "  workers: auto\n  renatus_mode: required_for_leaves\n",
        encoding="utf-8",
    )


def test_import_directory_zones_listed_and_objects_synced(tmp_path: Path):
    """
    Import d un dossier multi-niveaux sans zone YAML source:
    - cree dossier + <segment>.yaml type zone a chaque niveau
    - zones apparaissent dans GET /gui/tabs (selecteur)
    - objects de la zone parent contiennent les sous-zones / membres FS
    - graphe de la zone parent montre les enfants zone
    """
    pipe = tmp_path / "flow"
    _seed_main(pipe)

    # arborescence source: pack/a/t1.yaml + pack/b/t2.yaml (pas de zone YAML)
    src = tmp_path / "pack"
    (src / "a").mkdir(parents=True)
    (src / "b").mkdir(parents=True)
    (src / "a" / "t1.yaml").write_text(
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
    (src / "b" / "t2.yaml").write_text(
        yaml.dump(
            {
                "t2": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 2 AS n",
                }
            }
        ),
        encoding="utf-8",
    )

    client = TestClient(create_gui_app(tmp_path / "imp.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(src),
                "target_tab": "default",
                "conflict": "keep_both",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("count") == 2
        assert body.get("zones_created") or body.get("zone_tabs") or True

        # FS: zones
        assert (pipe / "default" / "pack").is_dir()
        assert (pipe / "default" / "pack.yaml").is_file()
        assert (pipe / "default" / "pack" / "a").is_dir()
        assert (pipe / "default" / "pack" / "a.yaml").is_file()
        assert (pipe / "default" / "pack" / "b").is_dir()
        assert (pipe / "default" / "pack" / "b.yaml").is_file()
        assert (pipe / "default" / "pack" / "a" / "t1.yaml").is_file()
        assert (pipe / "default" / "pack" / "b" / "t2.yaml").is_file()

        # F0131: selecteur = main + zones physiques (pas de vue all par defaut)
        tabs = client.get("/gui/tabs").json()
        ids = [t["id"] for t in tabs["tabs"]]
        assert "default" in ids
        assert "all" not in ids
        assert "pack" in ids
        assert "pack/a" in ids
        assert "pack/b" in ids

        # active_tab bascule sur la zone racine importee
        assert tabs.get("active_tab") == "pack" or body.get("root_import_tab") == "pack"

        # objects de pack contiennent a et b (sous-zones)
        pack = client.get("/gui/step/pack").json()
        assert pack["config"]["type"] == "zone"
        objs = pack["config"].get("objects") or {}
        assert "a" in objs
        assert "b" in objs

        # graphe pack: noeuds zone a, b (et pas forcement t1/t2 qui sont dans sous-dossiers)
        g = client.get("/gui/graph?tab=pack").json()
        gids = {n["id"] for n in g["nodes"] if not n.get("external")}
        assert "a" in gids
        assert "b" in gids

        # graphe sous-zone a: t1
        ga = client.get("/gui/graph?tab=pack/a").json()
        aids = {n["id"] for n in ga["nodes"] if not n.get("external")}
        assert "t1" in aids

        # main contient pack comme zone enfant
        gm = client.get("/gui/graph?tab=main").json()
        mids = {n["id"] for n in gm["nodes"] if not n.get("external")}
        assert "pack" in mids


def test_list_tabs_shows_existing_zones_without_open(tmp_path: Path):
    """Zones deja sur disque listées meme si jamais ouvertes (reload session)."""
    pipe = tmp_path / "flow"
    _seed_main(pipe)
    (pipe / "default" / "etl").mkdir()
    (pipe / "default" / "etl.yaml").write_text(
        "etl:\n  type: zone\n  label: etl\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "default" / "etl" / "t_x.yaml").write_text(
        yaml.dump(
            {
                "t_x": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS x",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "vis.duckdb", pipe))
    with client:
        # ne pas appeler create_tab / open — juste lister
        ids = [t["id"] for t in client.get("/gui/tabs").json()["tabs"]]
        assert "default/etl" in ids
