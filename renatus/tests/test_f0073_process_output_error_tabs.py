"""
F0073 — View: sous-onglets Output / Error pour execute_python.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0073_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0073" in text


def test_ui_process_subtabs():
    from tests.helpers.static_sources import read_all_js, read_css, read_index

    html = read_index()
    assert 'data-testid="process-view"' in html
    assert 'data-testid="tab-process-output"' in html
    assert 'data-testid="tab-process-error"' in html
    assert ">Output<" in html
    assert ">Error<" in html
    assert 'data-testid="process-out-stdout"' in html
    assert 'data-testid="process-out-stderr"' in html

    js = read_all_js()
    assert "switchProcessSubTab" in js
    assert "showProcessOutput" in js or "process-out-stdout" in js
    assert "isProcessPayload" in js or "execute_python" in js

    css = read_css()
    assert ".process-view" in css
    assert ".process-subtab" in css
    assert ".process-pane" in css


def test_build_still_returns_stdout_stderr(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default" / "py.yaml").write_text(
        yaml.dump(
            {
                "py": {
                    "type": "execute_python",
                    "requires": [],
                    "script": (
                        "import sys\n"
                        "print('OUT_OK')\n"
                        "print('ERR_OK', file=sys.stderr)\n"
                    ),
                }
            },
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        r = client.post("/gui/build/py")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("action") == "execute_python"
        assert "OUT_OK" in (body.get("stdout") or "")
        assert "ERR_OK" in (body.get("stderr") or "")
        # rows stream still present for compat
        assert body.get("columns") == ["stream", "content"]
