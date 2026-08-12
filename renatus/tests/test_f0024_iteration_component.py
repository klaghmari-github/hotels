"""
F0024 — tests du composant iteration (attributs + fin de parcours).

Concept verifie:
  1. Table de scenarios (donnees d iteration)
  2. step_view (vue temporaire 1 ligne = scenario courant)
  3. Flux target (execute) qui consomme step_view + source
  4. Table d ecriture des resultats (accumulation par tour)
  5. Iteration sequential jusqu au bout
  6. Vue finale branchee sur t_results → prouve le succes

Source: tests/fixtures/f0023/sales_mini.xlsx (ventes multi-regions).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
FIXTURE_XLSX = REPO / "tests" / "fixtures" / "f0023" / "sales_mini.xlsx"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(content, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def _edge_pairs(edges: list[dict]) -> set[tuple[str, str]]:
    return {
        (e.get("from") or e.get("from_"), e["to"])
        for e in edges
    }


def _pipeline_iteration_config() -> dict:
    """
    Pipeline minimal complet pour iteration.

    Graph logique:
      df_sales (excel)
        └─ t_sales
      t_scenarios  (regions a iterer)
      t_results    (sink, create_if_not_exists)
      x_agg        (execute: INSERT depuis v_step + t_sales)
      i_run        (iteration sequential)
      v_final      (view sur t_results — preuve de fin)
    """
    return {
        "df_sales": {
            "type": "dataframe",
            "file": "input/sales_mini.xlsx",
        },
        "t_sales": {
            "type": "table",
            "mode": "create_or_replace",
            "requires": ["df_sales"],
            "sql": "SELECT * FROM df_sales",
        },
        # Table des scenarios d iteration (1 ligne = 1 tour)
        "t_scenarios": {
            "type": "table",
            "mode": "create_or_replace",
            "requires": [],
            "sql": (
                "SELECT * FROM (VALUES "
                "('ASIA'), ('EU'), ('US')"
                ") AS t(region)"
            ),
        },
        # Sink resultats: schema vide, mode create_if_not_exists
        # pour accumuler les INSERT de chaque tour
        "t_results": {
            "type": "table",
            "mode": "create_if_not_exists",
            "requires": [],
            "sql": (
                "SELECT "
                "CAST(NULL AS VARCHAR) AS region, "
                "CAST(NULL AS VARCHAR) AS product, "
                "CAST(NULL AS BIGINT) AS total_qty, "
                "CAST(NULL AS DOUBLE) AS revenue "
                "WHERE 1 = 0"
            ),
        },
        # Flux traite a chaque iteration:
        # filtre t_sales sur region = v_step.region, agregate, INSERT
        # v_step = step_view TEMP (PAS dans requires)
        "x_agg": {
            "type": "execute_sql",
            "requires": ["t_sales", "t_results"],
            "sql": (
                "INSERT INTO t_results "
                "SELECT "
                "  (SELECT region FROM v_step) AS region, "
                "  product, "
                "  SUM(qty) AS total_qty, "
                "  SUM(qty * price) AS revenue "
                "FROM t_sales "
                "WHERE region = (SELECT region FROM v_step) "
                "GROUP BY product"
            ),
        },
        # Composant iteration — tous les attributs cles
        "i_run": {
            "type": "iteration",
            "execution": "sequential",
            "requires": ["t_scenarios", "t_results", "t_sales"],
            "scenarios": "t_scenarios",
            "step_view": "v_step",
            "target": "x_agg",
            "order_by": ["region"],
        },
        # Preuve de fin: vue sur le resultat final de l iteration
        "v_final": {
            "type": "view",
            "mode": "create_or_replace",
            "requires": ["t_results"],
            "sql": (
                "SELECT region, product, total_qty, revenue "
                "FROM t_results "
                "ORDER BY region, product"
            ),
        },
    }


def _prepare_project(tmp_path: Path) -> tuple[Path, Path]:
    """Cree project/pipelines + input/sales_mini.xlsx. Retourne (db, pipe)."""
    assert FIXTURE_XLSX.is_file(), f"fixture manquante: {FIXTURE_XLSX}"
    pipe = tmp_path / "flow"
    pipe.mkdir()
    inp = tmp_path / "input"
    inp.mkdir()
    shutil.copy(FIXTURE_XLSX, inp / "sales_mini.xlsx")
    _write_yaml(pipe / "default" / "pipeline.yaml", _pipeline_iteration_config())
    return tmp_path / "iter.duckdb", pipe


# Totaux attendus depuis sales_mini.xlsx (group by region, product)
# EU: A qty 10+4=14 rev 50+20=70; B qty 3 rev 37.5
# US: A 7/35; B 6/75; C 2/40
# ASIA: B 15/187.5; C 1/20
EXPECTED_FINAL = {
    ("ASIA", "B"): (15, 187.5),
    ("ASIA", "C"): (1, 20.0),
    ("EU", "A"): (14, 70.0),
    ("EU", "B"): (3, 37.5),
    ("US", "A"): (7, 35.0),
    ("US", "B"): (6, 75.0),
    ("US", "C"): (2, 40.0),
}


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


def test_feature_f0024_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0024" in features
    assert "iteration" in features.lower()


def test_fixture_xlsx_available():
    assert FIXTURE_XLSX.is_file()


# ---------------------------------------------------------------------------
# Core engine — attributs + completion
# ---------------------------------------------------------------------------


def test_iteration_config_attributes_present(tmp_path: Path):
    """Tous les attributs iteration sont dans le YAML pipeline."""
    _, pipe = _prepare_project(tmp_path)
    cfg = yaml.safe_load((pipe / "default" / "pipeline.yaml").read_text(encoding="utf-8"))
    i = cfg["i_run"]
    assert i["type"] in ("iterate", "iteration")  # F0093
    assert i["execution"] == "sequential"
    assert i["scenarios"] == "t_scenarios"
    assert i["step_view"] == "v_step"
    assert i["target"] == "x_agg"
    assert i["order_by"] == ["region"]
    assert "t_scenarios" in i["requires"]
    assert "t_results" in i["requires"]
    # step_view ne doit PAS etre une cle pipeline / requires du target
    assert "v_step" not in cfg
    assert "v_step" not in (cfg["x_agg"].get("requires") or [])


def test_iteration_runs_all_scenarios_and_fills_results(tmp_path: Path):
    """
    p_iteration parcourt tous les scenarios et remplit t_results.
    Atteint la fin: 3 regions × produits → 7 lignes attendues.
    """
    from renatus.pipeline import ConnectionPipeline

    db, pipe = _prepare_project(tmp_path)
    cp = ConnectionPipeline(db, pipe)
    try:
        cp.p_iteration("i_run")

        rows = cp.con.execute(
            """
            SELECT region, product, total_qty, revenue
            FROM t_results
            ORDER BY region, product
            """
        ).fetchall()
        assert len(rows) == 7, rows

        got = {
            (r, p): (int(q), float(rev))
            for r, p, q, rev in rows
        }
        assert got == EXPECTED_FINAL

        # L iteration elle-meme n est pas une relation materialisee
        assert not cp.relation_exists("i_run")
    finally:
        cp.close()


def test_final_view_on_results_proves_success(tmp_path: Path):
    """
    Apres iteration, v_final (branchee sur t_results) expose le resultat.
    C est le garde-fou 'on a bien fini et ca a marche'.
    """
    from renatus.pipeline import ConnectionPipeline

    db, pipe = _prepare_project(tmp_path)
    cp = ConnectionPipeline(db, pipe)
    try:
        cp.p_iteration("i_run")
        # Materialise la vue finale (depends de t_results deja remplie)
        cp.process_with_requires("v_final")
        assert cp.relation_exists("v_final")

        rows = cp.con.execute(
            "SELECT region, product, total_qty, revenue "
            "FROM v_final ORDER BY region, product"
        ).fetchall()
        assert len(rows) == 7
        # EU A
        eu_a = [r for r in rows if r[0] == "EU" and r[1] == "A"]
        assert len(eu_a) == 1
        assert eu_a[0][2] == 14
        assert abs(float(eu_a[0][3]) - 70.0) < 1e-6
    finally:
        cp.close()


def test_order_by_attribute_controls_scenario_order(tmp_path: Path):
    """
    order_by: [region] force l ordre ASIA, EU, US (alphabetique).
    On logge via une table d audit l ordre de consommation.
    """
    from renatus.pipeline import ConnectionPipeline

    db, pipe = _prepare_project(tmp_path)
    # Pipeline d audit: INSERT sequence_no + region dans t_order
    cfg = _pipeline_iteration_config()
    cfg["t_order"] = {
        "type": "table",
        "mode": "create_if_not_exists",
        "requires": [],
        "sql": (
            "SELECT CAST(NULL AS INTEGER) AS seq, "
            "CAST(NULL AS VARCHAR) AS region WHERE 1 = 0"
        ),
    }
    cfg["x_agg"] = {
        "type": "execute_sql",
        "requires": ["t_sales", "t_results", "t_order"],
        "sql": (
            "INSERT INTO t_order "
            "SELECT "
            "  (SELECT COUNT(*) + 1 FROM t_order), "
            "  (SELECT region FROM v_step); "
            "INSERT INTO t_results "
            "SELECT "
            "  (SELECT region FROM v_step) AS region, "
            "  product, "
            "  SUM(qty) AS total_qty, "
            "  SUM(qty * price) AS revenue "
            "FROM t_sales "
            "WHERE region = (SELECT region FROM v_step) "
            "GROUP BY product"
        ),
    }
    cfg["i_run"]["requires"] = [
        "t_scenarios",
        "t_results",
        "t_sales",
        "t_order",
    ]
    _write_yaml(pipe / "default" / "pipeline.yaml", cfg)

    cp = ConnectionPipeline(db, pipe)
    try:
        cp.p_iteration("i_run")
        order = [
            r[0]
            for r in cp.con.execute(
                "SELECT region FROM t_order ORDER BY seq"
            ).fetchall()
        ]
        assert order == ["ASIA", "EU", "US"]
    finally:
        cp.close()


def test_step_view_recreated_each_turn(tmp_path: Path):
    """
    A chaque tour, step_view porte la region du scenario courant.
    Verifie via resultats qu on n a pas melange les regions.
    """
    from renatus.pipeline import ConnectionPipeline

    db, pipe = _prepare_project(tmp_path)
    cp = ConnectionPipeline(db, pipe)
    try:
        cp.p_iteration("i_run")
        # Chaque ligne results.region doit etre dans scenarios
        regions = {
            r[0]
            for r in cp.con.execute(
                "SELECT DISTINCT region FROM t_results"
            ).fetchall()
        }
        assert regions == {"ASIA", "EU", "US"}
        # Pas de produit EU attribue a US etc. — check qty EU A
        q = cp.con.execute(
            "SELECT total_qty FROM t_results "
            "WHERE region = 'EU' AND product = 'A'"
        ).fetchone()
        assert q is not None and q[0] == 14
    finally:
        cp.close()


# ---------------------------------------------------------------------------
# GUI API — graphe, build iteration, vue finale
# ---------------------------------------------------------------------------


def test_gui_iteration_graph_edges(tmp_path: Path):
    """GET /gui/graph expose les requires de i_run et v_final."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    db, pipe = _prepare_project(tmp_path)
    client = TestClient(create_gui_app(db, pipe))
    with client:
        g = client.get("/gui/graph").json()
        ids = {n["id"] for n in g["nodes"]}
        assert "i_run" in ids
        assert "v_final" in ids
        assert "t_scenarios" in ids
        types = {n["id"]: n["type"] for n in g["nodes"]}
        assert types["i_run"] in ("iterate", "iteration")  # F0093
        assert types["v_final"] == "view"

        pairs = _edge_pairs(g["edges"])
        # i_run depends de scenarios, results, sales
        assert ("t_scenarios", "i_run") in pairs
        assert ("t_results", "i_run") in pairs
        assert ("t_sales", "i_run") in pairs
        # v_final branchee sur t_results (preuve)
        assert ("t_results", "v_final") in pairs
        # chaine source
        assert ("df_sales", "t_sales") in pairs


