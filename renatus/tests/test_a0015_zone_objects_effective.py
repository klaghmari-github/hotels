"""A0015 — zone Objects: liste effective (YAML ∪ FS), pas 0 si fichiers presents."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_anomaly_a0015_registered():
    text = (REPO / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0015" in text


def test_main_objects_include_fs_members(tmp_path: Path):
    """main.yaml objects:{} mais composants dans flow/default/ → get_step liste."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "default" / "t1.yaml").write_text(
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
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "t2.yaml").write_text(
        yaml.dump(
            {
                "t2": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": ["t1"],
                    "script": "SELECT n FROM t1",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        st = client.get("/gui/step/default").json()
        assert st["ok"] is True
        objs = st["config"].get("objects") or {}
        assert "t1" in objs
        assert "t2" in objs
        assert "main" not in objs

        # graphe main: composants presents
        g = client.get("/gui/graph?tab=main").json()
        ids = {n["id"] for n in g["nodes"] if not n.get("external")}
        assert "t1" in ids and "t2" in ids
        # catalog (tab=*) inclut les zones avec objects effectifs
        gall = client.get("/gui/graph?tab=*").json()
        main_cat = next(n for n in (gall.get("catalog") or []) if n["id"] == "default")
        g_objs = main_cat.get("objects") or {}
        assert "t1" in g_objs and "t2" in g_objs


def test_zone_objects_union_yaml_and_fs(tmp_path: Path):
    """objects YAML + composant cree dans le dossier zone (API tab)."""
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
                    "name": "df_a",
                    "tab": "default",
                    "config": {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": "SELECT 1 AS x",
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
                        "label": "Z1",
                        "objects": {"df_a": {}},
                    },
                },
            ).status_code
            == 200
        )
        # composant cree dans l onglet zone (FS), sans re-maj objects YAML
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "t_fs",
                    "tab": "z1",
                    "config": {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": "SELECT 2 AS y",
                    },
                },
            ).status_code
            == 200
        )
        # YAML zone n a pas t_fs
        z1_yaml = yaml.safe_load((pipe / "default" / "z1.yaml").read_text(encoding="utf-8"))
        assert "t_fs" not in (z1_yaml["z1"].get("objects") or {})

        st = client.get("/gui/step/z1").json()
        objs = st["config"].get("objects") or {}
        assert "df_a" in objs
        assert "t_fs" in objs


def test_put_zone_heal_and_detach_fs_member(tmp_path: Path):
    """
    Sauvegarde main.objects heale le YAML; retirer un membre partage
    detache la copie main (prev effectif A0015).
    """
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "c.duckdb", pipe))
    with client:
        for sid, script in (
            ("keep_me", "SELECT 1 AS n"),
            ("drop_me", "SELECT 2 AS n"),
        ):
            assert (
                client.post(
                    "/gui/steps",
                    json={
                        "name": sid,
                        "tab": "default",
                        "config": {
                            "type": "table",
                            "mode": "create_or_replace",
                            "requires": [],
                            "script": script,
                        },
                    },
                ).status_code
                == 200
            )
        # zone partagee: copie de drop_me (pour pouvoir le detacher de main)
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "z_share",
                    "tab": "default",
                    "config": {
                        "type": "zone",
                        "label": "share",
                        "objects": {"drop_me": {}},
                    },
                },
            ).status_code
            == 200
        )
        # effective main inclut keep_me, drop_me, z_share
        before = client.get("/gui/step/default").json()["config"]["objects"]
        assert "keep_me" in before and "drop_me" in before
        assert "z_share" in before

        # garder keep_me + z_share, retirer drop_me
        r = client.put(
            "/gui/step/default",
            json={
                "config": {
                    "type": "zone",
                    "label": "default",
                    "objects": {
                        "keep_me": {},
                        "z_share": {},
                    },
                }
            },
        )
        assert r.status_code == 200, r.text

        # YAML heale
        main_yaml = yaml.safe_load((pipe / "default.yaml").read_text(encoding="utf-8"))
        yobjs = main_yaml["default"]["objects"]
        assert "keep_me" in yobjs
        assert "z_share" in yobjs
        assert "drop_me" not in yobjs

        st = client.get("/gui/step/default").json()
        objs = st["config"].get("objects") or {}
        assert "keep_me" in objs
        assert "z_share" in objs
        assert "drop_me" not in objs

        gmain = {
            n["id"]
            for n in client.get("/gui/graph?tab=main").json()["nodes"]
            if not n.get("external")
        }
        assert "keep_me" in gmain
        assert "drop_me" not in gmain
        # encore dans le projet via z_share
        gz = {
            n["id"]
            for n in client.get("/gui/graph?tab=z_share").json()["nodes"]
            if not n.get("external")
        }
        assert "drop_me" in gz
