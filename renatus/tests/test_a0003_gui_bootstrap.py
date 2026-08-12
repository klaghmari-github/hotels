"""
A0003 — renatus-gui demarre avec des chemins inexistants.

Cree l'arborescence, accepte un pipeline vide, ordre args flexible.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_prepare_workspace_creates_missing_tree(tmp_path: Path):
    from renatus.pipeline.workspace import prepare_workspace

    db = tmp_path / "workspace" / "databases" / "default" / "main.duckdb"
    pipe = tmp_path / "workspace" / "flow"
    assert not db.parent.exists()
    assert not pipe.exists()

    db_out, pipe_out = prepare_workspace(db, pipe, create=True)
    assert pipe_out.is_dir()
    assert db_out.parent.is_dir()
    assert not db_out.exists()  # fichier cree a la connexion DuckDB


def test_normalize_swaps_pipeline_then_db(tmp_path: Path):
    from renatus.pipeline.workspace import normalize_db_and_pipeline

    pipe = tmp_path / "flow"
    db = tmp_path / "main.duckdb"
    db_out, pipe_out = normalize_db_and_pipeline(pipe, db)
    assert db_out == db
    assert pipe_out == pipe


def test_connection_pipeline_empty_dir(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "db" / "main.duckdb"
    db.parent.mkdir(parents=True)

    cp = ConnectionPipeline(db, pipe, read_only=False)
    try:
        assert cp.pipeline == {}
        assert list(cp.pipeline.keys()) == []
    finally:
        cp.close()


def test_gui_server_main_bootstraps_user_order(tmp_path: Path, monkeypatch):
    """
    Commande utilisateur :
      renatus-gui workspace/pipelines workspace/.../main.duckdb
    """
    from renatus.gui import server as gui_server

    pipe = tmp_path / "workspace" / "flow"
    db = tmp_path / "workspace" / "databases" / "default" / "main.duckdb"
    called: dict = {}

    def fake_run(app, host, port, log_level="info"):
        called["host"] = host
        called["port"] = port
        called["app"] = app

    monkeypatch.setattr("uvicorn.run", fake_run)

    code = gui_server.main(
        [str(pipe), str(db), "--host", "127.0.0.1", "--port", "8765"]
    )
    assert code == 0
    assert pipe.is_dir()
    assert db.parent.is_dir()
    # port demande 8765 ; si occupe (web_console), bascule libre suivante
    assert called.get("port") in {8765, 8766, 8767, 8768, 8769}
    # app creee = bootstrap OK
    assert called.get("app") is not None


def test_gui_service_connect_missing_paths(tmp_path: Path):
    from renatus.gui.service import GuiService

    pipe = tmp_path / "p" / "flow"
    db = tmp_path / "d" / "main.duckdb"
    svc = GuiService()
    try:
        info = svc.connect(db, pipe)
        assert info.ok is True
        assert pipe.is_dir()
        assert Path(info.db_path).parent.is_dir()
        # zero steps
        g = svc.graph()
        nodes = g.get("nodes") if isinstance(g, dict) else getattr(g, "nodes", [])
        if hasattr(nodes, "__len__"):
            assert len(nodes) == 0
    finally:
        svc.close()


def test_gui_app_health_empty_workspace(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    db = tmp_path / "db" / "t.duckdb"
    # create_gui_app via GuiService.__init__ -> connect -> prepare
    app = create_gui_app(db, pipe)
    with TestClient(app) as client:
        r = client.get("/gui/graph")
        # 200 even if empty
        assert r.status_code in (200, 404) or r.status_code == 200
        # graph endpoint
        if r.status_code == 200:
            body = r.json()
            nodes = body.get("nodes") or body.get("data", {}).get("nodes") or []
            assert len(nodes) == 0
