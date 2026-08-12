"""
F0026 — sauvegarde / ouverture d un projet renatus (db + pipelines).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js


def test_feature_f0026_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0026" in features
    assert "projet" in features.lower() or "project" in features.lower()


def test_renatus_project_save_load_roundtrip(tmp_path: Path):
    from renatus.pipeline.project import RenatusProject, is_project_file

    db = tmp_path / "data" / "main.duckdb"
    pipe = tmp_path / "flow"
    pipe.mkdir(parents=True)
    db.parent.mkdir(parents=True)

    proj = RenatusProject.from_workspace(
        db, pipe, name="demo_sales", read_only=False
    )
    out = tmp_path / "demo_sales.renatus.yaml"
    written = proj.save(out)
    assert written.is_file()
    assert is_project_file(written)

    raw = yaml.safe_load(written.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["name"] == "demo_sales"
    assert "db_path" in raw
    assert "pipeline_path" in raw
    # chemins relatifs au fichier projet
    assert not Path(raw["db_path"]).is_absolute() or "main.duckdb" in raw["db_path"]

    loaded = RenatusProject.load(written)
    assert loaded.name == "demo_sales"
    assert Path(loaded.db_path).resolve() == db.resolve()
    assert Path(loaded.pipeline_path).resolve() == pipe.resolve()
    assert loaded.read_only is False
    assert loaded.project_file == str(written.resolve())


def test_project_relative_paths_portable(tmp_path: Path):
    """Deplacer le dossier projet: chemins relatifs toujours valides."""
    from renatus.pipeline.project import RenatusProject

    root = tmp_path / "pkg"
    (root / "flow").mkdir(parents=True)
    (root / "db").mkdir()
    db = root / "db" / "app.duckdb"
    pipe = root / "flow"
    proj_file = root / "app.renatus.yaml"

    RenatusProject.from_workspace(db, pipe, name="app").save(proj_file)
    raw = yaml.safe_load(proj_file.read_text(encoding="utf-8"))
    assert raw["db_path"] == "db/app.duckdb" or raw["db_path"].endswith(
        "app.duckdb"
    )

    loaded = RenatusProject.load(proj_file)
    assert Path(loaded.db_path) == db.resolve()
    assert Path(loaded.pipeline_path) == pipe.resolve()


def test_gui_save_and_open_project_api(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "ws.duckdb"
    client = TestClient(create_gui_app(db, pipe))
    proj_path = tmp_path / "mon.renatus.yaml"

    with client:
        # infos projet
        r = client.get("/gui/project")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["db_path"]
        assert body["pipeline_path"]
        assert body["suggested_path"]

        # save
        r2 = client.post(
            "/gui/project/save",
            json={"path": str(proj_path), "name": "mon_projet"},
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["ok"] is True
        assert Path(data["path"]).is_file()
        assert data["name"] == "mon_projet"

        # workspace expose le projet
        ws = client.get("/gui/workspace").json()
        assert ws["project_name"] == "mon_projet"
        assert ws["project_file"]

        # reconnect via open (meme fichier)
        # creer un second workspace puis reouvrir le projet
        other_pipe = tmp_path / "other_pipes"
        other_pipe.mkdir()
        other_db = tmp_path / "other.duckdb"
        client.post(
            "/gui/connect",
            json={
                "db_path": str(other_db),
                "pipeline_path": str(other_pipe),
            },
        )
        ws2 = client.get("/gui/workspace").json()
        assert "other" in ws2["db_label"] or "other" in ws2["db_path"]

        r3 = client.post(
            "/gui/project/open",
            json={"path": str(proj_path)},
        )
        assert r3.status_code == 200, r3.text
        opened = r3.json()
        assert opened["ok"] is True
        assert opened["project_name"] == "mon_projet"
        assert Path(opened["db_path"]).resolve() == db.resolve()
        assert Path(opened["pipeline_path"]).resolve() == pipe.resolve()


def test_gui_server_starts_from_project_file(
    tmp_path: Path, monkeypatch
):
    from renatus.pipeline.project import RenatusProject
    from renatus.gui import server as gui_server

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "main.duckdb"
    proj = tmp_path / "start.renatus.yaml"
    RenatusProject.from_workspace(db, pipe, name="start").save(proj)

    called: dict = {}

    def fake_run(app, host, port, log_level="info"):
        called["port"] = port
        called["app"] = app
        svc = app.state.gui
        called["project_name"] = getattr(svc, "_project_name", None)
        called["db"] = str(svc.api.db_path)

    monkeypatch.setattr("uvicorn.run", fake_run)

    code = gui_server.main(
        [str(proj), "--host", "127.0.0.1", "--port", "8799"]
    )
    assert code == 0
    assert called.get("port") == 8799
    assert called.get("project_name") == "start"
    assert Path(called["db"]).resolve() == db.resolve()


def test_gui_server_project_flag(tmp_path: Path, monkeypatch):
    from renatus.pipeline.project import RenatusProject
    from renatus.gui import server as gui_server

    pipe = tmp_path / "p"
    pipe.mkdir()
    db = tmp_path / "x.duckdb"
    proj = tmp_path / "flag.renatus.yaml"
    RenatusProject.from_workspace(db, pipe, name="flagged").save(proj)

    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)
    code = gui_server.main(
        ["--project", str(proj), "--port", "8801"]
    )
    assert code == 0


def test_ui_has_project_controls():
    html = (
        REPO / "src" / "renatus" / "gui" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert 'data-testid="btn-project-save"' in html
    assert 'data-testid="btn-project-open"' in html
    assert 'data-testid="project-dialog"' in html
    js = read_all_js()
    assert "/gui/project/save" in js
    assert "/gui/project/open" in js


def test_load_missing_project_raises(tmp_path: Path):
    from renatus.pipeline.project import RenatusProject

    with pytest.raises(FileNotFoundError):
        RenatusProject.load(tmp_path / "absent.renatus.yaml")


def test_load_incomplete_project_raises(tmp_path: Path):
    from renatus.pipeline.project import RenatusProject

    bad = tmp_path / "bad.renatus.yaml"
    bad.write_text("name: only\n", encoding="utf-8")
    with pytest.raises(ValueError):
        RenatusProject.load(bad)
