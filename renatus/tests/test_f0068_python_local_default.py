"""
F0068 — execute_python: defaut = python local ; venv optionnel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0068_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0068" in text


def test_resolve_empty_venv_is_sys_executable(tmp_path: Path):
    from renatus.pipeline.steps.python_action import resolve_venv_python

    assert resolve_venv_python(tmp_path, None) == Path(sys.executable).resolve()
    assert resolve_venv_python(tmp_path, "") == Path(sys.executable).resolve()
    assert resolve_venv_python(tmp_path, "   ") == Path(sys.executable).resolve()


def test_resolve_explicit_venv_still_used(tmp_path: Path):
    from renatus.pipeline.steps.python_action import resolve_venv_python

    venv = tmp_path / "myenv"
    bindir = venv / "bin"
    bindir.mkdir(parents=True)
    py = bindir / "python"
    py.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    py.chmod(0o755)
    resolved = resolve_venv_python(tmp_path, "myenv")
    assert resolved == py.resolve()


def test_ui_venv_placeholder_local():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="cfg-venv"' in html
    assert "python local" in html.lower() or "(python local)" in html
    js = read_all_js()
    # venv vide omis du YAML (defaut moteur = local)
    assert "if (venv) config.venv = venv" in js or "config.venv = venv" in js


def test_execute_without_venv_uses_local(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    project = tmp_path / "p"
    pipe = project / "flow"
    pipe.mkdir(parents=True)
    out = project / "ok.txt"
    (pipe / "default" / "py.yaml").write_text(
        yaml.dump(
            {
                "py": {
                    "type": "execute_python",
                    "requires": [],
                    "script": f"open({str(out)!r}, 'w').write('local')\n",
                }
            },
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(project / "db.duckdb"), pipe)
    try:
        cp.process("py")
        result = (getattr(cp, "python_run_results", None) or {}).get("py") or {}
    finally:
        cp.close()
    assert out.read_text(encoding="utf-8") == "local"
    assert Path(result["python"]).resolve() == Path(sys.executable).resolve()
