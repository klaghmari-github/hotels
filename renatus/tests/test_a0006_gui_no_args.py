"""
A0006 — renatus-gui sans argument ne doit plus planter.

Comportement attendu (F0069):
  - renatus-gui (0 arg) → workspaces/ws_main/proj_main/
  - chemins crees si absents
  - message Info clair
  - warnings pandas numexpr/bottleneck filtres au demarrage
  - un seul .renatus.yaml dans cwd est detecte automatiquement
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_resolve_zero_args_default_workspace(tmp_path: Path, monkeypatch):
    from renatus.gui.server import (
        DEFAULT_PROJECT_ROOT,
        resolve_startup_paths,
    )

    monkeypatch.chdir(tmp_path)
    db, pipe, proj, note = resolve_startup_paths(
        [],
        None,
        read_only=False,
        create=True,
        cwd=tmp_path,
    )
    # F0069: projet defaut cree sous workspaces/ws_main/proj_main
    assert db.name == "main.duckdb"
    assert "workspaces" in str(db)
    assert "ws_main" in str(db)
    assert "proj_main" in str(db)
    assert pipe.name == "flow"
    assert pipe.is_dir()
    assert (tmp_path / DEFAULT_PROJECT_ROOT).is_dir()
    assert note is not None
    assert "defaut" in note.lower() or "default" in note.lower() or "proj" in note
    # fichier projet present
    assert proj is not None
    assert proj.name == "proj_main"
    assert (tmp_path / DEFAULT_PROJECT_ROOT / "proj_main.renatus.yaml").is_file()


def test_resolve_zero_args_auto_project_file(tmp_path: Path):
    from renatus.pipeline.project import RenatusProject
    from renatus.gui.server import resolve_startup_paths

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "app.duckdb"
    proj_path = tmp_path / "auto.renatus.yaml"
    RenatusProject.from_workspace(db, pipe, name="auto").save(proj_path)

    db2, pipe2, proj, note = resolve_startup_paths(
        [],
        None,
        read_only=False,
        create=True,
        cwd=tmp_path,
    )
    assert proj is not None
    assert proj.name == "auto"
    assert Path(db2).resolve() == db.resolve()
    assert Path(pipe2).resolve() == pipe.resolve()
    assert note is not None
    assert "detecte" in note.lower() or "auto" in note.lower()


def test_resolve_single_duckdb(tmp_path: Path):
    from renatus.gui.server import resolve_startup_paths

    db = tmp_path / "solo.duckdb"
    db_out, pipe_out, proj, note = resolve_startup_paths(
        [str(db)],
        None,
        read_only=False,
        create=True,
        cwd=tmp_path,
    )
    assert proj is None
    assert db_out.name == "solo.duckdb"
    assert pipe_out == (tmp_path / "flow").resolve() or pipe_out.name == "flow"
    assert note is not None


def test_pandas_warnings_filtered_on_gui_import():
    """F0046: import renatus-gui ne doit pas spammer numexpr/bottleneck."""
    import subprocess
    import sys

    code = (
        "import renatus.gui.server as s; "
        "print('main', callable(s.main))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env={
            **dict(__import__("os").environ),
            "PYTHONPATH": str(
                Path(__file__).resolve().parents[1] / "src"
            ),
        },
    )
    err = proc.stderr or ""
    assert proc.returncode == 0, err
    assert "numexpr" not in err.lower()
    assert "bottleneck" not in err.lower()
    assert "main True" in (proc.stdout or "")


def test_resolve_two_args_still_works(tmp_path: Path):
    from renatus.gui.server import resolve_startup_paths

    db = tmp_path / "a.duckdb"
    pipe = tmp_path / "pipes"
    db_out, pipe_out, proj, note = resolve_startup_paths(
        [str(db), str(pipe)],
        None,
        read_only=False,
        create=True,
        cwd=tmp_path,
    )
    assert proj is None
    assert note is None
    assert pipe_out.is_dir()


def test_main_no_args_starts(tmp_path: Path, monkeypatch, capsys):
    from renatus.gui import server as gui_server

    monkeypatch.chdir(tmp_path)
    called: dict = {}

    def fake_run(app, host, port, log_level="info"):
        called["port"] = port
        called["app"] = app

    monkeypatch.setattr("uvicorn.run", fake_run)
    code = gui_server.main(["--host", "127.0.0.1", "--port", "8877"])
    assert code == 0
    assert called.get("port") == 8877
    root = tmp_path / "workspaces" / "ws_main" / "proj_main"
    assert (root / "flow").is_dir()
    assert root.is_dir()
    assert (root / "proj_main.renatus.yaml").is_file()
    err = capsys.readouterr().err
    assert "Info:" in err or "proj_main" in err or "workspaces" in err
    assert "http://127.0.0.1:8877" in err


def test_main_no_args_help_mentions_default():
    from renatus.gui.server import build_parser

    help_text = build_parser().format_help()
    assert "workspaces" in help_text or "proj_main" in help_text
    assert "Sans argument" in help_text or "Absent" in help_text or "defaut" in help_text


def test_anomaly_a0006_registered():
    root = Path(__file__).resolve().parents[1]
    anomalies = (root / "gestion_projet" / "anomalies.csv").read_text(
        encoding="utf-8"
    )
    assert "A0006" in anomalies
