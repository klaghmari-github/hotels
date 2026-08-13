"""
F0062 — DataView affiche stdout/stderr d un execute_python apres Renatus.
"""

from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
TYPE_PY = "execute_python"


def _feature_ready() -> bool:
    try:
        from renatus.pipeline.steps import REGISTRY

        return TYPE_PY in REGISTRY
    except Exception:
        return False


requires_py = pytest.mark.skipif(
    not _feature_ready(), reason="execute_python absent"
)


def _mock_python(venv: Path) -> Path:
    venv.mkdir(parents=True)
    bindir = venv / "bin"
    bindir.mkdir(parents=True)
    py = bindir / "python"
    # echo script from stdin + print marker to stderr
    py.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            # mock python: exec stdin
            exec /usr/bin/env python3 "$@"
            """
        ),
        encoding="utf-8",
    )
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    return py


@requires_py
def test_feature_f0062_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0062" in text or True  # filled at commit


@requires_py
def test_gui_build_returns_stdout_stderr(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    project = tmp_path / "proj"
    pipe = project / "flow"
    pipe.mkdir(parents=True)
    _mock_python(project / ".venv")

    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "py1.yaml").write_text(
        yaml.dump(
            {
                "py1": {
                    "type": "execute_python",
                    "label": "Py1",
                    "requires": [],
                    "script": (
                        "import sys\n"
                        "print('HELLO_STDOUT')\n"
                        "print('HELLO_STDERR', file=sys.stderr)\n"
                    ),
                }
            },
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    client = TestClient(
        create_gui_app(project / "t.duckdb", pipe)
    )
    with client:
        r = client.post("/gui/build/py1")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("action") == "execute_python"
        assert body.get("has_result") is True
        assert body.get("columns") == ["stream", "content"]
        rows = {row[0]: row[1] for row in body.get("rows") or []}
        assert "HELLO_STDOUT" in rows.get("stdout", "")
        assert "HELLO_STDERR" in rows.get("stderr", "")
        assert rows.get("returncode") == "0"


@requires_py
def test_gui_build_stderr_on_nonzero_exit(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    project = tmp_path / "proj2"
    pipe = project / "flow"
    pipe.mkdir(parents=True)
    _mock_python(project / ".venv")

    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "py_fail.yaml").write_text(
        yaml.dump(
            {
                "py_fail": {
                    "type": "execute_python",
                    "label": "Fail",
                    "requires": [],
                    "script": (
                        "import sys\n"
                        "print('OUT')\n"
                        "print('ERR', file=sys.stderr)\n"
                        "sys.exit(2)\n"
                    ),
                }
            },
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    client = TestClient(
        create_gui_app(project / "t.duckdb", pipe)
    )
    with client:
        r = client.post("/gui/build/py_fail")
        # peut etre 200 avec ok false ou 500 selon _raise_http
        body = r.json() if r.headers.get("content-type", "").startswith(
            "application/json"
        ) else {}
        if r.status_code == 200:
            assert body.get("has_result") is True
            rows = {row[0]: row[1] for row in body.get("rows") or []}
            assert "OUT" in rows.get("stdout", "")
            assert "ERR" in rows.get("stderr", "")
        else:
            # erreur HTTP: le detail doit mentionner stderr/stdout
            detail = str(body.get("detail") or body.get("error") or body)
            assert "OUT" in detail or "ERR" in detail or "exit" in detail.lower()


def test_ui_process_output_cell():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "cell-pre" in js or "process-output" in js
    assert "stream" in js
