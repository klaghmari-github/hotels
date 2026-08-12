"""F0118 — progression UI Renatus zone (plan + etats graphe + barre)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0118_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0118" in text


def test_ui_build_progress_markup_and_css():
    html = read_index()
    assert 'data-testid="build-progress"' in html
    assert 'id="build-progress"' in html
    assert 'id="build-progress-fill"' in html
    assert 'id="build-progress-label"' in html
    css = read_css()
    assert ".build-progress" in css
    assert ".build-progress-fill" in css
    assert ".node.build-pending" in css
    assert ".node.build-running" in css
    assert ".node.build-done" in css
    assert ".node.build-idle" in css
    assert "build-running-pulse" in css


def test_js_zone_build_progress_orchestration():
    js = read_all_js()
    assert "buildZoneWithProgress" in js
    assert "startZoneBuildProgress" in js
    assert "clearZoneBuildProgress" in js
    assert "applyBuildProgressClasses" in js
    assert "updateBuildProgressBar" in js
    assert "setZoneBuildRunning" in js
    assert "setZoneBuildDone" in js
    assert "/plan" in js
    assert "/complete" in js
    assert "zoneBuild" in js
    assert "build-pending" in js
    assert "build-running" in js
    assert "build-done" in js
    assert "build-idle" in js


def _seed_zone_pipe(pipe: Path, *, renatus_mode: str = "root_to_leaves") -> None:
    pipe.mkdir(parents=True, exist_ok=True)
    (pipe / "default").mkdir(exist_ok=True)
    (pipe / "default.yaml").write_text(
        yaml.dump(
            {
                "default": {
                    "type": "zone",
                    "label": "default",
                    "objects": {},
                    "workers": "queue",
                    "renatus_mode": renatus_mode,
                }
            }
        ),
        encoding="utf-8",
    )
    for sid, script, reqs in (
        ("t_a", "SELECT 1 AS n", []),
        ("v_b", "SELECT n FROM t_a", ["t_a"]),
        ("t_c", "SELECT 3 AS n", []),
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


def test_zone_build_plan_endpoint(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed_zone_pipe(pipe, renatus_mode="root_to_leaves")
    client = TestClient(create_gui_app(tmp_path / "p.duckdb", pipe))
    with client:
        r = client.get("/gui/build/default/plan")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("zone_id") == "default"
        jobs = body.get("jobs") or []
        assert body.get("total") == len(jobs)
        assert len(jobs) >= 2
        ids = [j["id"] for j in jobs]
        # root_to_leaves: tous les membres
        assert "t_a" in ids
        assert "v_b" in ids
        assert "t_c" in ids
        # ordre: requires avant dependents (topo)
        assert ids.index("t_a") < ids.index("v_b")
        for j in jobs:
            assert "index" in j
            assert "label" in j
            assert "line" in j


def test_zone_build_plan_leaves_mode(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed_zone_pipe(pipe, renatus_mode="required_for_leaves")
    client = TestClient(create_gui_app(tmp_path / "q.duckdb", pipe))
    with client:
        body = client.get("/gui/build/default/plan").json()
        jobs = body.get("jobs") or []
        ids = [j["id"] for j in jobs]
        # leaves + requires: v_b leaf (needs t_a), t_c leaf
        assert "v_b" in ids
        assert "t_c" in ids
        assert "t_a" in ids  # require de v_b


def test_non_zone_plan_single_job(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed_zone_pipe(pipe)
    client = TestClient(create_gui_app(tmp_path / "r.duckdb", pipe))
    with client:
        body = client.get("/gui/build/t_a/plan").json()
        assert body.get("ok") is True
        assert body.get("total") == 1
        assert (body.get("jobs") or [])[0]["id"] == "t_a"


def test_zone_build_complete_after_orchestrated_jobs(tmp_path: Path):
    """Simule le flux F0118: plan → jobs individuels → complete."""
    pipe = tmp_path / "flow"
    _seed_zone_pipe(pipe, renatus_mode="root_to_leaves")
    client = TestClient(create_gui_app(tmp_path / "s.duckdb", pipe))
    with client:
        plan = client.get("/gui/build/default/plan").json()
        jobs = plan.get("jobs") or []
        assert jobs
        built = []
        errors = []
        for j in jobs:
            br = client.post(f"/gui/build/{j['id']}")
            assert br.status_code == 200, br.text
            b = br.json()
            entry = {
                "id": j["id"],
                "ok": b.get("ok") is not False,
                "action": b.get("action"),
                "message": b.get("message"),
                "label": j.get("label") or j["id"],
                "line": j.get("line"),
                "renatus_time": b.get("renatus_time"),
            }
            built.append(entry)
            if not entry["ok"]:
                errors.append({"id": j["id"], "error": entry["message"]})

        done = client.post(
            "/gui/build/default/complete",
            json={"elapsed": 1.23, "built": built, "errors": errors},
        )
        assert done.status_code == 200, done.text
        body = done.json()
        assert body.get("action") == "zone_build"
        assert body.get("ok") is True
        assert body.get("orchestrated") is True
        assert body.get("renatus_time") == 1.23
        times = body.get("member_renatus_times") or {}
        assert "t_a" in times
        assert "v_b" in times
        # zone time exposed via get_step
        assert client.get("/gui/step/default").json().get("renatus_time") == 1.23
        assert client.get("/gui/step/t_a").json().get("renatus_time") is not None
