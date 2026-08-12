"""
F0023 — scenarios de test : graphe de dependances + chaine Excel.

Scenario type (sans iteration) :
  1. dataframe branche sur un fichier Excel (tests/fixtures/f0023/sales_mini.xlsx)
  2. table ou view branchee sur la dataframe (requires)
  3. enchainement table/view : select colonnes, filtre, group by
  4. GET /gui/graph : nodes + edges coherents avec requires
  5. build / preview limit 3

Iteration : hors scope (feature separee).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
FIXTURE_XLSX = REPO / "tests" / "fixtures" / "f0023" / "sales_mini.xlsx"


def _edge_pairs(edges: list[dict]) -> set[tuple[str, str]]:
    return {
        (e.get("from") or e.get("from_"), e["to"])
        for e in edges
    }


def _setup_workspace(tmp_path: Path) -> tuple:
    """GUI sur tmp_path avec input/sales_mini.xlsx (copie fixture)."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    assert FIXTURE_XLSX.is_file(), f"fixture manquante: {FIXTURE_XLSX}"
    pipe = tmp_path / "flow"
    pipe.mkdir()
    inp = tmp_path / "input"
    inp.mkdir()
    dest = inp / "sales_mini.xlsx"
    shutil.copy(FIXTURE_XLSX, dest)
    client = TestClient(create_gui_app(tmp_path / "f0023.duckdb", pipe))
    return client, pipe, dest


def _create_step(client, name: str, config: dict) -> None:
    r = client.post("/gui/steps", json={"name": name, "config": config})
    assert r.status_code == 200, f"create {name}: {r.text}"


def test_fixture_excel_exists_and_readable():
    """Le fichier Excel de test est versionne et lisible (openpyxl/pandas)."""
    assert FIXTURE_XLSX.is_file()
    assert FIXTURE_XLSX.stat().st_size > 100
    import pandas as pd

    df = pd.read_excel(FIXTURE_XLSX)
    assert list(df.columns) == ["id", "region", "product", "qty", "price"]
    assert len(df) >= 5
    assert set(df["region"]) >= {"EU", "US", "ASIA"}


def test_feature_f0023_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0023" in features
    assert "sales_mini.xlsx" in features or "f0023" in features.lower()


def test_scenario_df_xlsx_to_table_graph_and_build(tmp_path: Path):
    """
    Scenario A:
      df_sales (excel) → t_sales (SELECT *)
    Verifie edges graphe + build + preview limit 3.
    """
    client, pipe, _ = _setup_workspace(tmp_path)
    with client:
        _create_step(
            client,
            "df_sales",
            {"type": "dataframe", "file": "input/sales_mini.xlsx"},
        )
        _create_step(
            client,
            "t_sales",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_sales"],
                "sql": "SELECT * FROM df_sales ORDER BY id",
            },
        )

        g = client.get("/gui/graph").json()
        assert g["ok"] is True
        ids = {n["id"] for n in g["nodes"]}
        assert ids == {"df_sales", "t_sales"}
        types = {n["id"]: n["type"] for n in g["nodes"]}
        assert types["df_sales"] == "dataframe"
        assert types["t_sales"] == "table"
        assert ("df_sales", "t_sales") in _edge_pairs(g["edges"])

        # build table (lineage inclut dataframe excel)
        b = client.post("/gui/build/t_sales?limit=3")
        assert b.status_code == 200, b.text
        body = b.json()
        assert body["ok"] is True
        assert body["has_result"] is True
        assert body["row_count"] == 3
        assert set(body["columns"]) >= {"id", "region", "product", "qty", "price"}
        assert len(body["rows"]) == 3

        prev = client.get("/gui/preview/t_sales?limit=3").json()
        assert prev.get("exists") is True
        assert prev.get("row_count") == 3


def test_scenario_df_to_view_select_columns(tmp_path: Path):
    """
    Scenario B:
      df_sales → v_products (SELECT id, product, qty)
    """
    client, _, _ = _setup_workspace(tmp_path)
    with client:
        _create_step(
            client,
            "df_sales",
            {"type": "dataframe", "file": "input/sales_mini.xlsx"},
        )
        _create_step(
            client,
            "v_products",
            {
                "type": "view",
                "mode": "create_or_replace",
                "requires": ["df_sales"],
                "sql": (
                    "SELECT id, product, qty FROM df_sales "
                    "ORDER BY id"
                ),
            },
        )

        g = client.get("/gui/graph").json()
        assert ("df_sales", "v_products") in _edge_pairs(g["edges"])
        types = {n["id"]: n["type"] for n in g["nodes"]}
        assert types["v_products"] == "view"

        b = client.post("/gui/build/v_products?limit=3").json()
        assert b["ok"] is True
        assert b["columns"] == ["id", "product", "qty"]
        assert len(b["rows"]) == 3
        # pas de colonnes region/price dans le select
        assert "region" not in b["columns"]
        assert "price" not in b["columns"]


