"""F0116 — zone workers + renatus_mode (required_for_leaves / root_to_leaves)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.pipeline.steps.org import (
    RENATUS_MODE_LEAVES,
    RENATUS_MODE_ROOT,
    normalize_renatus_mode,
    normalize_zone_workers,
)
from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0116_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0116" in text


def test_normalize_workers_and_mode():
    assert normalize_zone_workers(None) == "auto"
    assert normalize_zone_workers("queue") == "queue"
    assert normalize_zone_workers(1) == "queue"
    assert normalize_zone_workers(4) == "4"
    assert normalize_renatus_mode(None) == RENATUS_MODE_LEAVES
    assert normalize_renatus_mode("root_to_leaves") == RENATUS_MODE_ROOT
    assert normalize_renatus_mode("required for leaves") == RENATUS_MODE_LEAVES


def test_ui_zone_workers_fields():
    html = read_index()
    assert 'data-testid="field-zone-workers"' in html
    assert 'data-testid="cfg-zone-workers"' in html
    assert 'data-testid="field-zone-renatus-mode"' in html
    assert 'data-testid="cfg-zone-renatus-mode"' in html
    assert "required_for_leaves" in html
    assert "root_to_leaves" in html
    js = read_all_js()
    assert "zoneWorkers" in js or "cfgZoneWorkers" in js
    assert "renatus_mode" in js


def test_zone_defaults_and_build_modes(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        yaml.dump(
            {
                "default": {
                    "type": "zone",
                    "label": "default",
                    "objects": {},
                    "workers": "auto",
                    "renatus_mode": "required_for_leaves",
                }
            }
        ),
        encoding="utf-8",
    )
    # line1: t1 -> v1 (leaf v1)
    # line2: t2 alone (leaf t2)
    for sid, script, reqs in (
        ("t1", "SELECT 1 AS n", []),
        ("v1", "SELECT n FROM t1", ["t1"]),
        ("t2", "SELECT 2 AS n", []),
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

    client = TestClient(create_gui_app(tmp_path / "z.duckdb", pipe))
    with client:
        st = client.get("/gui/step/default").json()
        assert st["config"]["workers"] == "auto"
        assert st["config"]["renatus_mode"] == "required_for_leaves"

        # leaves mode: build v1 (pulls t1) + t2
        b = client.post("/gui/build/main")
        assert b.status_code == 200, b.text
        body = b.json()
        assert body.get("action") == "zone_build"
        assert body.get("renatus_mode") == "required_for_leaves"
        assert body.get("workers") == "auto"
        assert body.get("flow_lines") == 2
        built_ids = [x["id"] for x in body.get("built") or []]
        # leaves: v1 and t2 (t1 may appear as dep of v1 inside p_table_view,
        # but zone-level targets are leaves)
        assert "v1" in built_ids
        assert "t2" in built_ids

        # switch to root_to_leaves
        r = client.put(
            "/gui/step/default",
            json={
                "config": {
                    "type": "zone",
                    "label": "default",
                    "objects": {
                        "t1": {},
                        "v1": {},
                        "t2": {},
                    },
                    "workers": "queue",
                    "renatus_mode": "root_to_leaves",
                }
            },
        )
        assert r.status_code == 200, r.text
        st2 = client.get("/gui/step/default").json()
        assert st2["config"]["workers"] == "queue"
        assert st2["config"]["renatus_mode"] == "root_to_leaves"

        b2 = client.post("/gui/build/main").json()
        assert b2.get("renatus_mode") == "root_to_leaves"
        assert b2.get("workers") == "queue"
        built2 = [x["id"] for x in b2.get("built") or []]
        # root_to_leaves: all members appear as zone targets
        assert "t1" in built2
        assert "v1" in built2
        assert "t2" in built2


def test_flow_lines_partition():
    from renatus.gui.service import GuiService

    pipeline = {
        "a": {"type": "table", "requires": []},
        "b": {"type": "view", "requires": ["a"]},
        "c": {"type": "table", "requires": []},
    }
    lines = GuiService._zone_flow_lines(["a", "b", "c"], pipeline)
    assert len(lines) == 2
    flat = {frozenset(x) for x in lines}
    assert frozenset(["a", "b"]) in flat
    assert frozenset(["c"]) in flat
    leaves = GuiService._zone_line_leaves(["a", "b"], pipeline)
    assert leaves == ["b"]
