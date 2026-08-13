"""
F0064 — supprimer une zone ferme ses onglets ouverts (server + GUI sync).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0064_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0064" in text


def _client(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    return TestClient(create_gui_app(tmp_path / "m.duckdb", pipe)), pipe


def test_delete_zone_closes_open_tab(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "zone_gone",
                "tab": "default",
                "config": {"type": "zone", "label": "Gone"},
            },
        )
        assert r.status_code == 200, r.text
        assert (pipe / "default" / "zone_gone.yaml").is_file()
        assert (pipe / "default" / "zone_gone").is_dir()

        act = client.post("/gui/tabs/zone_gone/activate")
        assert act.status_code == 200, act.text
        assert act.json()["active_tab"] == "default/zone_gone"
        tabs_before = client.get("/gui/tabs").json()
        assert "default/zone_gone" in [t["id"] for t in tabs_before["tabs"]]

        deleted = client.delete("/gui/step/zone_gone")
        assert deleted.status_code == 200, deleted.text
        body = deleted.json()
        assert body["ok"] is True
        closed = body.get("closed_tabs", [])
        assert "default/zone_gone" in closed or "zone_gone" in closed
        assert body["active_tab"] == "default"
        ids = [t["id"] for t in body["tabs"]]
        assert "zone_gone" not in ids
        assert "default/zone_gone" not in ids
        assert "default" in ids

        # disque nettoyé
        assert not (pipe / "default" / "zone_gone.yaml").exists()
        assert not (pipe / "default" / "zone_gone").exists()

        # GET tabs confirme
        tabs_after = client.get("/gui/tabs").json()
        assert tabs_after["active_tab"] == "default"
        assert "zone_gone" not in [t["id"] for t in tabs_after["tabs"]]
        assert "default/zone_gone" not in [t["id"] for t in tabs_after["tabs"]]


def test_delete_zone_while_on_parent_still_closes_tab(tmp_path: Path):
    """Zone selectionnee depuis default: l onglet zone ouvert en fond doit partir."""
    client, pipe = _client(tmp_path)
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "zone_bg",
                "tab": "default",
                "config": {"type": "zone", "label": "BG"},
            },
        )
        client.post("/gui/tabs/zone_bg/activate")
        client.post("/gui/tabs/default/activate")
        assert client.get("/gui/tabs").json()["active_tab"] == "default"
        tab_ids = [t["id"] for t in client.get("/gui/tabs").json()["tabs"]]
        assert "default/zone_bg" in tab_ids or "zone_bg" in tab_ids

        deleted = client.delete("/gui/step/zone_bg")
        assert deleted.status_code == 200, deleted.text
        body = deleted.json()
        closed = body.get("closed_tabs", [])
        assert "default/zone_bg" in closed or "zone_bg" in closed
        assert "zone_bg" not in [t["id"] for t in body["tabs"]]
        assert "default/zone_bg" not in [t["id"] for t in body["tabs"]]
        assert body["active_tab"] == "default"
        assert not (pipe / "default" / "zone_bg.yaml").exists()


def test_js_delete_step_resyncs_tabs():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "closed_tabs" in js or "refreshTabs" in js
    assert "deleteStep" in js
    # resync apres DELETE
    assert "renderPipelineTabs" in js
    assert "data.tabs" in js or "data.active_tab" in js
    # import refreshTabs dans step-crud
    assert "refreshTabs" in js