def test_gui_build_iteration_then_final_view(tmp_path: Path):
    """
    GUI: Build i_run (p_iteration) puis Build v_final.
    Preview v_final = resultat de fin de parcours.
    """
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    db, pipe = _prepare_project(tmp_path)
    client = TestClient(create_gui_app(db, pipe))
    with client:
        # Build iteration
        r = client.post("/gui/build/i_run")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["action"] == "p_iteration"
        assert body.get("has_result") is False  # iteration ≠ relation

        # Build vue finale (consomme t_results rempli)
        r2 = client.post("/gui/build/v_final?limit=20")
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["ok"] is True
        assert data["has_result"] is True
        assert data["row_count"] == 7
        cols = data["columns"]
        assert cols == ["region", "product", "total_qty", "revenue"]

        # Map rows
        idx_r = cols.index("region")
        idx_p = cols.index("product")
        idx_q = cols.index("total_qty")
        idx_rev = cols.index("revenue")
        got = {
            (row[idx_r], row[idx_p]): (
                int(row[idx_q]),
                float(row[idx_rev]),
            )
            for row in data["rows"]
        }
        assert got == EXPECTED_FINAL

        # Preview aussi
        prev = client.get("/gui/preview/v_final?limit=20").json()
        assert prev.get("exists") is True
        assert prev.get("row_count") == 7


