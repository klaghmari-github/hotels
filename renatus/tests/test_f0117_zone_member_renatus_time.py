"""F0117 — zone Renatus met a jour renatus_time de chaque membre builde."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0117_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0117" in text


def test_js_shows_member_times():
    js = read_all_js()
    assert "member_renatus_times" in js or "renatus_time" in js


def test_zone_build_updates_member_renatus_times(tmp_path: Path):
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
                    "workers": "queue",
                    "renatus_mode": "root_to_leaves",
                }
            }
        ),
        encoding="utf-8",
    )
    for sid, script, reqs in (
        ("t_a", "SELECT 1 AS n", []),
        ("v_b", "SELECT n FROM t_a", ["t_a"]),
    ):
        (pipe / "default" / f"{sid}.yaml").write_text(
            yaml.dump(
                {
                    sid: {
                        "type": "table" if sid == "t_a" else "view",
                        "mode": "create_or_replace",
                        "requires": reqs,
                        "script": script,
                    }
                }
            ),
            encoding="utf-8",
        )

    client = TestClient(create_gui_app(tmp_path / "t.duckdb", pipe))
    with client:
        # avant: pas de temps
        assert client.get("/gui/step/t_a").json().get("renatus_time") is None
        assert client.get("/gui/step/v_b").json().get("renatus_time") is None
        assert client.get("/gui/step/default").json().get("renatus_time") is None

        b = client.post("/gui/build/default")
        assert b.status_code == 200, b.text
        body = b.json()
        assert body.get("action") == "zone_build"
        assert body.get("ok") is True
        # temps global zone
        assert body.get("renatus_time") is not None
        assert body["renatus_time"] >= 0

        # chaque membre builde a un temps
        built = {x["id"]: x for x in body.get("built") or []}
        assert "t_a" in built and "v_b" in built
        assert built["t_a"].get("renatus_time") is not None
        assert built["v_b"].get("renatus_time") is not None
        times = body.get("member_renatus_times") or {}
        assert "t_a" in times and "v_b" in times

        # get_step expose les temps calcules
        assert client.get("/gui/step/t_a").json().get("renatus_time") is not None
        assert client.get("/gui/step/v_b").json().get("renatus_time") is not None
        assert client.get("/gui/step/default").json().get("renatus_time") is not None


def test_zone_leaves_mode_times_requires_too(tmp_path: Path):
    """required_for_leaves chronometre aussi les requires dans la zone."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n"
        "  workers: queue\n  renatus_mode: required_for_leaves\n",
        encoding="utf-8",
    )
    for sid, script, reqs in (
        ("t_a", "SELECT 1 AS n", []),
        ("v_b", "SELECT n FROM t_a", ["t_a"]),
    ):
        (pipe / "default" / f"{sid}.yaml").write_text(
            yaml.dump(
                {
                    sid: {
                        "type": "table" if sid == "t_a" else "view",
                        "mode": "create_or_replace",
                        "requires": reqs,
                        "script": script,
                    }
                }
            ),
            encoding="utf-8",
        )
    client = TestClient(create_gui_app(tmp_path / "u.duckdb", pipe))
    with client:
        body = client.post("/gui/build/default").json()
        assert body.get("ok") is True
        times = body.get("member_renatus_times") or {}
        assert "t_a" in times
        assert "v_b" in times
        assert client.get("/gui/step/t_a").json()["renatus_time"] is not None
