"""F0091 — schema calcule (name + type) pour dataframe/table/view."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0091_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0091" in text


def test_ui_schema_field_present():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="field-schema"' in html
    assert 'data-testid="cfg-schema"' in html
    js = read_all_js()
    assert "renderSchema" in js
    assert "data.schema" in js


def test_get_step_schema_after_build(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    # source csv
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "a.csv").write_text("id,name\n1,alice\n2,bob\n", encoding="utf-8")

    client = TestClient(create_gui_app(tmp_path / "s.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "df1",
                "tab": "default",
                "config": {
                    "type": "dataframe",
                    "label": "df1",
                    "name": "df1",
                    "file": "input/a.csv",
                },
            },
        )
        assert r.status_code == 200, r.text

        # avant build: schema vide
        st0 = client.get("/gui/step/df1").json()
        assert "schema" in st0
        assert st0["schema"] == [] or st0.get("schema_count") == 0
        assert "schema" not in (st0.get("config") or {})

        # build materialise
        b = client.post("/gui/build/df1?limit=3")
        assert b.status_code == 200, b.text

        st = client.get("/gui/step/df1").json()
        schema = st.get("schema") or []
        assert len(schema) >= 2
        names = {c["name"] for c in schema}
        assert "id" in names
        assert "name" in names
        for c in schema:
            assert "type" in c and c["type"]

        # non stocke YAML
        ypath = pipe / "default" / "df1.yaml"
        raw = yaml.safe_load(ypath.read_text(encoding="utf-8"))
        assert "schema" not in raw["df1"]


def test_put_strips_schema(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "s2.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "t1",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                    "schema": [{"name": "fake", "type": "X"}],
                },
            },
        )
        raw = yaml.safe_load(
            (pipe / "default" / "t1.yaml").read_text(encoding="utf-8")
        )
        assert "schema" not in raw["t1"]


def test_execute_has_empty_schema(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "s3.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "x1",
                "config": {
                    "type": "execute_sql",
                    "requires": [],
                    "script": "SELECT 1",
                },
            },
        )
        st = client.get("/gui/step/x1").json()
        assert st.get("schema") == []
