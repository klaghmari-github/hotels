"""
F0048 — attribut name (relation physique) distinct du label (composant).

dataframe / table / view :
  - label = UI
  - name = entite en base (SQL / register)
  - defaut name = label
  - requires reference l id, SQL reference le name
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js


def test_feature_f0048_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0048" in features


def test_ui_name_field_for_dataframe():
    html = (
        REPO / "src" / "renatus" / "gui" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert 'data-testid="cfg-relation-name"' in html
    assert "name-hint" in html or "Name" in html
    js = read_all_js()
    assert 'type === "dataframe"' in js
    assert "fieldRelationName.hidden" in js or "dataframe" in js


def test_dataframe_name_used_for_register(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    pipe = tmp_path / "p"
    pipe.mkdir()
    # mini csv
    csv = tmp_path / "sales.csv"
    csv.write_text("id,amount\n1,10\n2,20\n", encoding="utf-8")
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "df_step.yaml").write_text(
        yaml.dump(
            {
                "df_step": {
                    "type": "dataframe",
                    "label": "df_2026",
                    "name": "df_sales",
                    "file": str(csv),
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "v_step.yaml").write_text(
        yaml.dump(
            {
                "v_step": {
                    "type": "view",
                    "label": "vue_kpi",
                    "name": "v_kpi",
                    "mode": "create_or_replace",
                    "requires": ["df_step"],
                    "sql": "SELECT id, amount * 2 AS amount FROM df_sales",
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(tmp_path / "t.duckdb", pipe)
    try:
        assert cp.relation_name("df_step") == "df_sales"
        assert cp.relation_name("v_step") == "v_kpi"
        cp.process_with_requires("v_step")
        rows = cp.con.sql("SELECT amount FROM v_kpi ORDER BY id").fetchall()
        assert rows == [(20,), (40,)]
    finally:
        cp.close()


def test_gui_persists_name_on_dataframe(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "x.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "dataframe_test",
                "config": {
                    "type": "dataframe",
                    "label": "df_2026",
                    "name": "df_sales",
                    "file": "input/sales.csv",
                },
            },
        )
        assert r.status_code == 200, r.text
        path = pipe / "default" / "dataframe_test.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["dataframe_test"]["label"] == "df_2026"
        assert data["dataframe_test"]["name"] == "df_sales"
        assert data["dataframe_test"]["file"] == "input/sales.csv"

        # default name = label si name omis
        r2 = client.post(
            "/gui/steps",
            json={
                "name": "dataframe_auto",
                "config": {
                    "type": "dataframe",
                    "label": "Mon DF",
                    "file": "input/a.csv",
                },
            },
        )
        assert r2.status_code == 200, r2.text
        data2 = yaml.safe_load(
            (pipe / "default" / "dataframe_auto.yaml").read_text(encoding="utf-8")
        )
        assert data2["dataframe_auto"]["name"] == "Mon DF"


def test_gui_build_view_sql_uses_dataframe_name(tmp_path: Path):
    """
    Scenario utilisateur: df label df_2026, name df_sales ;
    view requires id step ; SQL FROM df_sales.
    """
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "sales.csv").write_text(
        "id,amount\n1,5\n2,15\n", encoding="utf-8"
    )
    # chemin relatif au project_dir = parent de pipelines
    client = TestClient(create_gui_app(tmp_path / "z.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "dataframe_2026_08_08_20_15",
                    "config": {
                        "type": "dataframe",
                        "label": "df_2026",
                        "name": "df_sales",
                        "file": "input/sales.csv",
                    },
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "view_2026_08_08_10_15_20",
                    "config": {
                        "type": "view",
                        "label": "view_kpi",
                        "name": "v_kpi",
                        "mode": "create_or_replace",
                        "requires": ["dataframe_2026_08_08_20_15"],
                        "sql": "SELECT id, amount FROM df_sales",
                    },
                },
            ).status_code
            == 200
        )
        b = client.post("/gui/build/view_2026_08_08_10_15_20?limit=5")
        assert b.status_code == 200, b.text
        body = b.json()
        assert body.get("ok") is True
        assert body.get("row_count", 0) >= 2
        # meta requires expose relation_name SQL
        step = client.get("/gui/step/view_2026_08_08_10_15_20").json()
        # put renvoie requires meta avec relation_name
        put = client.put(
            "/gui/step/view_2026_08_08_10_15_20",
            json={"config": step["config"]},
        )
        assert put.status_code == 200
        reqs = {r["id"]: r for r in put.json().get("requires") or []}
        assert reqs["dataframe_2026_08_08_20_15"]["relation_name"] == "df_sales"


def test_relation_name_fallback_label(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    pipe = tmp_path / "p2"
    pipe.mkdir()
    # F0101: stem = id
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "step_x.yaml").write_text(
        yaml.dump(
            {
                "step_x": {
                    "type": "table",
                    "label": "MaTable",
                    # pas de name → relation_name = label
                    "mode": "create_or_replace",
                    "sql": "SELECT 1 AS n",
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(tmp_path / "y.duckdb", pipe)
    try:
        assert cp.relation_name("step_x") == "MaTable"
    finally:
        cp.close()
