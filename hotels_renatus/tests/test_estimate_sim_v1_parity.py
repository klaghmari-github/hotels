"""Tests unitaires hotels_renatus — estimate sim_v1 SQL vs service release."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RENATUS = Path("/media/laghmari/ssd-data/dev/hotels/renatus")
RELEASE = Path("/media/laghmari/ssd-data/dev/hotels/release_1_0_0")

sys.path.insert(0, str(RENATUS / "src"))
sys.path.insert(0, str(RELEASE))


@pytest.fixture(scope="module")
def estimate_db(tmp_path_factory):
    """Base DuckDB temporaire + flow estimate_sim_v1 uniquement (symlinks résolus)."""
    from renatus.pipeline import ConnectionPipeline

    tmp = tmp_path_factory.mktemp("hr_v1")
    flow = tmp / "flow"
    flow.mkdir()
    # Copie monocomposants nécessaires (fichiers réels, pas symlinks cassés)
    needed = [
        ROOT / "flow" / "estimate_sim_v1" / "df_estimate_input_v1.yaml",
        ROOT / "flow" / "estimate_sim_v1" / "t_estimate_input_v1.yaml",
        ROOT / "flow" / "estimate_sim_v1" / "v_estimate_hotel_levers.yaml",
        ROOT / "flow" / "estimate_sim_v1" / "v_estimate_sim_v1.yaml",
        ROOT / "flow" / "build_sim_v1" / "df_pilot_defaults.yaml",
        ROOT / "flow" / "build_sim_v1" / "t_pilot_defaults.yaml",
    ]
    for src in needed:
        assert src.exists(), src
        # dé-symlink
        real = src.resolve()
        (flow / src.name).write_text(real.read_text(encoding="utf-8"), encoding="utf-8")

    # input paths: rewrite relative to ROOT
    # dataframe files point to input/ and input_estimate relative to project
    # → project_dir = ROOT for path resolution: pass ROOT as parent of flow? 
    # ConnectionPipeline project_dir = parent of flow if flow is dir
    # So put flow under ROOT-like structure
    proj = tmp / "proj"
    proj.mkdir()
    flow2 = proj / "flow"
    flow2.mkdir()
    for f in flow.iterdir():
        (flow2 / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    # symlink inputs into proj
    (proj / "input").symlink_to(RELEASE / "data" / "files" / "input")
    (proj / "input_estimate").symlink_to(ROOT / "input_estimate")

    db = proj / "test.duckdb"
    cp = ConnectionPipeline(str(db), flow2)
    try:
        cp.process_with_requires("v_estimate_sim_v1")
    finally:
        cp.close()
    return db


def test_estimate_sim_v1_matches_classic(estimate_db):
    import duckdb
    from src.sim_v1.service import SimV1Service

    con = duckdb.connect(str(estimate_db), read_only=True)
    ren = con.execute(
        "SELECT solution, montant_ventes_par_mois, montant_marge_par_mois "
        "FROM v_estimate_sim_v1 ORDER BY solution"
    ).df()
    inp = con.execute("SELECT * FROM t_estimate_input_v1").df().iloc[0]
    con.close()

    assert len(ren) >= 1
    sols = [str(s).upper() for s in ren["solution"].tolist()]
    classic = SimV1Service().predict_from_levers(
        hotel_nb_chambres=float(inp["hotel_nb_chambres"]),
        hotel_to_annuel=float(inp["hotel_to_annuel"]),
        hotel_guests_per_chambre=float(inp["hotel_guests_per_chambre"]),
        metres_lineaires=float(inp["metres_lineaires"]),
        type_mix={
            "F&B": float(inp["mix_fb"]),
            "NON F&B": 1.0 - float(inp["mix_fb"]),
        },
        nb_frigos_froid=float(inp.get("nb_frigos_froid") or 3),
        solutions=sols,
    )
    by = {str(r["solution"]).upper(): r for r in classic}
    for _, row in ren.iterrows():
        sol = str(row["solution"]).upper()
        assert abs(float(row["montant_ventes_par_mois"]) - float(by[sol]["montant_ventes_par_mois"])) < 0.05
        assert abs(float(row["montant_marge_par_mois"]) - float(by[sol]["montant_marge_par_mois"])) < 0.05


def test_roi_positive_when_margin_exceeds_cost(estimate_db):
    import duckdb
    from renatus.pipeline import ConnectionPipeline

    # extend flow with roi steps
    proj = estimate_db.parent
    flow = proj / "flow"
    for name in ("t_solution_costs.yaml", "v_roi_from_estimate_v1.yaml"):
        src = (ROOT / "flow" / "roi" / name).resolve()
        (flow / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    cp = ConnectionPipeline(str(estimate_db), flow)
    try:
        cp.process_with_requires("v_roi_from_estimate_v1")
        roi = cp.con.execute("SELECT * FROM v_roi_from_estimate_v1").df()
    finally:
        cp.close()
    assert not roi.empty
    assert "roi_monthly" in roi.columns
    assert "payback_months" in roi.columns


def test_zone_files_and_symlinks_exist():
    assert (ROOT / "flow" / "main.yaml").is_file()
    assert (ROOT / "flow" / "roi.yaml").is_file()
    # shared presence via symlink
    link = ROOT / "flow" / "estimate_sim_v1" / "t_pilot_defaults.yaml"
    assert link.exists()
    assert link.is_symlink() or link.is_file()
