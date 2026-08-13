"""
F0075 — palette regions + execute_shell.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.pipeline.steps import REGISTRY, create_step, tools_catalog
from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0075_registered():
    assert "F0075" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_registry_has_execute_shell():
    assert "execute_shell" in REGISTRY
    step = create_step(
        "sh1",
        {"type": "execute_shell", "script": "echo ok", "requires": []},
    )
    assert step.type == "execute_shell"


def test_tools_catalog_regions_order():
    cat = tools_catalog()
    types = [t["type"] for t in cat]
    assert types.index("dataframe") < types.index("execute_sql")
    assert types.index("execute_shell") < types.index("iterate")
    assert types.index("execute_sql") < types.index("execute_shell")
    # regions
    by = {t["type"]: t for t in cat}
    assert by["dataframe"].get("region") == "datasets"
    assert by["execute_sql"].get("region") == "execute"
    assert by["execute_shell"].get("region") == "execute"
    assert by["zone"].get("region") == "flow"


def test_execute_shell_runs_and_stdout(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    project = tmp_path / "p"
    pipe = project / "flow"
    pipe.mkdir(parents=True)
    out = project / "marker.txt"
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "sh.yaml").write_text(
        yaml.dump(
            {
                "sh": {
                    "type": "execute_shell",
                    "requires": [],
                    "script": f"echo HELLO_SHELL > {out}\n",
                }
            },
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(project / "db.duckdb"), pipe)
    try:
        cp.process("sh")
        store = getattr(cp, "python_run_results", {}) or {}
        assert "sh" in store
        assert store["sh"]["returncode"] == 0
    finally:
        cp.close()
    assert out.is_file()
    assert "HELLO_SHELL" in out.read_text(encoding="utf-8")


def test_gui_build_shell(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "s.yaml").write_text(
        yaml.dump(
            {
                "s": {
                    "type": "execute_shell",
                    "requires": [],
                    "script": "echo OUT_SHELL; echo ERR_SHELL >&2\n",
                }
            },
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        r = client.post("/gui/build/s")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("action") == "execute_shell"
        assert "OUT_SHELL" in (body.get("stdout") or "")
        assert "ERR_SHELL" in (body.get("stderr") or "")


def test_ui_toolbox_regions_and_shell():
    from tests.helpers.static_sources import read_all_js, read_css, read_index

    html = read_index()
    assert "execute_shell" in html

    js = read_all_js()
    assert "toolbox-region" in js
    assert "execute_shell" in js
    assert "Datasets" in js
    assert "Execute" in js
    assert "Flow" in js
    assert "ExecuteShellStepType" in js or 'super("execute_shell")' in js

    css = read_css()
    assert ".toolbox-region" in css
    assert "execute_shell" in css
