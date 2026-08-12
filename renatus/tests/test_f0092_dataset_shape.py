"""F0092 — shape calcule [rows, cols] pour dataframe/table/view."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0092_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0092" in text


def test_ui_shape_field_present():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="field-shape"' in html
    assert 'data-testid="cfg-shape"' in html
    js = read_all_js()
    assert "renderShape" in js
    assert "data.shape" in js


def test_shape_null_before_build_then_rows_cols(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "a.csv").write_text("id,name\n1,a\n2,b\n3,c\n", encoding="utf-8")

    client = TestClient(create_gui_app(tmp_path / "sh.duckdb", pipe))
    with client:
        assert (
            client.post(
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
            ).status_code
            == 200
        )
        st0 = client.get("/gui/step/df1").json()
        assert st0.get("shape") is None
        assert "shape" not in (st0.get("config") or {})

        assert client.post("/gui/build/df1?limit=10").status_code == 200
        st = client.get("/gui/step/df1").json()
        shape = st.get("shape")
        assert shape == [3, 2], shape
        assert st.get("schema_count") == 2

        # put ne stocke pas shape (dataframe register est session; reload = rebuild)
        client.put(
            "/gui/step/df1",
            json={
                "config": {
                    "type": "dataframe",
                    "label": "df1",
                    "name": "df1",
                    "file": "input/a.csv",
                    "shape": [9, 9],
                }
            },
        )
        raw = yaml.safe_load(
            (pipe / "default" / "df1.yaml").read_text(encoding="utf-8")
        )
        assert "shape" not in raw["df1"]
        # apres put, rebuild pour re-materialiser puis shape a jour
        assert client.post("/gui/build/df1").status_code == 200
        st2 = client.get("/gui/step/df1").json()
        assert st2.get("shape") == [3, 2]


def test_table_shape_after_build(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "t.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "t1",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS a, 'x' AS b UNION ALL SELECT 2, 'y'",
                },
            },
        )
        assert client.post("/gui/build/t1").status_code == 200
        st = client.get("/gui/step/t1").json()
        assert st.get("shape") == [2, 2]
