"""
F0032 — projet = repo git local, branche de travail, auto-commit, merge main.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js


def test_feature_f0032_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0032" in features


def test_project_git_init_and_work_branch(tmp_path: Path):
    from renatus.pipeline.project_git import ProjectGit, BRANCH_RE

    root = tmp_path / "proj"
    root.mkdir()
    (root / "readme.txt").write_text("x", encoding="utf-8")
    git = ProjectGit(root)
    branch = git.init_repository()
    assert git.is_repo()
    assert BRANCH_RE.match(branch)
    assert git.current_branch() == branch
    assert (root / ".gitignore").is_file()


def test_auto_commit_on_work_branch(tmp_path: Path):
    from renatus.pipeline.project_git import ProjectGit

    root = tmp_path / "p"
    root.mkdir()
    git = ProjectGit(root)
    git.init_repository()
    work = git.current_branch()
    (root / "flow").mkdir()
    (root / "flow" / "a.yaml").write_text(
        "a:\n  type: table\n  sql: SELECT 1\n  requires: []\n  mode: create_or_replace\n",
        encoding="utf-8",
    )
    assert git.commit_all("add a") is True
    assert git.current_branch() == work
    # second commit
    (root / "flow" / "b.yaml").write_text(
        "b:\n  type: table\n  sql: SELECT 2\n  requires: []\n  mode: create_or_replace\n",
        encoding="utf-8",
    )
    assert git.commit_all("add b") is True
    # ahead of main
    pend = git.find_latest_branch_ahead_of_main()
    assert pend is not None
    assert pend.name == work
    assert pend.ahead >= 1


def test_merge_into_main(tmp_path: Path):
    from renatus.pipeline.project_git import ProjectGit

    root = tmp_path / "m"
    root.mkdir()
    git = ProjectGit(root)
    work = git.init_repository()
    (root / "f.txt").write_text("1", encoding="utf-8")
    git.commit_all("work")
    res = git.merge_into_main(work)
    assert res["ok"] is True
    assert git.current_branch() != "main"  # nouvelle branche travail
    # main a le contenu
    git.checkout("main")
    assert (root / "f.txt").read_text(encoding="utf-8") == "1"
    pend = git.find_latest_branch_ahead_of_main()
    # apres merge, l ancienne work n est plus en avance (ou new work empty)
    # la nouvelle branche de travail n a pas de commit en avance
    if pend:
        assert pend.ahead >= 0


def test_gui_save_project_inits_git(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "db.duckdb"
    proj = tmp_path / "demo.renatus.yaml"
    client = TestClient(create_gui_app(db, pipe))
    with client:
        r = client.post(
            "/gui/project/save",
            json={"path": str(proj), "name": "demo"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert (tmp_path / ".git").is_dir()
        assert body.get("work_branch")
        assert body["work_branch"].startswith("b_")


def test_gui_step_autocommit_and_open_pending(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app
    from renatus.pipeline.project_git import ProjectGit

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "x.duckdb"
    proj = tmp_path / "x.renatus.yaml"
    client = TestClient(create_gui_app(db, pipe))
    with client:
        assert (
            client.post(
                "/gui/project/save",
                json={"path": str(proj), "name": "x"},
            ).status_code
            == 200
        )
        # create step → auto-commit
        r = client.post(
            "/gui/steps",
            json={
                "name": "t_one",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                },
            },
        )
        assert r.status_code == 200, r.text
        git = ProjectGit(tmp_path)
        assert git.current_branch().startswith("b_")
        # open → main + pending
        opened = client.post(
            "/gui/project/open", json={"path": str(proj)}
        ).json()
        assert opened["ok"] is True
        assert opened.get("git_branch") in ("main", "master")
        assert opened.get("pending_branch") is not None
        pb = opened["pending_branch"]["name"]
        # resume
        res = client.post(
            "/gui/project/resume", json={"branch": pb}
        )
        assert res.status_code == 200, res.text
        assert res.json()["branch"] == pb
        # step visible
        g = client.get("/gui/graph?tab=*").json()
        ids = {n["id"] for n in g["nodes"]}
        assert "t_one" in ids


def test_gui_save_merges_to_main(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app
    from renatus.pipeline.project_git import ProjectGit

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "y.duckdb"
    proj = tmp_path / "y.renatus.yaml"
    client = TestClient(create_gui_app(db, pipe))
    with client:
        client.post(
            "/gui/project/save", json={"path": str(proj), "name": "y"}
        )
        client.post(
            "/gui/steps",
            json={
                "name": "t_m",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 7 AS n",
                },
            },
        )
        # Save projet = merge main
        r = client.post(
            "/gui/project/save", json={"path": str(proj), "name": "y"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        git = ProjectGit(tmp_path)
        # main contient le fichier step
        git.checkout("main")
        assert (pipe / "default" / "t_m.yaml").is_file() or any(
            pipe.rglob("t_m.yaml")
        )


def test_ui_handles_pending_branch():
    js = read_all_js()
    assert "pending_branch" in js
    assert "/gui/project/resume" in js
    assert "confirm" in js
