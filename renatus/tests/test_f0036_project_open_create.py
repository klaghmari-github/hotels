"""
F0036 — ouvrir / creer un projet via chemin + branchements db/pipelines.

- Inspect: existing vs new
- Create: .renatus.yaml + db + pipelines + git
- Open: charge infos du fichier projet
- UI: zones style dropzone
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


def test_feature_f0036_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0036" in features


def test_ui_project_open_create_zones():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-testid="project-path-zone"' in html
    assert 'data-testid="project-db-zone"' in html
    assert 'data-testid="project-pipe-zone"' in html
    assert 'data-testid="project-existing-panel"' in html
    assert 'data-testid="project-new-panel"' in html
    assert 'data-testid="project-create-name"' in html
    assert 'data-testid="btn-project-open"' in html

    js = read_all_js()
    assert "/gui/project/inspect" in js
    assert "/gui/project/create" in js
    assert "applyProjectInspect" in js
    assert "inspectProjectPathNow" in js

    css = CSS.read_text(encoding="utf-8")
    assert "path-zone" in css
    assert "project-meta-card" in css


def test_find_and_resolve_project_helpers(tmp_path: Path):
    from renatus.pipeline.project import (
        RenatusProject,
        find_project_file,
        resolve_project_target,
    )

    root = tmp_path / "demo"
    (root / "flow").mkdir(parents=True)
    db = root / "demo.duckdb"
    proj = RenatusProject.from_workspace(db, root / "flow", name="demo")
    pf = root / "demo.renatus.yaml"
    proj.save(pf)

    assert find_project_file(root) == pf.resolve()
    assert find_project_file(pf) == pf.resolve()
    assert find_project_file(tmp_path / "missing_dir") is None

    # nouveau dossier
    pf2, r2 = resolve_project_target(tmp_path / "brand_new")
    assert r2.name == "brand_new"
    assert pf2.name.endswith(".renatus.yaml")


def test_gui_inspect_create_open(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    # workspace bootstrap minimal
    boot_pipe = tmp_path / "boot_pipelines"
    boot_pipe.mkdir()
    boot_db = tmp_path / "boot.duckdb"
    client = TestClient(create_gui_app(boot_db, boot_pipe))

    new_root = tmp_path / "mon_projet"
    with client:
        # inspect new
        r = client.post(
            "/gui/project/inspect",
            json={"path": str(new_root)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["kind"] == "new"
        assert body["suggested_db_path"]
        assert body["suggested_pipeline_path"]
        assert "flow" in body["suggested_pipeline_path"]

        # create
        r2 = client.post(
            "/gui/project/create",
            json={
                "path": str(new_root),
                "name": "mon_projet",
                "db_path": body["suggested_db_path"],
                "pipeline_path": body["suggested_pipeline_path"],
            },
        )
        assert r2.status_code == 200, r2.text
        created = r2.json()
        assert created["ok"] is True
        assert created.get("created") is True
        assert Path(created["project_file"]).is_file()
        assert Path(created["pipeline_path"]).is_dir()
        assert (new_root / ".git").is_dir() or (
            Path(created["project_file"]).parent / ".git"
        ).is_dir()

        raw = yaml.safe_load(
            Path(created["project_file"]).read_text(encoding="utf-8")
        )
        assert raw["name"] == "mon_projet"
        assert "db_path" in raw
        assert "pipeline_path" in raw

        # inspect existing
        r3 = client.post(
            "/gui/project/inspect",
            json={"path": str(new_root)},
        )
        assert r3.status_code == 200
        ex = r3.json()
        assert ex["kind"] == "existing"
        assert ex["name"] == "mon_projet"

        # create again fails
        r4 = client.post(
            "/gui/project/create",
            json={"path": str(new_root), "name": "x"},
        )
        assert r4.status_code in (400, 500)

        # open via dossier
        r5 = client.post(
            "/gui/project/open",
            json={"path": str(new_root)},
        )
        assert r5.status_code == 200, r5.text
        assert r5.json()["project_name"] == "mon_projet" or r5.json().get(
            "name"
        ) == "mon_projet" or "mon_projet" in str(r5.json())

        # open via fichier
        r6 = client.post(
            "/gui/project/open",
            json={"path": created["project_file"]},
        )
        assert r6.status_code == 200, r6.text


def test_create_with_external_db_and_internal_pipe(tmp_path: Path):
    """F0043: db hors projet OK ; pipelines hors projet refuse."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    boot = tmp_path / "b_pipe"
    boot.mkdir()
    client = TestClient(
        create_gui_app(tmp_path / "b.duckdb", boot)
    )
    root = tmp_path / "custom"
    db = tmp_path / "elsewhere" / "data.duckdb"
    pipe_outside = tmp_path / "elsewhere" / "pipes"
    with client:
        # pipelines hors projet → erreur
        r_bad = client.post(
            "/gui/project/create",
            json={
                "path": str(root),
                "name": "custom",
                "db_path": str(db),
                "pipeline_path": str(pipe_outside),
            },
        )
        assert r_bad.status_code in (400, 500), r_bad.text

        # db externe + pipelines dans le projet OK
        r = client.post(
            "/gui/project/create",
            json={
                "path": str(root),
                "name": "custom",
                "db_path": str(db),
                "pipeline_path": "flow",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert Path(body["db_path"]).resolve() == db.resolve()
        assert Path(body["pipeline_path"]).resolve() == (
            root / "flow"
        ).resolve()
        assert (root / "flow").is_dir()
        assert body.get("db_external") is True
        assert body.get("pipelines_inside_project") is True
