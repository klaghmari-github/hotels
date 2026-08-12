"""A0014 — Renatus View met a jour schema / shape / renatus_time en Config."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js

REPO = Path(__file__).resolve().parents[1]


def test_anomaly_a0014_registered():
    text = (REPO / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0014" in text


def test_js_refreshes_calculated_after_dataview_build():
    js = read_all_js()
    assert "refreshCalculatedConfigFields" in js
    assert "renderSchema" in js
    assert "renderShape" in js
    assert "renderRenatusTime" in js


def test_preview_build_records_renatus_time_and_schema(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    csv = tmp_path / "sales.csv"
    csv.write_text("id,amount\n1,10\n2,20\n3,30\n", encoding="utf-8")
    client = TestClient(create_gui_app(tmp_path / "t.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "df1",
                    "config": {
                        "type": "dataframe",
                        "label": "df1",
                        "name": "df1",
                        "file": str(csv),
                    },
                },
            ).status_code
            == 200
        )
        # avant build: pas de schema / time
        st0 = client.get("/gui/step/df1").json()
        assert st0.get("schema") in ([], None) or st0.get("schema_count", 0) == 0
        assert st0.get("renatus_time") is None

        prev = client.get("/gui/preview/df1?limit=3&build=true")
        assert prev.status_code == 200, prev.text
        body = prev.json()
        assert body.get("ok") is not False
        assert body.get("renatus_time") is not None
        assert body["renatus_time"] >= 0
        assert body.get("columns") or body.get("has_result")

        st = client.get("/gui/step/df1").json()
        assert st.get("renatus_time") is not None
        assert st["renatus_time"] >= 0
        schema = st.get("schema") or []
        assert len(schema) >= 2
        names = {c["name"] for c in schema}
        assert "id" in names and "amount" in names
        shape = st.get("shape")
        assert shape is not None
        assert shape[0] == 3
        assert shape[1] == 2
