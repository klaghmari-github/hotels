"""F0145 — multi-presence via symlinks (meme nom = meme id)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.gui.yaml_store import YamlStepStore

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0145_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0145" in text


def test_attach_creates_symlink_same_name(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    store = YamlStepStore(pipe)
    store.save_step(
        "obj1",
        {
            "type": "table",
            "label": "L1",
            "mode": "create_or_replace",
            "requires": [],
            "script": "SELECT 1",
        },
        tab="default",
    )
    master = pipe / "default" / "obj1.yaml"
    assert master.is_file() and not master.is_symlink()

    link = store.attach_to_tab("obj1", "default/zone_a")
    assert link == pipe / "default" / "zone_a" / "obj1.yaml"
    assert link.is_symlink()
    assert link.name == master.name
    assert link.resolve() == master.resolve()
    # meme contenu
    assert yaml.safe_load(link.read_text())["obj1"]["label"] == "L1"
    assert len(store.origins_of("obj1")) == 2


def test_save_updates_single_physical_file(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    store = YamlStepStore(pipe)
    store.save_step(
        "t1",
        {
            "type": "table",
            "label": "A",
            "mode": "create_or_replace",
            "requires": [],
            "script": "SELECT 1",
        },
        tab="default",
    )
    store.attach_to_tab("t1", "default/z")
    store.save_step(
        "t1",
        {
            "type": "table",
            "label": "B",
            "mode": "create_or_replace",
            "requires": [],
            "script": "SELECT 2",
        },
        tab="default",
    )
    master = pipe / "default" / "t1.yaml"
    link = pipe / "default" / "z" / "t1.yaml"
    assert not master.is_symlink()
    assert link.is_symlink()
    assert yaml.safe_load(master.read_text())["t1"]["label"] == "B"
    assert yaml.safe_load(link.read_text())["t1"]["label"] == "B"
    # un seul inode physique pour le contenu
    assert master.stat().st_ino == link.stat().st_ino


def test_zone_folder_symlink_on_attach_zone(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "zone_src",
                    "tab": "default",
                    "config": {"type": "zone", "label": "Src", "objects": {}},
                },
            ).status_code
            == 200
        )
        # membre dans la zone source
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "inner",
                    "tab": "zone_src",
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
        assert (pipe / "default" / "zone_src").is_dir()
        assert not (pipe / "default" / "zone_src").is_symlink()

        # partager zone_src dans une autre zone parente
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "zone_host",
                    "tab": "default",
                    "config": {
                        "type": "zone",
                        "label": "Host",
                        "objects": {"zone_src": {}},
                    },
                },
            ).status_code
            == 200
        )
        link_yaml = pipe / "default" / "zone_host" / "zone_src.yaml"
        link_dir = pipe / "default" / "zone_host" / "zone_src"
        assert link_yaml.is_symlink()
        assert link_dir.is_symlink()
        assert link_yaml.resolve() == (
            pipe / "default" / "zone_src.yaml"
        ).resolve()
        assert link_dir.resolve() == (pipe / "default" / "zone_src").resolve()
        # contenu accessible via le lien dossier
        assert (link_dir / "inner.yaml").is_file()


def test_gui_share_unshare_symlink(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "m.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "obj1",
                    "tab": "default",
                    "config": {
                        "type": "table",
                        "label": "Label1",
                        "name": "obj1",
                        "mode": "create_or_replace",
                        "requires": [],
                        "sql": "SELECT 1 AS n",
                    },
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "zone_a",
                    "tab": "default",
                    "config": {
                        "type": "zone",
                        "label": "ZA",
                        "objects": {"obj1": {}},
                    },
                },
            ).status_code
            == 200
        )
        linked = pipe / "default" / "zone_a" / "obj1.yaml"
        master = pipe / "default" / "obj1.yaml"
        assert master.is_file() and not master.is_symlink()
        assert linked.is_symlink()
        assert linked.resolve() == master.resolve()

        st = client.get("/gui/step/obj1").json()
        zids = {z["id"] for z in st["zones"]}
        assert "default" in zids and "zone_a" in zids
        za = next(z for z in st["zones"] if z["id"] == "zone_a")
        assert za.get("symlink") is True

        # save propage via le meme inode
        assert (
            client.put(
                "/gui/step/obj1",
                json={
                    "config": {
                        "type": "table",
                        "label": "Label10",
                        "name": "obj1",
                        "mode": "create_or_replace",
                        "requires": [],
                        "sql": "SELECT 1 AS n",
                    }
                },
            ).status_code
            == 200
        )
        assert yaml.safe_load(linked.read_text())["obj1"]["label"] == "Label10"

        r = client.post(
            "/gui/step/obj1/unshare-zone",
            json={"zone_tab": "zone_a"},
        )
        assert r.status_code == 200, r.text
        assert not linked.exists()
        assert master.is_file()


def test_cache_bust_f0145():
    from tests.helpers.static_sources import read_index

    assert "F0145" in read_index() or "main.js?v=F" in read_index()
