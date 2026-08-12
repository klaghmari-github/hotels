"""F0082 / F0144 — zone default protegee = flow/default/."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.gui.yaml_store import YamlStepStore

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0082_registered():
    assert "F0082" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_ensure_main_creates_folder_and_yaml(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    # step a la racine → migre vers default/
    (pipe / "t1.yaml").write_text(
        "t1:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  script: SELECT 1\n",
        encoding="utf-8",
    )
    store = YamlStepStore(pipe)
    assert (pipe / "default").is_dir()
    assert (pipe / "default.yaml").is_file()
    assert (pipe / "default" / "t1.yaml").is_file()
    assert not (pipe / "t1.yaml").exists()
    body = yaml.safe_load((pipe / "default.yaml").read_text(encoding="utf-8"))
    assert body["default"]["type"] == "zone"
    assert store.dir_for_tab("default") == (pipe / "default").resolve()
    assert "t1" in store.steps_in_tab("default")
    assert "default" not in store.steps_in_tab("default")


def test_legacy_main_migrates_to_default(tmp_path: Path):
    """F0144: flow/main + main.yaml → flow/default + default.yaml."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "main").mkdir()
    (pipe / "main" / "a.yaml").write_text(
        "a:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  script: SELECT 1\n",
        encoding="utf-8",
    )
    (pipe / "main.yaml").write_text(
        "main:\n  type: zone\n  label: main\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "etl.yaml").write_text(
        "etl:\n  type: zone\n  label: etl\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "etl").mkdir()
    (pipe / "etl" / "b.yaml").write_text(
        "b:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  script: SELECT 2\n",
        encoding="utf-8",
    )
    store = YamlStepStore(pipe)
    assert (pipe / "default").is_dir()
    assert (pipe / "default.yaml").is_file()
    assert not (pipe / "main").exists()
    assert not (pipe / "main.yaml").exists()
    assert (pipe / "default" / "a.yaml").is_file()
    assert (pipe / "default" / "etl").is_dir()
    assert (pipe / "default" / "etl.yaml").is_file()
    assert (pipe / "default" / "etl" / "b.yaml").is_file()
    body = yaml.safe_load((pipe / "default.yaml").read_text(encoding="utf-8"))
    assert "default" in body
    assert body["default"]["label"] == "default"
    assert store.zone_path_for("etl", "default") == "default/etl"
    assert "a" in store.steps_in_tab("default")
    assert "b" in store.steps_in_tab("default/etl")


def test_cannot_delete_main_zone(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        tabs = client.get("/gui/tabs").json()
        ids = {t["id"] for t in tabs.get("tabs") or []}
        assert "default" in ids
        st = client.get("/gui/step/default")
        assert st.status_code == 200
        assert st.json().get("config", {}).get("type") == "zone"
        r = client.delete("/gui/step/default")
        assert r.status_code >= 400
        assert "protegee" in r.text.lower() or "default" in r.text.lower()


def test_new_steps_go_under_main(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "obj_a",
                "tab": "default",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 2 AS n",
                },
            },
        )
        assert r.status_code == 200, r.text
        assert (pipe / "default" / "obj_a.yaml").is_file()


def test_ui_protects_main_delete():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "Zone default protegee" in js
    assert (
        'state.selected === "default"' in js
        or 'name === "default"' in js
        or 'name === "main"' in js
    )
