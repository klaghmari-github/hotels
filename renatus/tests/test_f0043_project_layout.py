"""
F0043 — layout projet : pipelines dans git, donnees referencees hors workspace.

- .renatus.yaml stocke db_path + pipeline_path
- pipeline_path doit etre sous le root projet
- db_path peut etre hors projet (prive)
- gitignore ignore *.duckdb et input/
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0043_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0043" in features


def test_ensure_pipelines_inside_project_helper(tmp_path: Path):
    from renatus.pipeline.project import (
        ensure_pipelines_inside_project,
        is_under_directory,
    )

    root = tmp_path / "proj"
    root.mkdir()
    assert ensure_pipelines_inside_project(root, None) == (
        root / "flow"
    ).resolve()
    assert ensure_pipelines_inside_project(root, "flow/etl") == (
        root / "flow" / "etl"
    ).resolve()
    outside = tmp_path / "other" / "pipes"
    try:
        ensure_pipelines_inside_project(root, outside)
        raise AssertionError("devait lever ValueError")
    except ValueError as e:
        assert "interieur" in str(e).lower() or "projet" in str(e).lower()
    assert is_under_directory(root / "flow", root)
    assert not is_under_directory(outside, root)


def test_create_stores_connection_and_forces_pipelines(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app
    from renatus.pipeline.project_git import ProjectGit

    boot = tmp_path / "boot_p"
    boot.mkdir()
    client = TestClient(create_gui_app(tmp_path / "boot.duckdb", boot))
    root = tmp_path / "myproj"
    external_db = tmp_path / "secret" / "warehouse.duckdb"
    with client:
        r = client.post(
            "/gui/project/create",
            json={
                "path": str(root),
                "name": "myproj",
                "db_path": str(external_db),
                "pipeline_path": "flow",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        pf = Path(body["project_file"])
        assert pf.is_file()
        raw = yaml.safe_load(pf.read_text(encoding="utf-8"))
        assert raw["name"] == "myproj"
        assert "db_path" in raw
        assert "pipeline_path" in raw
        # pipeline relatif sous le projet
        assert not Path(raw["pipeline_path"]).is_absolute() or (
            root.resolve() in Path(body["pipeline_path"]).resolve().parents
            or Path(body["pipeline_path"]).resolve() == (root / "flow").resolve()
        )
        assert Path(body["pipeline_path"]).resolve() == (
            root / "flow"
        ).resolve()
        # db externe stocke (souvent absolu)
        assert Path(body["db_path"]).resolve() == external_db.resolve()
        assert body.get("db_external") is True
        # git present, duckdb ignore
        git = ProjectGit(root)
        assert git.is_repo()
        gi = (root / ".gitignore").read_text(encoding="utf-8")
        assert "*.duckdb" in gi
        assert "input/" in gi


def test_docs_mention_project_layout():
    gui = (REPO / "doc" / "GUI.md").read_text(encoding="utf-8")
    assert "F0043" in gui or "flow" in gui.lower()
    assert "prive" in gui.lower() or "hors" in gui.lower()
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "flow" in readme.lower()
    assert ".renatus.yaml" in readme
    core = (REPO / "doc" / "CORE.md").read_text(encoding="utf-8")
    assert "renatus.yaml" in core or "F0043" in core


def test_ui_project_zones_wording():
    html = (
        REPO / "src" / "renatus" / "gui" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    # F0066: wording projet epure — zones + champs restent
    assert 'data-testid="project-pipe-zone"' in html
    assert 'data-testid="project-db-zone"' in html
    assert "Pipelines" in html or "flow" in html
