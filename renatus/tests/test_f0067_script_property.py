"""
F0067 — property unifiee ``script`` (SQL ou Python) a la place de ``sql``.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.pipeline.steps import create_step, normalize_script_key, script_text
from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0067_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0067" in text


def test_normalize_script_key_migrates_sql():
    out = normalize_script_key(
        {"type": "table", "sql": "SELECT 1", "requires": []}
    )
    assert out.get("script") == "SELECT 1"
    assert "sql" not in out


def test_script_text_accepts_legacy_sql():
    assert script_text({"sql": "SELECT 2"}) == "SELECT 2"
    assert script_text({"script": "print(1)"}) == "print(1)"


def test_execute_step_runs_script_sql(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    pipe = tmp_path / "p"
    pipe.mkdir()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "x.yaml").write_text(
        "x:\n  type: execute\n  requires: []\n  script: SELECT 1\n",
        encoding="utf-8",
    )
    db = tmp_path / "t.duckdb"
    cp = ConnectionPipeline(str(db), pipe)
    try:
        cp.process("x")
    finally:
        cp.close()


def test_legacy_sql_yaml_still_loads(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    pipe = tmp_path / "p"
    pipe.mkdir()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "t.yaml").write_text(
        "t:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  sql: SELECT 9 AS n\n",
        encoding="utf-8",
    )
    db = tmp_path / "t.duckdb"
    cp = ConnectionPipeline(str(db), pipe)
    try:
        assert "script" in cp.pipeline["t"]
        assert "sql" not in cp.pipeline["t"]
        assert cp.pipeline["t"]["script"] == "SELECT 9 AS n"
        cp.process("t")
    finally:
        cp.close()


def test_gui_saves_script_not_sql(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "s.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "t_script",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 3 AS n",  # legacy input still ok
                },
            },
        )
        assert r.status_code == 200, r.text
        data = yaml.safe_load(
            (pipe / "default" / "t_script.yaml").read_text(encoding="utf-8")
        )
        assert "script" in data["t_script"]
        assert "sql" not in data["t_script"]
        assert "SELECT 3" in data["t_script"]["script"]

        g = client.get("/gui/step/t_script").json()
        assert "script" in g["config"]
        assert "sql" not in g["config"]


def test_ui_script_field_unified():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert 'data-testid="field-script"' in html
    assert 'data-testid="cfg-script"' in html
    assert "cfg-sql" not in html or 'id="cfg-script"' in html
    assert ">Script<" in html or "Script" in html
    # plus de champ SQL separe
    assert 'id="cfg-sql"' not in html
    assert 'id="field-sql"' not in html

    js = read_all_js()
    assert "config.script" in js
    # defaults table/execute utilisent script
    assert 'script: "SELECT' in js or "script: 'SELECT" in js


def test_tool_meta_fields_script():
    table = create_step("t", {"type": "table", "script": "SELECT 1"})
    meta = type(table).tool_meta()
    assert "script" in meta["fields"]
    assert "sql" not in meta["fields"]
    exe = create_step("e", {"type": "execute_sql", "script": "SELECT 1"})
    assert "script" in type(exe).tool_meta()["fields"]
