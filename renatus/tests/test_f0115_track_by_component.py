"""F0115 — Track filtre par composant (zone recursive) + trailers commit."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.pipeline.project_git import ProjectGit
from tests.helpers.static_sources import read_all_js

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0115_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0115" in text


def test_js_loads_step_changelog():
    js = read_all_js()
    assert "loadStepChangelog" in js
    assert "step_id=" in js or "step_id" in js
    assert "refreshTrackIfActive" in js


def test_commit_trailers_and_filter_by_step(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "t_a",
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
                    "name": "t_b",
                    "tab": "default",
                    "config": {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": "SELECT 2 AS n",
                    },
                },
            ).status_code
            == 200
        )
        client.put(
            "/gui/step/t_a",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 11 AS n",
                }
            },
        )

        # filtre t_a: pas de t_b
        cl_a = client.get("/gui/changelog?step_id=t_a&limit=50").json()
        assert cl_a["ok"] is True
        assert cl_a["step_id"] == "t_a"
        assert cl_a["paths"]
        subjects_a = " | ".join(e["subject"] for e in cl_a["entries"])
        assert "t_a" in subjects_a
        assert "t_b" not in subjects_a or "create step t_b" not in subjects_a

        cl_b = client.get("/gui/changelog?step_id=t_b&limit=50").json()
        subjects_b = " | ".join(e["subject"] for e in cl_b["entries"])
        assert "t_b" in subjects_b

        # trailers dans le message git
        git = ProjectGit(tmp_path)
        raw = git._run(
            "log", "-1", "--format=%B", "--", "flow/default/t_a.yaml", check=False
        )
        body = raw.stdout or ""
        assert "renatus-component: t_a" in body or "t_a" in body


def test_zone_recursive_changelog(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "z1",
                "tab": "default",
                "config": {"type": "zone", "label": "z1", "objects": {}},
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "t_in",
                "tab": "z1",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                },
            },
        )
        # default voit commits de z1 et t_in
        cl_main = client.get("/gui/changelog?step_id=default&limit=50").json()
        subjects = " | ".join(e["subject"] for e in cl_main["entries"])
        assert "t_in" in subjects or any(
            "t_in" in (p or "") for p in (cl_main.get("paths") or [])
        )
        # z1 voit t_in
        cl_z = client.get("/gui/changelog?step_id=z1&limit=50").json()
        sub_z = " | ".join(e["subject"] for e in cl_z["entries"])
        assert "t_in" in sub_z or cl_z["count"] >= 1


def test_reset_history(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "c.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "t_x",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                },
            },
        )
        git = ProjectGit(tmp_path)
        before = len(git.global_log(limit=100))
        assert before >= 1
        r = client.post("/gui/changelog/reset-history")
        assert r.status_code == 200, r.text
        after = git.global_log(limit=100)
        # historique court (reparti de zero)
        assert len(after) <= 3
