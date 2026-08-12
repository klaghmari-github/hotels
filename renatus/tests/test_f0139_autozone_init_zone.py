"""F0139 — auto-zone = template d init → zone physique (type zone)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.pipeline.steps.auto_zone import (
    compute_auto_zone_members,
    normalize_auto_kind,
    recursive_zone_leaf_ids,
)
from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0139_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0139" in text


def test_normalize_allzone_to_flatzone():
    assert normalize_auto_kind("allzone") == "flatzone"
    assert normalize_auto_kind("flatzone") == "flatzone"


def test_recursive_zone_leaf_ids():
    pipe = {
        "default": {"type": "zone", "objects": {"a": {}, "sub": {}}},
        "a": {"type": "table", "requires": []},
        "sub": {"type": "zone", "objects": {"b": {}}},
        "b": {"type": "view", "requires": ["a"]},
    }

    def members_of(zid):
        return (pipe.get(zid) or {}).get("objects") or {}

    leaves = recursive_zone_leaf_ids("default", pipe, members_of)
    assert leaves == {"a", "b"}


def _seed(pipe: Path) -> None:
    pipe.mkdir(parents=True, exist_ok=True)
    (pipe / "default").mkdir(exist_ok=True)
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    for sid, script, reqs in (
        ("t_a", "SELECT 1 AS n", []),
        ("v_b", "SELECT n FROM t_a", ["t_a"]),
        ("v_c", "SELECT n FROM v_b", ["v_b"]),
    ):
        (pipe / "default" / f"{sid}.yaml").write_text(
            yaml.dump(
                {
                    sid: {
                        "type": "table" if sid.startswith("t") else "view",
                        "mode": "create_or_replace",
                        "requires": reqs,
                        "script": script,
                    }
                }
            ),
            encoding="utf-8",
        )


def test_flatzone_creates_physical_zone_with_copies(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed(pipe)
    client = TestClient(create_gui_app(tmp_path / "f.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/auto-zone",
            json={"type": "flatzone", "parent": "default", "name": "flat_default"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "flat_default"
        assert body.get("type") == "zone"
        assert body.get("init_from") in {"flatzone", "allzone"}
        # definition zone physique
        assert (pipe / "default" / "flat_default.yaml").is_file() or (
            pipe / "default" / "flat_default.yaml"
        ).is_file() or (pipe / "default" / "flat_default").is_dir()
        # membres copies
        zdir = pipe / "default" / "flat_default"
        if not zdir.is_dir():
            # peut etre sous main si tab placement
            zdir = pipe / "default" / "flat_default" if False else zdir
        # chercher copies
        found = list(pipe.rglob("t_a.yaml"))
        # origin + copy
        assert len(found) >= 2, found
        cfg = client.get("/gui/step/flat_default").json()
        assert cfg["config"]["type"] == "zone"
        objs = cfg["config"].get("objects") or {}
        assert "t_a" in objs and "v_b" in objs and "v_c" in objs


def test_allzone_alias_creates_zone(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed(pipe)
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/auto-zone",
            json={"type": "allzone", "parent": "default"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("type") == "zone"
        assert body["config"]["type"] == "zone"


def test_backzone_init_zone(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed(pipe)
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/auto-zone",
            json={"type": "backzone", "object": "v_c", "name": "bac_vc"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "bac_vc"
        assert body["config"]["type"] == "zone"
        objs = body["config"].get("objects") or {}
        assert set(objs.keys()) == {"t_a", "v_b", "v_c"}


def test_ui_flatzone_palette():
    js = read_all_js()
    assert "flatzone" in js
    assert "pickParentZoneForFlat" in js or "flat-parent" in js
    assert "Flat zone" in js or "flatzone" in js
    html = read_index()
    # dialog parent cree dynamiquement — presence code
    assert "Zone source" in js or "zone parent" in js.lower() or "flat-parent" in js
