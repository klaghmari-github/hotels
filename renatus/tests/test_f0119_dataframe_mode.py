"""F0119 — dataframe mode create_if_not_exists / create_or_replace (session)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.pipeline import ConnectionPipeline
from renatus.pipeline.steps.relation import DataframeStep
from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0119_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0119" in text


def test_dataframe_mode_defaults_and_allow_list():
    s = DataframeStep("df1", {"type": "dataframe", "file": "a.csv"})
    assert s.mode == "create_if_not_exists"
    assert s.is_stable_frontier() is True
    cfg = s.to_config()
    assert cfg.get("mode") == "create_if_not_exists"
    assert "mode" in DataframeStep.ALLOWED_CONFIG_KEYS

    s2 = DataframeStep(
        "df2",
        {
            "type": "dataframe",
            "file": "a.csv",
            "mode": "create_or_replace",
        },
    )
    assert s2.mode == "create_or_replace"
    assert s2.is_stable_frontier() is False


def test_ui_dataframe_shows_mode():
    html = read_index()
    assert 'data-for-types="dataframe,table,view"' in html
    js = read_all_js()
    assert "create_if_not_exists" in js
    # DataframeStepType expose mode
    assert "mode: true" in js or 'mode: true' in js
    assert 'mode: "create_if_not_exists"' in js or "create_if_not_exists" in js
    css = read_css()
    # ne plus cacher mode pour dataframe
    assert (
        '.config-form[data-step-type="dataframe"] #field-mode' not in css
        or "dataframe" not in css.split("#field-mode")[0][-80:]
    )
    # defense: execute_* cachent encore mode
    assert 'data-step-type="execute_sql"] #field-mode' in css


def _write_csv(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_create_if_not_exists_reuses_loaded_dataframe(tmp_path: Path):
    """Apres 1er load, 2e process ne relit pas le fichier source."""
    inp = tmp_path / "input"
    src = inp / "data.csv"
    _write_csv(src, "id,n\n1,alice\n")
    pipe = tmp_path / "flow"
    pipe.mkdir()
    # F0101: fichier = id.yaml
    (pipe / "default" / "df_a.yaml").write_text(
        yaml.dump(
            {
                "df_a": {
                    "type": "dataframe",
                    "file": "input/data.csv",
                    "mode": "create_if_not_exists",
                    "name": "df_a",
                }
            }
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(tmp_path / "t.duckdb", pipe, read_only=False)
    try:
        assert cp.should_process("df_a") is True
        cp.process("df_a")
        assert cp.relation_exists("df_a")
        assert cp.should_process("df_a") is False

        # muter le fichier source: ne doit PAS etre relu
        _write_csv(src, "id,n\n9,bob\n")
        # 2e build skip
        cp.process_with_requires("df_a")
        rows = cp.con.execute('SELECT * FROM "df_a"').fetchall()
        assert rows == [(1, "alice")], rows
    finally:
        cp.close()


def test_create_or_replace_rereads_source(tmp_path: Path):
    inp = tmp_path / "input"
    src = inp / "data.csv"
    _write_csv(src, "id,n\n1,alice\n")
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default" / "df_b.yaml").write_text(
        yaml.dump(
            {
                "df_b": {
                    "type": "dataframe",
                    "file": "input/data.csv",
                    "mode": "create_or_replace",
                    "name": "df_b",
                }
            }
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(tmp_path / "u.duckdb", pipe, read_only=False)
    try:
        assert cp.should_process("df_b") is True
        cp.process("df_b")
        assert cp.con.execute('SELECT * FROM "df_b"').fetchall() == [
            (1, "alice")
        ]
        # toujours a reprocesser
        assert cp.should_process("df_b") is True
        _write_csv(src, "id,n\n9,bob\n")
        cp.process("df_b")
        assert cp.con.execute('SELECT * FROM "df_b"').fetchall() == [(9, "bob")]
    finally:
        cp.close()


def test_session_keeps_dataframe_and_table_across_builds(tmp_path: Path):
    """Etat de session: df + table restent disponibles entre builds GUI."""
    inp = tmp_path / "input"
    _write_csv(inp / "s.csv", "x\n1\n2\n")
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "default" / "df_s.yaml").write_text(
        yaml.dump(
            {
                "df_s": {
                    "type": "dataframe",
                    "file": "input/s.csv",
                    "mode": "create_if_not_exists",
                    "name": "df_s",
                }
            }
        ),
        encoding="utf-8",
    )
    (pipe / "default" / "t_s.yaml").write_text(
        yaml.dump(
            {
                "t_s": {
                    "type": "table",
                    "mode": "create_if_not_exists",
                    "requires": ["df_s"],
                    "script": 'SELECT x FROM "df_s"',
                    "name": "t_s",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "sess.duckdb", pipe))
    with client:
        b1 = client.post("/gui/build/df_s")
        assert b1.status_code == 200, b1.text
        assert b1.json().get("ok") is not False
        b2 = client.post("/gui/build/t_s")
        assert b2.status_code == 200, b2.text
        # 2e renatus df: skip (relation deja la)
        b3 = client.post("/gui/build/df_s")
        assert b3.status_code == 200, b3.text
        # table toujours queryable
        r = client.get("/gui/result/t_s?limit=10")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is not False or body.get("rows") is not None
        rows = body.get("rows") or []
        assert len(rows) >= 1

        # put mode sur df + re-build ne casse pas
        step = client.get("/gui/step/df_s").json()
        cfg = dict(step.get("config") or {})
        cfg["mode"] = "create_if_not_exists"
        put = client.put(
            "/gui/step/df_s",
            json={"config": cfg, "yaml": None},
        )
        assert put.status_code == 200, put.text
        got = client.get("/gui/step/df_s").json()["config"]
        assert got.get("mode") == "create_if_not_exists"


def test_gui_tools_catalog_lists_mode_for_dataframe():
    from renatus.pipeline.steps.factory import tools_catalog

    tools = tools_catalog()
    df = next(t for t in tools if t.get("type") == "dataframe" or t.get("id") == "dataframe")
    fields = df.get("fields") or []
    assert "mode" in fields
