"""F0128 / F0139 — templates auto → zones physiques."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.pipeline.steps.auto_zone import (
    auto_zone_id_for,
    compute_auto_zone_members,
    recursive_dependents,
    recursive_requires,
)
from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0128_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0128" in text


def test_ui_auto_palette():
    html = read_index()
    # convert legacy encore present dans HTML
    assert 'data-testid="btn-auto-convert"' in html or "auto-convert" in html
    js = read_all_js()
    assert "flatzone" in js or "allzone" in js
    assert "backzone" in js
    assert "forzone" in js
    assert "bidzone" in js
    assert "/gui/auto-zone" in js


def test_compute_lineage_helpers():
    pipe = {
        "a": {"type": "table", "requires": []},
        "b": {"type": "view", "requires": ["a"]},
        "c": {"type": "view", "requires": ["b"]},
        "d": {"type": "view", "requires": ["a"]},
    }
    assert recursive_requires("c", pipe) == {"a", "b", "c"}
    assert recursive_dependents("a", pipe) == {"a", "b", "c", "d"}
    bid = compute_auto_zone_members("bidzone", pipe, object_id="b")
    assert set(bid.keys()) == {"a", "b", "c"}
    assert auto_zone_id_for("backzone", "t_x") == "bac_t_x"
    assert auto_zone_id_for("flatzone", "default") == "flat_default"
    assert auto_zone_id_for("allzone", "default") == "flat_default"


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


def test_flatzone_and_backzone_materialize(tmp_path: Path):
    """F0139: creation → type zone + copies YAML."""
    pipe = tmp_path / "flow"
    _seed(pipe)
    client = TestClient(create_gui_app(tmp_path / "az.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/auto-zone",
            json={"type": "flatzone", "parent": "default", "name": "flat_default"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "flat_default"
        assert body.get("type") == "zone"
        assert body["config"]["type"] == "zone"
        objs = body.get("objects") or body["config"].get("objects") or {}
        assert "t_a" in objs and "v_b" in objs and "v_c" in objs
        # dossier membres
        assert (pipe / "default" / "flat_default").is_dir() or any(
            p.name == "t_a.yaml" and "flat_default" in str(p)
            for p in pipe.rglob("t_a.yaml")
        )

        # deuxieme creation → nouvel id (pas reutilise logique)
        r2 = client.post(
            "/gui/auto-zone",
            json={"type": "flatzone", "parent": "default"},
        )
        assert r2.status_code == 200
        assert r2.json()["id"] != "flat_default" or r2.json().get("reused")

        rb = client.post(
            "/gui/auto-zone",
            json={"type": "backzone", "object": "v_c", "name": "bac_v_c"},
        )
        assert rb.status_code == 200, rb.text
        assert rb.json()["id"] == "bac_v_c"
        assert rb.json()["config"]["type"] == "zone"
        mem = rb.json().get("objects") or rb.json()["config"].get("objects") or {}
        assert set(mem.keys()) == {"t_a", "v_b", "v_c"}

        tabs = client.get("/gui/tabs").json()
        ids = [t["id"] for t in tabs["tabs"]]
        assert "default" in ids
        # zone physique listable
        assert any("bac_v_c" in i or i == "bac_v_c" for i in ids)
        assert "auto" not in ids

        # graphe de la zone bac_v_c
        g = client.get("/gui/graph?tab=bac_v_c").json()
        gids = {n["id"] for n in g["nodes"] if not n.get("external")}
        assert gids == {"t_a", "v_b", "v_c"}


def test_forzone_and_bidzone(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed(pipe)
    client = TestClient(create_gui_app(tmp_path / "fz.duckdb", pipe))
    with client:
        rf = client.post(
            "/gui/auto-zone", json={"type": "forzone", "object": "t_a"}
        )
        assert rf.status_code == 200
        assert rf.json()["id"] == "for_t_a"
        assert rf.json()["config"]["type"] == "zone"
        assert set((rf.json().get("objects") or rf.json()["config"]["objects"]).keys()) == {
            "t_a",
            "v_b",
            "v_c",
        }
        rbi = client.post(
            "/gui/auto-zone", json={"type": "bidzone", "object": "v_b"}
        )
        assert rbi.status_code == 200
        assert rbi.json()["id"] == "bid_v_b"
        assert set(
            (rbi.json().get("objects") or rbi.json()["config"]["objects"]).keys()
        ) == {
            "t_a",
            "v_b",
            "v_c",
        }
