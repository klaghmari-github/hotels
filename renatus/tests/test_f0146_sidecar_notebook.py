"""F0146 — sidecars .py/.ipynb + notebook multi-cellules + companions."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.gui.yaml_store import YamlStepStore
from renatus.pipeline.steps.source_files import companion_files, parse_ipynb

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0146_registered():
    assert "F0146" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_execute_python_writes_py_sidecar(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "py1",
                "tab": "default",
                "config": {
                    "type": "execute_python",
                    "label": "py1",
                    "requires": [],
                    "script": "print(42)\n",
                },
            },
        )
        assert r.status_code == 200, r.text
        yml = pipe / "default" / "py1.yaml"
        py = pipe / "default" / "py1.py"
        assert yml.is_file()
        assert py.is_file()
        assert "print(42)" in py.read_text(encoding="utf-8")
        body = yaml.safe_load(yml.read_text(encoding="utf-8"))
        # corps non stocke (ou vide) dans le yaml
        assert body["py1"].get("script") in (None, "", "print(42)\n")
        st = client.get("/gui/step/py1").json()
        assert "print(42)" in (st["config"].get("script") or "")
        assert st.get("source_format") == "py"
        assert st.get("source_file", "").endswith("py1.py")


def test_notebook_writes_ipynb_and_cells(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "nb1",
                "tab": "default",
                "config": {
                    "type": "notebook",
                    "label": "nb1",
                    "requires": [],
                    "script": "x = 1\n",
                    "notebook": {
                        "nbformat": 4,
                        "nbformat_minor": 5,
                        "metadata": {},
                        "cells": [
                            {
                                "cell_type": "code",
                                "metadata": {},
                                "source": ["x = 1\n", "print(x)\n"],
                                "outputs": [],
                            },
                            {
                                "cell_type": "code",
                                "metadata": {},
                                "source": ["y = x + 1\n"],
                                "outputs": [],
                            },
                        ],
                    },
                },
            },
        )
        assert r.status_code == 200, r.text
        ipynb = pipe / "default" / "nb1.ipynb"
        assert ipynb.is_file()
        nb = parse_ipynb(ipynb.read_text(encoding="utf-8"))
        assert len(nb["cells"]) == 2
        st = client.get("/gui/step/nb1").json()
        assert st.get("source_format") == "ipynb"
        assert st.get("notebook") is not None
        assert "x = 1" in (st["config"].get("script") or "")


def test_attach_symlinks_companions(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    store = YamlStepStore(pipe)
    store.save_step(
        "obj",
        {
            "type": "execute_python",
            "label": "obj",
            "requires": [],
            "script": "print('hi')\n",
        },
        tab="default",
    )
    master = pipe / "default" / "obj.yaml"
    py = pipe / "default" / "obj.py"
    assert py.is_file()
    store.attach_to_tab("obj", "default/zone_x")
    link_y = pipe / "default" / "zone_x" / "obj.yaml"
    link_p = pipe / "default" / "zone_x" / "obj.py"
    assert link_y.is_symlink()
    assert link_p.is_symlink()
    assert link_p.resolve() == py.resolve()
    comps = companion_files(master)
    assert any(c.name == "obj.py" for c in comps)


def test_ui_notebook_multi_cell():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="nb-cells"' in html
    assert 'data-testid="nb-btn-add-cell"' in html
    js = read_all_js()
    assert "cellsToNotebook" in js or "nbformat" in js
    assert "F0146" in html or "main.js?v=F0146" in html