def test_scenario_filter_region_eu(tmp_path: Path):
    """
    Scenario C:
      df_sales → t_eu (WHERE region = 'EU')
    """
    client, _, _ = _setup_workspace(tmp_path)
    with client:
        _create_step(
            client,
            "df_sales",
            {"type": "dataframe", "file": "input/sales_mini.xlsx"},
        )
        _create_step(
            client,
            "t_eu",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_sales"],
                "sql": (
                    "SELECT * FROM df_sales "
                    "WHERE region = 'EU' ORDER BY id"
                ),
            },
        )

        g = client.get("/gui/graph").json()
        assert ("df_sales", "t_eu") in _edge_pairs(g["edges"])

        # build sans limit pour compter toutes les lignes EU
        b = client.post("/gui/build/t_eu?limit=100").json()
        assert b["ok"] is True
        # fixture: EU rows id 1,2,5 → 3 lignes
        assert b["row_count"] == 3
        for row in b["rows"]:
            # columns order: id, region, product, qty, price
            region_idx = b["columns"].index("region")
            assert row[region_idx] == "EU"


def test_scenario_group_by_region(tmp_path: Path):
    """
    Scenario D:
      df_sales → t_by_region (GROUP BY region, SUM qty)
    """
    client, _, _ = _setup_workspace(tmp_path)
    with client:
        _create_step(
            client,
            "df_sales",
            {"type": "dataframe", "file": "input/sales_mini.xlsx"},
        )
        _create_step(
            client,
            "t_by_region",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_sales"],
                "sql": (
                    "SELECT region, SUM(qty) AS total_qty "
                    "FROM df_sales "
                    "GROUP BY region "
                    "ORDER BY region"
                ),
            },
        )

        g = client.get("/gui/graph").json()
        assert ("df_sales", "t_by_region") in _edge_pairs(g["edges"])

        b = client.post("/gui/build/t_by_region?limit=10").json()
        assert b["ok"] is True
        assert b["columns"] == ["region", "total_qty"]
        # 3 regions dans la fixture
        assert b["row_count"] == 3
        by_region = {
            row[0]: row[1] for row in b["rows"]
        }
        # EU: 10+3+4=17, US: 7+2+6=15, ASIA: 15+1=16
        assert by_region["EU"] == 17
        assert by_region["US"] == 15
        assert by_region["ASIA"] == 16


def test_scenario_chain_df_table_view_table(tmp_path: Path):
    """
    Scenario E — chaine longue (visualisation multi-edges):
      df_sales → t_all → v_eu → t_eu_products_agg

    df_sales (excel)
      └─ t_all (SELECT *)
           └─ v_eu (WHERE region='EU')
                └─ t_eu_products_agg (GROUP BY product)

    Verifie le graphe complet + build de la feuille + donnees.
    """
    client, pipe, _ = _setup_workspace(tmp_path)
    with client:
        _create_step(
            client,
            "df_sales",
            {"type": "dataframe", "file": "input/sales_mini.xlsx"},
        )
        _create_step(
            client,
            "t_all",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_sales"],
                "sql": "SELECT * FROM df_sales",
            },
        )
        _create_step(
            client,
            "v_eu",
            {
                "type": "view",
                "mode": "create_or_replace",
                "requires": ["t_all"],
                "sql": "SELECT * FROM t_all WHERE region = 'EU'",
            },
        )
        _create_step(
            client,
            "t_eu_products_agg",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["v_eu"],
                "sql": (
                    "SELECT product, SUM(qty) AS qty_sum, "
                    "COUNT(*) AS n_lines "
                    "FROM v_eu "
                    "GROUP BY product "
                    "ORDER BY product"
                ),
            },
        )

        g = client.get("/gui/graph").json()
        ids = {n["id"] for n in g["nodes"]}
        assert ids == {
            "df_sales",
            "t_all",
            "v_eu",
            "t_eu_products_agg",
        }
        pairs = _edge_pairs(g["edges"])
        assert pairs == {
            ("df_sales", "t_all"),
            ("t_all", "v_eu"),
            ("v_eu", "t_eu_products_agg"),
        }
        # pas d'arete directe df → feuille (lineage via chaine)
        assert ("df_sales", "t_eu_products_agg") not in pairs

        b = client.post(
            "/gui/build/t_eu_products_agg?limit=10"
        ).json()
        assert b["ok"] is True, b
        assert b["columns"] == ["product", "qty_sum", "n_lines"]
        # EU products: A (10+4=14, 2 lines), B (3, 1 line)
        by_prod = {row[0]: (row[1], row[2]) for row in b["rows"]}
        assert by_prod["A"] == (14, 2)
        assert by_prod["B"] == (3, 1)
        assert "C" not in by_prod  # C pas en EU dans fixture

        # preview sources intermediaires apres materialisation
        prev_eu = client.get("/gui/preview/v_eu?limit=3").json()
        assert prev_eu.get("exists") is True
        assert prev_eu.get("row_count") == 3

        # YAML requires persistes pour chaque step
        # (fichiers crees par YamlStepStore)
        yaml_files = list(pipe.rglob("*.yaml"))
        assert yaml_files
        merged: dict = {}
        for f in yaml_files:
            content = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            for k, v in content.items():
                if isinstance(v, dict) and "type" in v:
                    merged[k] = v
                elif k == "type":
                    # format single-step file keyed by filename stem
                    pass
        # store format: {name: config} par fichier name.yaml
        for name in ("t_all", "v_eu", "t_eu_products_agg"):
            # F0082: steps main sous flow/default/
            step_file = pipe / "default" / f"{name}.yaml"
            if not step_file.is_file():
                step_file = pipe / f"{name}.yaml"
            assert step_file.is_file(), name
            cfg = yaml.safe_load(step_file.read_text(encoding="utf-8"))
            # format {name: {...}} ou config plate
            if name in cfg:
                requires = cfg[name].get("requires") or []
            else:
                requires = cfg.get("requires") or []
            assert len(requires) >= 1, name


