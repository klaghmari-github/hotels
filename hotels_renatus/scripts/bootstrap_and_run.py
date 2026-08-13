#!/usr/bin/env python3
"""
Bootstrap projet hotels_renatus + exécution flux (CLI renatus).

  python scripts/bootstrap_and_run.py --fresh
  python scripts/bootstrap_and_run.py --step v_estimate_sim_v1
  python scripts/bootstrap_and_run.py --parity

Étapes par défaut (build léger + estimate + ROI) :
  df_pilot_defaults → t_pilot_defaults → v_estimate_sim_v1 → v_roi_from_estimate_v1
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENATUS = Path("/media/laghmari/ssd-data/dev/hotels/renatus")
RELEASE = Path("/media/laghmari/ssd-data/dev/hotels/release_1_0_0")


def _ensure_input_link() -> None:
    link = ROOT / "input"
    target = RELEASE / "data" / "files" / "input"
    if link.is_symlink() or link.exists():
        return
    link.symlink_to(target)


def _write_project_yaml(db: Path) -> Path:
    yml = ROOT / "hotels_renatus.renatus.yaml"
    yml.write_text(
        "\n".join(
            [
                f"db_path: {db}",
                f"flow_path: {ROOT / 'flow'}",
                "name: hotels_renatus",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return yml


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fresh", action="store_true", help="Recrée data/main.duckdb")
    p.add_argument(
        "--step",
        action="append",
        default=[],
        help="Étape(s) process_with_requires (répétable)",
    )
    p.add_argument(
        "--parity",
        action="store_true",
        help="Après estimate_sim_v1, compare au service release",
    )
    p.add_argument(
        "--full-build-v1",
        action="store_true",
        help="Matérialise aussi LOO v1 (plus long)",
    )
    args = p.parse_args()

    sys.path.insert(0, str(RENATUS / "src"))
    from renatus.pipeline import ConnectionPipeline

    _ensure_input_link()
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / "main.duckdb"
    if args.fresh and db.exists():
        db.unlink()
        wal = Path(str(db) + ".wal")
        if wal.exists():
            wal.unlink()

    _write_project_yaml(db)
    flow = ROOT / "flow"

    steps = list(args.step)
    if not steps:
        steps = [
            "t_pilot_defaults",
            "t_estimate_input_v1",
            "v_estimate_sim_v1",
            "t_solution_costs",
            "v_roi_from_estimate_v1",
        ]
        if args.full_build_v1:
            steps = [
                "t_pilot_defaults",
                "t_hotel_params",
                "t_v1_loo_hotels",
                "v_v1_loo_metrics",
                "v_estimate_sim_v1",
                "v_roi_from_estimate_v1",
            ]

    print(f"db={db}")
    print(f"flow={flow}")
    print(f"steps={steps}")

    cp = ConnectionPipeline(str(db), flow)
    try:
        for name in steps:
            print(f"── process_with_requires {name}")
            cp.process_with_requires(name)
            print(f"   OK {name}")
    finally:
        cp.close()

    if args.parity:
        return _parity_v1(db)
    return 0


def _parity_v1(db: Path) -> int:
    import duckdb
    import pandas as pd

    sys.path.insert(0, str(RELEASE))
    from src.sim_v1.service import SimV1Service

    con = duckdb.connect(str(db), read_only=True)
    ren = con.execute(
        """
        SELECT solution, montant_ventes_par_mois, montant_marge_par_mois
        FROM v_estimate_sim_v1
        ORDER BY solution
        """
    ).df()
    try:
        inp = con.execute("SELECT * FROM t_estimate_input_v1").df().iloc[0]
    except Exception:
        inp = con.execute("SELECT * FROM df_estimate_input_v1").df().iloc[0]
    con.close()
    if ren.empty:
        print("PARITY FAIL: v_estimate_sim_v1 vide")
        return 1

    svc = SimV1Service()
    classic = svc.predict_from_levers(
        hotel_nb_chambres=float(inp["hotel_nb_chambres"]),
        hotel_to_annuel=float(inp["hotel_to_annuel"]),
        hotel_guests_per_chambre=float(inp["hotel_guests_per_chambre"]),
        metres_lineaires=float(inp["metres_lineaires"]),
        type_mix={
            "F&B": float(inp["mix_fb"]),
            "NON F&B": 1.0 - float(inp["mix_fb"]),
        },
        nb_frigos_froid=float(inp.get("nb_frigos_froid") or 3),
        solutions=["SIMPLY", "LIBERTY", "CONNECTED"],
    )
    by_sol = {
        str(r["solution"]).upper(): r for r in classic
    }

    ok = True
    print("solution | renatus_ca | classic_ca | abs_diff")
    for _, r in ren.iterrows():
        sol = str(r["solution"]).upper()
        ca_r = float(r["montant_ventes_par_mois"])
        ca_c = float(by_sol[sol]["montant_ventes_par_mois"])
        diff = abs(ca_r - ca_c)
        print(f"{sol:9} | {ca_r:10.4f} | {ca_c:10.4f} | {diff:.4f}")
        if diff > 0.05:  # tolérance centimes / float
            ok = False

    if ok:
        print("PARITY OK sim_v1 estimate (renatus flow ≈ classic service)")
        return 0
    print("PARITY FAIL")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
