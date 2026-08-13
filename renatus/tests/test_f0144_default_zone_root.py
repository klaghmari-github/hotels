"""F0144 — zone racine default + tout le projet sous flow/default/."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.gui.yaml_store import YamlStepStore

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0144_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0144" in text


def test_root_tab_is_default():
    assert YamlStepStore.ROOT_TAB == "default"
    assert YamlStepStore.LEGACY_ROOT_TAB == "main"


def test_project_create_ensures_default(tmp_path: Path):
    boot = tmp_path / "boot"
    boot.mkdir()
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", boot))
    root = tmp_path / "proj"
    with client:
        cr = client.post(
            "/gui/project/create",
            json={
                "path": str(root),
                "name": "proj",
                "pipeline_path": "flow",
            },
        )
        assert cr.status_code == 200, cr.text
        pipe = Path(cr.json()["pipeline_path"]).resolve()
        assert (pipe / "default").is_dir()
        assert (pipe / "default.yaml").is_file()
        body = yaml.safe_load((pipe / "default.yaml").read_text(encoding="utf-8"))
        assert body["default"]["type"] == "zone"
        tabs = client.get("/gui/tabs").json()
        assert tabs["active_tab"] == "default"
        assert any(t["id"] == "default" for t in tabs["tabs"])


def test_open_migrates_main_and_nests_zones(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "main").mkdir()
    (pipe / "main" / "s.yaml").write_text(
        "s:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  script: SELECT 1\n",
        encoding="utf-8",
    )
    (pipe / "main.yaml").write_text(
        "main:\n  type: zone\n  label: main\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "z1.yaml").write_text(
        "z1:\n  type: zone\n  label: z1\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "z1").mkdir()
    (pipe / "z1" / "t.yaml").write_text(
        "t:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  script: SELECT 2\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "o.duckdb", pipe))
    with client:
        assert (pipe / "default").is_dir()
        assert (pipe / "default.yaml").is_file()
        assert not (pipe / "main").exists()
        assert not (pipe / "main.yaml").exists()
        assert (pipe / "default" / "s.yaml").is_file()
        assert (pipe / "default" / "z1").is_dir()
        assert (pipe / "default" / "z1.yaml").is_file()
        assert (pipe / "default" / "z1" / "t.yaml").is_file()
        body = yaml.safe_load((pipe / "default.yaml").read_text(encoding="utf-8"))
        assert "default" in body
        assert body["default"].get("label") == "default"
        tabs = client.get("/gui/tabs").json()
        ids = [t["id"] for t in tabs["tabs"]]
        assert "default" in ids
        assert "default/z1" in ids or "z1" in ids
        # create child zone under default
        r = client.post("/gui/tabs", json={"name": "child"})
        assert r.status_code == 200, r.text
        assert r.json()["id"] == "default/child"
        assert (pipe / "default" / "child").is_dir()
        assert (pipe / "default" / "child.yaml").is_file()


def test_normalize_tab_id_nests_under_default():
    store = YamlStepStore.__new__(YamlStepStore)
    store.active_tab = "default"
    assert store.normalize_tab_id("main") == "default"
    assert store.normalize_tab_id("etl") == "default/etl"
    assert store.normalize_tab_id("default/etl") == "default/etl"
    assert store.normalize_tab_id("etl/sub") == "default/etl/sub"


def test_frontend_uses_default_not_main_zone():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert 'activeTab: "default"' in js
    assert "Zone default protegee" in js


def test_cache_bust_f0144():
    from tests.helpers.static_sources import read_index

    # cache-bust avance avec les features suivantes (ex. F0145)
    assert "main.js?v=F" in read_index()