def test_scenario_multi_requires_diamond(tmp_path: Path):
    """
    Scenario F — deux branches puis jointure (multi-requires):
      df_sales → t_eu
      df_sales → t_us
      t_eu + t_us → v_union (UNION ALL)

    Graphe: 2 edges depuis df_sales, 2 edges vers v_union.
    """
    client, _, _ = _setup_workspace(tmp_path)
    with client:
        _create_step(
            client,
            "df_sales",
            {"type": "dataframe", "file": "input/sales_mini.xlsx"},
        )
        _create_step(
            client,
            "t_eu",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_sales"],
                "sql": "SELECT * FROM df_sales WHERE region = 'EU'",
            },
        )
        _create_step(
            client,
            "t_us",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_sales"],
                "sql": "SELECT * FROM df_sales WHERE region = 'US'",
            },
        )
        _create_step(
            client,
            "v_union",
            {
                "type": "view",
                "mode": "create_or_replace",
                "requires": ["t_eu", "t_us"],
                "sql": (
                    "SELECT * FROM t_eu "
                    "UNION ALL "
                    "SELECT * FROM t_us"
                ),
            },
        )

        g = client.get("/gui/graph").json()
        pairs = _edge_pairs(g["edges"])
        assert ("df_sales", "t_eu") in pairs
        assert ("df_sales", "t_us") in pairs
        assert ("t_eu", "v_union") in pairs
        assert ("t_us", "v_union") in pairs
        # df a 2 enfants
        children = {to for fr, to in pairs if fr == "df_sales"}
        assert children == {"t_eu", "t_us"}

        b = client.post("/gui/build/v_union?limit=20").json()
        assert b["ok"] is True
        # 3 EU + 3 US = 6
        assert b["row_count"] == 6


def test_scenario_put_requires_updates_graph_edges(tmp_path: Path):
    """
    Scenario G — reconfig requires (comme UI multi-select):
      cree table sans requires, puis PUT requires=[df_sales]
      → edge apparait dans le graphe.
    """
    client, _, _ = _setup_workspace(tmp_path)
    with client:
        _create_step(
            client,
            "df_sales",
            {"type": "dataframe", "file": "input/sales_mini.xlsx"},
        )
        _create_step(
            client,
            "t_late",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": "SELECT 1 AS id",
            },
        )
        g0 = client.get("/gui/graph").json()
        assert ("df_sales", "t_late") not in _edge_pairs(g0["edges"])

        r = client.put(
            "/gui/step/t_late",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["df_sales"],
                    "sql": "SELECT * FROM df_sales WHERE qty > 5 ORDER BY id",
                }
            },
        )
        assert r.status_code == 200, r.text

        g1 = client.get("/gui/graph").json()
        assert ("df_sales", "t_late") in _edge_pairs(g1["edges"])

        b = client.post("/gui/build/t_late?limit=20").json()
        assert b["ok"] is True
        # qty > 5: id 1(10), 3(7), 6(15), 8(6) → 4
        assert b["row_count"] == 4


def test_graph_js_renders_edges_and_icons():
    """UI: app.js dessine edges + icones (visualisation dependances)."""
    js = read_all_js()
    assert "renderGraph" in js
    assert "layoutNodes" in js
    assert "class=\"edge\"" in js or "class='edge'" in js or 'class="edge"' in js
    assert "typeIconSvg" in js or "typeIconSvgGroup" in js
    assert "requires" in js