def test_gui_get_step_iteration_attributes(tmp_path: Path):
    """GET /gui/step/i_run renvoie scenarios, step_view, target, order_by."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    db, pipe = _prepare_project(tmp_path)
    client = TestClient(create_gui_app(db, pipe))
    with client:
        r = client.get("/gui/step/i_run")
        assert r.status_code == 200, r.text
        cfg = r.json()["config"]
        assert cfg['type'] in ('iterate', 'iteration')  # F0093
        assert cfg["execution"] == "sequential"
        assert cfg["scenarios"] == "t_scenarios"
        assert cfg["step_view"] == "v_step"
        assert cfg["target"] == "x_agg"
        assert cfg["order_by"] == ["region"]
        assert set(cfg["requires"]) >= {
            "t_scenarios",
            "t_results",
            "t_sales",
        }


def test_gui_create_iteration_steps_from_scratch(tmp_path: Path):
    """
    Creation progressive via API GUI (comme l UI):
    steps + requires, puis build iteration, puis vue finale.
    """
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    assert FIXTURE_XLSX.is_file()
    pipe = tmp_path / "flow"
    pipe.mkdir()
    inp = tmp_path / "input"
    inp.mkdir()
    shutil.copy(FIXTURE_XLSX, inp / "sales_mini.xlsx")
    client = TestClient(
        create_gui_app(tmp_path / "scratch.duckdb", pipe)
    )

    def create(name: str, config: dict) -> None:
        r = client.post(
            "/gui/steps", json={"name": name, "config": config}
        )
        assert r.status_code == 200, f"{name}: {r.text}"

    with client:
        create(
            "df_sales",
            {"type": "dataframe", "file": "input/sales_mini.xlsx"},
        )
        create(
            "t_sales",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_sales"],
                "sql": "SELECT * FROM df_sales",
            },
        )
        create(
            "t_scenarios",
            {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": (
                    "SELECT * FROM (VALUES ('EU'), ('US')) "
                    "AS t(region)"
                ),
            },
        )
        create(
            "t_results",
            {
                "type": "table",
                "mode": "create_if_not_exists",
                "requires": [],
                "sql": (
                    "SELECT CAST(NULL AS VARCHAR) AS region, "
                    "CAST(NULL AS VARCHAR) AS product, "
                    "CAST(NULL AS BIGINT) AS total_qty "
                    "WHERE 1 = 0"
                ),
            },
        )
        create(
            "x_step",
            {
                "type": "execute_sql",
                "requires": ["t_sales", "t_results"],
                "sql": (
                    "INSERT INTO t_results "
                    "SELECT (SELECT region FROM v_step), product, "
                    "SUM(qty) FROM t_sales "
                    "WHERE region = (SELECT region FROM v_step) "
                    "GROUP BY product"
                ),
            },
        )
        create(
            "i_loop",
            {
                "type": "iteration",
                "execution": "sequential",
                "requires": ["t_scenarios", "t_results", "t_sales"],
                "scenarios": "t_scenarios",
                "step_view": "v_step",
                "target": "x_step",
                "order_by": ["region"],
            },
        )
        create(
            "v_done",
            {
                "type": "view",
                "mode": "create_or_replace",
                "requires": ["t_results"],
                "sql": (
                    "SELECT region, COUNT(*) AS n "
                    "FROM t_results GROUP BY region ORDER BY region"
                ),
            },
        )

        pairs = _edge_pairs(
            client.get("/gui/graph").json()["edges"]
        )
        assert ("t_scenarios", "i_loop") in pairs
        assert ("t_results", "v_done") in pairs

        assert client.post("/gui/build/i_loop").status_code == 200
        fin = client.post("/gui/build/v_done?limit=10").json()
        assert fin["ok"] is True
        assert fin["row_count"] == 2  # EU + US only
        by_reg = {row[0]: row[1] for row in fin["rows"]}
        # EU: products A,B → 2; US: A,B,C → 3
        assert by_reg["EU"] == 2
        assert by_reg["US"] == 3


def test_iteration_empty_scenarios_completes(tmp_path: Path):
    """0 scenario: p_iteration termine sans erreur, t_results vide."""
    from renatus.pipeline import ConnectionPipeline

    db, pipe = _prepare_project(tmp_path)
    cfg = _pipeline_iteration_config()
    cfg["t_scenarios"]["script"] = (
        "SELECT CAST(NULL AS VARCHAR) AS region WHERE 1 = 0"
    )
    _write_yaml(pipe / "default" / "pipeline.yaml", cfg)

    cp = ConnectionPipeline(db, pipe)
    try:
        cp.p_iteration("i_run")
        n = cp.con.execute(
            "SELECT COUNT(*) FROM t_results"
        ).fetchone()[0]
        assert n == 0
        cp.process_with_requires("v_final")
        n2 = cp.con.execute(
            "SELECT COUNT(*) FROM v_final"
        ).fetchone()[0]
        assert n2 == 0
    finally:
        cp.close()
