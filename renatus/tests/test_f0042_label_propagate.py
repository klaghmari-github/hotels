"""
F0042 — renommage de label propage aux dependances (affichage + heal).

requires stocke l id YAML. Le label est resolu a la volee.
Si un require legacy contenait l ancien label, il est reecrit en id.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"


def test_feature_f0042_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0042" in features


def test_ui_handles_label_changed():
    js = read_all_js()
    assert "label_changed" in js
    assert "patchStepLabelInState" in js or "label_new" in js


def test_label_change_updates_dependents_display_meta(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "l.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "src",
                "config": {
                    "type": "table",
                    "label": "Ancien label",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "child",
                "config": {
                    "type": "table",
                    "label": "Enfant",
                    "mode": "create_or_replace",
                    "requires": ["src"],
                    "sql": "SELECT n FROM src",
                },
            },
        )

        # rename label de src
        r = client.put(
            "/gui/step/src",
            json={
                "config": {
                    "type": "table",
                    "label": "Nouveau label",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                }
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["label_changed"] is True
        assert body["label_old"] == "Ancien label"
        assert body["label_new"] == "Nouveau label"
        # dependents voient le nouveau label via get_step
        deps = {d["id"]: d for d in body["dependents"]}
        assert "child" in deps

        # catalog / get child requires meta
        child = client.get("/gui/step/child").json()
        assert child["config"]["requires"] == ["src"]  # id inchange
        # src label a jour
        src = client.get("/gui/step/src").json()
        assert src["label"] == "Nouveau label"
        # child YAML still requires id (F0082: sous main/)
        raw = yaml.safe_load(
            (pipe / "default" / "child.yaml").read_text(encoding="utf-8")
        )
        assert raw["child"]["requires"] == ["src"]
        raw_src = yaml.safe_load(
            (pipe / "default" / "src.yaml").read_text(encoding="utf-8")
        )
        assert raw_src["src"]["label"] == "Nouveau label"

        # graph catalog label
        g = client.get("/gui/graph?tab=*").json()
        cat = {n["id"]: n for n in g.get("catalog") or g["nodes"]}
        assert cat["src"]["label"] == "Nouveau label"


def test_requires_meta_has_fresh_labels_after_rename(tmp_path: Path):
    """Apres rename, requires meta de l enfant resout le nouveau label."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "h.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "src",
                "config": {
                    "type": "table",
                    "label": "LibelleX",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "dep",
                "config": {
                    "type": "table",
                    "label": "Dep",
                    "mode": "create_or_replace",
                    "requires": ["src"],
                    "sql": "SELECT 1",
                },
            },
        )
        client.put(
            "/gui/step/src",
            json={
                "config": {
                    "type": "table",
                    "label": "LibelleY",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                }
            },
        )
        # put de dep renvoie requires meta avec nouveau label de src
        r = client.put(
            "/gui/step/dep",
            json={
                "config": {
                    "type": "table",
                    "label": "Dep",
                    "mode": "create_or_replace",
                    "requires": ["src"],
                    "sql": "SELECT 1",
                }
            },
        )
        assert r.status_code == 200, r.text
        reqs = {x["id"]: x for x in r.json().get("requires") or []}
        assert reqs["src"]["label"] == "LibelleY"
        # YAML dep: toujours id (F0082: sous main/)
        raw = yaml.safe_load(
            (pipe / "default" / "dep.yaml").read_text(encoding="utf-8")
        )
        assert raw["dep"]["requires"] == ["src"]
