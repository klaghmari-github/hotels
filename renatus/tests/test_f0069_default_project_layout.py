"""
F0069 — layout par defaut workspaces/ws_main/proj_main.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0069_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0069" in text


def test_default_paths_constants():
    from renatus.gui.server import (
        DEFAULT_DB_REL,
        DEFAULT_PIPE_REL,
        DEFAULT_PROJECT_FILE_REL,
        DEFAULT_PROJECT_ROOT,
    )

    assert DEFAULT_PROJECT_ROOT == Path("workspaces") / "ws_main" / "proj_main"
    assert DEFAULT_DB_REL == DEFAULT_PROJECT_ROOT / "main.duckdb"
    assert DEFAULT_PIPE_REL == DEFAULT_PROJECT_ROOT / "flow"
    assert DEFAULT_PROJECT_FILE_REL.name == "proj_main.renatus.yaml"


def test_creates_missing_tree(tmp_path: Path):
    from renatus.gui.server import resolve_startup_paths

    root = tmp_path / "workspaces" / "ws_main" / "proj_main"
    assert not root.exists()
    db, pipe, proj, note = resolve_startup_paths(
        [],
        None,
        read_only=False,
        create=True,
        cwd=tmp_path,
    )
    assert root.is_dir()
    assert pipe.is_dir()
    assert pipe == (root / "flow").resolve()
    assert db == (root / "main.duckdb").resolve()
    assert (root / "proj_main.renatus.yaml").is_file()
    assert proj is not None
    assert proj.name == "proj_main"
    assert note is not None


def test_default_save_path_under_project_root(tmp_path: Path):
    from renatus.pipeline.project import RenatusProject

    pipe = tmp_path / "workspaces" / "ws_main" / "proj_main" / "flow"
    pipe.mkdir(parents=True)
    db = pipe.parent / "main.duckdb"
    proj = RenatusProject.from_workspace(db, pipe, name="proj_main")
    save = proj.default_save_path()
    assert save.parent == pipe.parent.resolve()
    assert save.name == "proj_main.renatus.yaml"
