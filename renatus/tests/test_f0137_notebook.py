"""F0137 — composant notebook + editeur session (Jupyter-like)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0137_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0137" in text


def test_notebook_type_in_registry():
    from renatus.pipeline.steps import REGISTRY, allowed_types, tools_catalog

    assert "notebook" in REGISTRY
    assert "notebook" in allowed_types()
    types = {t["type"] for t in tools_catalog()}
    assert "notebook" in types


def test_ui_notebook_dialog_and_type():
    html = read_index()
    assert 'data-testid="notebook-dialog"' in html
    assert 'data-testid="nb-code"' in html
    assert 'data-testid="nb-vars-list"' in html
    assert 'data-testid="nb-btn-run"' in html
    js = read_all_js()
    assert "openNotebookDialog" in js
    assert "NotebookStepType" in js or 'super("notebook")' in js
    assert "/gui/python/session/vars" in js
    assert "/gui/python/session/exec" in js
    assert "F0137" in html or "notebook-dialog" in html


def test_session_vars_and_exec_api(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "default" / "nb1.yaml").write_text(
        yaml.dump(
            {
                "nb1": {
                    "type": "notebook",
                    "label": "nb1",
                    "requires": [],
                    "script": "print(1)\n",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "n.duckdb", pipe))
    with client:
        # peupler la session
        r = client.post(
            "/gui/python/session/exec",
            json={
                "code": "import math\ndf_name = 'hotels'\nx = 3.14\n",
                "step_id": "nb1",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("returncode") == 0
        assert body.get("session") is True
        names = {v["name"] for v in (body.get("vars") or [])}
        assert "x" in names
        assert "df_name" in names
        assert "math" in names

        # vars endpoint
        rv = client.get("/gui/python/session/vars", params={"step_id": "nb1"})
        assert rv.status_code == 200
        names2 = {v["name"] for v in (rv.json().get("vars") or [])}
        assert "x" in names2

        # reutilise variable
        r2 = client.post(
            "/gui/python/session/exec",
            json={"code": "print(df_name, x)\n", "step_id": "nb1"},
        )
        assert r2.status_code == 200
        assert "hotels" in (r2.json().get("stdout") or "")
        assert "3.14" in (r2.json().get("stdout") or "")


def test_notebook_step_process_uses_session(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    project = tmp_path / "p"
    flow = project / "flow"
    flow.mkdir(parents=True)
    (flow / "n1.yaml").write_text(
        yaml.dump(
            {
                "n1": {
                    "type": "notebook",
                    "requires": [],
                    "script": "shared = [1, 2, 3]\n",
                }
            }
        ),
        encoding="utf-8",
    )
    (flow / "n2.yaml").write_text(
        yaml.dump(
            {
                "n2": {
                    "type": "notebook",
                    "requires": ["n1"],
                    "script": "print(sum(shared))\n",
                }
            }
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(project / "db.duckdb"), flow)
    try:
        cp.process_with_requires("n2")
        res = (getattr(cp, "python_run_results", None) or {}).get("n2") or {}
        assert res.get("returncode") == 0
        assert "6" in (res.get("stdout") or "")
    finally:
        cp.close()
