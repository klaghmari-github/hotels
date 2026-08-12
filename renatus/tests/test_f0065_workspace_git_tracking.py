"""
F0065 — tracking git auto du workspace (changelogs sans Sauver projet).

- Connect workspace sans .renatus.yaml → init git + fichier projet
- create / update / delete step → commits avec id objet
- GET /gui/changelog → timeline non vide
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from renatus.pipeline.project_git import ProjectGit
from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0065_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0065" in text


def test_connect_auto_inits_git_without_project_file(tmp_path: Path):
    """Workspace defaut-like: pipelines/ + db, sans .renatus.yaml."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "main.duckdb"
    client = TestClient(create_gui_app(db, pipe))
    with client:
        info = client.get("/gui/project").json()
        assert info.get("has_project_file") is True or info.get(
            "project_file"
        )
        assert (tmp_path / ".git").is_dir()
        git = ProjectGit(tmp_path)
        assert git.is_repo()
        assert git.current_branch().startswith("b_") or git.current_branch() in (
            "main",
            "master",
        )
        # fichier projet a la racine (pas sous pipelines)
        yaml_files = list(tmp_path.glob("*.renatus.yaml"))
        assert len(yaml_files) >= 1


def test_step_crud_autocommit_and_changelog(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "w.duckdb"
    client = TestClient(create_gui_app(db, pipe))
    with client:
        # create
        r = client.post(
            "/gui/steps",
            json={
                "name": "obj_alpha",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                    "label": "Alpha",
                },
            },
        )
        assert r.status_code == 200, r.text

        # update
        r2 = client.put(
            "/gui/step/obj_alpha",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 2 AS n",
                    "label": "Alpha",
                }
            },
        )
        assert r2.status_code == 200, r2.text

        # second object then delete
        client.post(
            "/gui/steps",
            json={
                "name": "obj_beta",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 3 AS n",
                },
            },
        )
        deleted = client.delete("/gui/step/obj_beta")
        assert deleted.status_code == 200, deleted.text

        cl = client.get("/gui/changelog?limit=50")
        assert cl.status_code == 200, cl.text
        body = cl.json()
        assert body["ok"] is True
        entries = body["entries"]
        assert len(entries) >= 3
        subjects = " | ".join(e["subject"] for e in entries)
        assert "obj_alpha" in subjects
        assert "obj_beta" in subjects
        assert "create step obj_alpha" in subjects or "create step" in subjects
        assert "delete step obj_beta" in subjects

        git = ProjectGit(tmp_path)
        log = git.global_log(limit=20)
        assert any("obj_alpha" in e["subject"] for e in log)


def test_global_log_includes_all_branches(tmp_path: Path):
    root = tmp_path / "p"
    root.mkdir()
    git = ProjectGit(root)
    work = git.init_repository()
    (root / "a.txt").write_text("1", encoding="utf-8")
    git.commit_all("create step a_id")
    # merge to main then new work — commits work branch still visible with --all
    git.merge_into_main(work)
    git.checkout("main")
    log = git.global_log(limit=20)
    subjects = [e["subject"] for e in log]
    assert any("a_id" in s for s in subjects)
