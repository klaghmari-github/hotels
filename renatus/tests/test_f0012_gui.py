"""
F0012 — gui GUI : tools, create step, preview limit 3, labels.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _app(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "main.duckdb"
    app = create_gui_app(db, pipe)
    return TestClient(app), db, pipe


def test_tools_catalog(tmp_path: Path):
    client, _, _ = _app(tmp_path)
    with client:
        r = client.get("/gui/tools")
        assert r.status_code == 200
        tools = r.json()["tools"]
        types = {t["type"] for t in tools}
        assert {"dataframe", "table", "view", "execute_sql", "iterate"} <= types


def test_workspace_labels(tmp_path: Path):
    client, db, pipe = _app(tmp_path)
    with client:
        r = client.get("/gui/workspace")
        assert r.status_code == 200
        body = r.json()
        assert body["db_label"] == "main"
        assert body["pipeline_label"] == "flow"
        assert body["db_path"].endswith("main.duckdb")
        assert "flow" in body["pipeline_path"]


def test_create_dataframe_and_preview_missing(tmp_path: Path):
    client, db, pipe = _app(tmp_path)
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "df_demo",
                "config": {
                    "type": "dataframe",
                    "file": "input/people.csv",
                },
            },
        )
        assert r.status_code == 200, r.text
        assert (pipe / "default" / "df_demo.yaml").is_file()

        g = client.get("/gui/graph").json()
        ids = {n["id"] for n in g["nodes"]}
        assert "df_demo" in ids

        prev = client.get("/gui/preview/df_demo?limit=3").json()
        assert prev.get("exists") is False
        assert prev.get("ok") is True


def test_create_table_chain_and_build_preview(tmp_path: Path):
    """dataframe CSV + table SQL ; build affiche limit 3."""
    client, db, pipe = _app(tmp_path)
    # projet: parent de pipeline = root pour resolve_project_path
    # ConnectionPipeline project_dir = parent of pipeline dir
    root = tmp_path
    inp = root / "input"
    inp.mkdir()
    (inp / "people.csv").write_text("id,name\n1,alice\n2,bob\n3,cara\n4,dan\n", encoding="utf-8")

    with client:
        assert client.post(
            "/gui/steps",
            json={
                "name": "df_people",
                "config": {"type": "dataframe", "file": "input/people.csv"},
            },
        ).status_code == 200
        assert client.post(
            "/gui/steps",
            json={
                "name": "t_people",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["df_people"],
                    "sql": "SELECT * FROM df_people ORDER BY id",
                },
            },
        ).status_code == 200

        g = client.get("/gui/graph").json()
        edges = g["edges"]
        assert any(
            (e.get("from") == "df_people" or e.get("from_") == "df_people")
            and e.get("to") == "t_people"
            for e in edges
        )

        prev = client.get("/gui/preview/t_people?limit=3&build=true").json()
        assert prev.get("ok") is True
        assert prev.get("row_count") == 3
        assert prev.get("columns")
        assert len(prev.get("rows") or []) == 3


def test_static_index_has_toolbox_and_dataview(tmp_path: Path):
    client, _, _ = _app(tmp_path)
    with client:
        r = client.get("/")
        assert r.status_code == 200
        html = r.text
        assert "toolbox" in html
        assert "DataView" in html or "dataview" in html.lower()
        assert "graph-canvas" in html


def test_capture_referenced_in_features_csv():
    root = Path(__file__).resolve().parents[1]
    features = (root / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0012" in features
    assert "captures/F0012_gui_before.png" in features
    cap = root / "gestion_projet" / "agentic" / "captures" / "F0012_gui_before.png"
    assert cap.is_file()
