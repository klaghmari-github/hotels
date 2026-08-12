"""A0016 — vider Objects d une zone (seules copies → suppression, pas d erreur)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_anomaly_a0016_registered():
    text = (REPO / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0016" in text


def test_empty_main_objects_deletes_sole_copies(tmp_path: Path):
    """Popup Objects: retirer tous les membres de main → zone vide, OK 200."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    for sid, script in (("t_a", "SELECT 1 AS n"), ("t_b", "SELECT 2 AS n")):
        (pipe / "default" / f"{sid}.yaml").write_text(
            yaml.dump(
                {
                    sid: {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": script,
                    }
                }
            ),
            encoding="utf-8",
        )
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        before = client.get("/gui/step/default").json()["config"]["objects"]
        assert "t_a" in before and "t_b" in before

        r = client.put(
            "/gui/step/default",
            json={
                "config": {
                    "type": "zone",
                    "label": "default",
                    "objects": {},
                }
            },
        )
        assert r.status_code == 200, r.text

        after = client.get("/gui/step/default").json()["config"]["objects"]
        assert after == {} or after == {}
        assert "t_a" not in after
        assert "t_b" not in after

        g = client.get("/gui/graph?tab=main").json()
        ids = {
            n["id"]
            for n in g["nodes"]
            if not n.get("external") and n.get("type") != "zone"
        }
        assert "t_a" not in ids
        assert "t_b" not in ids
        # fichiers supprimes
        assert not (pipe / "default" / "t_a.yaml").exists()
        assert not (pipe / "default" / "t_b.yaml").exists()


def test_empty_zone_cascades_subzone(tmp_path: Path):
    """Vider main supprime aussi une sous-zone (seule copie) apres son contenu."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "t_root",
                    "tab": "default",
                    "config": {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": "SELECT 1 AS n",
                    },
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "z1",
                    "tab": "default",
                    "config": {
                        "type": "zone",
                        "label": "z1",
                        "objects": {},
                    },
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "t_in_z",
                    "tab": "z1",
                    "config": {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": "SELECT 3 AS n",
                    },
                },
            ).status_code
            == 200
        )

        r = client.put(
            "/gui/step/default",
            json={
                "config": {
                    "type": "zone",
                    "label": "default",
                    "objects": {},
                }
            },
        )
        assert r.status_code == 200, r.text

        gall = {
            n["id"] for n in client.get("/gui/graph?tab=*").json()["nodes"]
        }
        # catalog still has main zone
        assert "t_root" not in gall
        assert "t_in_z" not in gall
        assert "z1" not in gall


def test_shared_member_detach_not_delete(tmp_path: Path):
    """Membre partage: retirer de main detache sans supprimer le composant."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "c.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "shared",
                    "tab": "default",
                    "config": {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": "SELECT 1 AS n",
                    },
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "z_share",
                    "tab": "default",
                    "config": {
                        "type": "zone",
                        "label": "share",
                        "objects": {"shared": {}},
                    },
                },
            ).status_code
            == 200
        )
        # garder z_share, retirer shared de main
        r = client.put(
            "/gui/step/default",
            json={
                "config": {
                    "type": "zone",
                    "label": "default",
                    "objects": {"z_share": {}},
                }
            },
        )
        assert r.status_code == 200, r.text
        # shared encore dans le projet via z_share
        gall = {
            n["id"] for n in client.get("/gui/graph?tab=*").json()["nodes"]
        }
        assert "shared" in gall
        gmain = {
            n["id"]
            for n in client.get("/gui/graph?tab=main").json()["nodes"]
            if not n.get("external")
        }
        assert "shared" not in gmain
        assert "z_share" in gmain
