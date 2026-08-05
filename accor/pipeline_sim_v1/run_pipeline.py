#!/usr/bin/env python3
"""
Lance le LOO sim_v1 via ConnectionPipeline (DuckDB + YAML).

  python -m pipeline_sim_v1.run_pipeline
  python pipeline_sim_v1/run_pipeline.py --rebuild
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

import pandas as pd

_PKG = Path(__file__).resolve().parent
_ROOT = _PKG.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline_sim_v1.constants import DATA_DIR, EXCEL_NEW, PROJECT_ROOT
from pipeline_sim_v1.prepare_sources import prepare_all

DB_DIR = PROJECT_ROOT / "duckdb" / "pilotes" / "sim_v1"
DB_PATH = DB_DIR / "sim_v1.duckdb"
# Repertoire package : rglob charge config/*.yaml, project_dir = accor/
PIPELINE_PATH = PROJECT_ROOT / "pipeline_sim_v1"


def open_sim_v1_pipeline(*, rebuild_db: bool = False):
    """Ouvre la base sim_v1 avec le gestionnaire de pipelines de main.py."""
    from main import ConnectionPipeline

    DB_DIR.mkdir(parents=True, exist_ok=True)
    if rebuild_db and DB_PATH.exists():
        for suffix in ("", ".wal"):
            p = Path(str(DB_PATH) + suffix) if suffix else DB_PATH
            if p.exists():
                p.unlink()

    try:
        return ConnectionPipeline(DB_PATH, PIPELINE_PATH, read_only=False)
    except Exception as first_error:
        # Copie de secours si lock (rare sur base dediee)
        work = DB_DIR / "sim_v1_work.duckdb"
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, work)
        else:
            raise first_error
        return ConnectionPipeline(work, PIPELINE_PATH, read_only=False)


def run_loo_pipeline(*, rebuild: bool = True) -> dict[str, pd.DataFrame]:
    """
    1. Prepare les Excel plats
    2. Charge tables / vues
    3. Execute i_v1_loo_evaluation
    4. Retourne predictions + metrics
    """
    logging.info("Preparation des sources plates…")
    prepare_all()

    cp = open_sim_v1_pipeline(rebuild_db=rebuild)
    try:
        # Recree le result set si rebuild
        if rebuild:
            try:
                cp.con.execute("DROP TABLE IF EXISTS t_v1_loo_results")
            except Exception:
                pass

        logging.info("Chargement t_hotel_params / scope…")
        cp.process_with_requires("t_v1_loo_hotels")
        cp.process_with_requires("t_v1_loo_results")
        cp.process_with_requires("t_solution_reference")

        n_hotels = cp.con.execute(
            "SELECT COUNT(*) FROM t_v1_loo_hotels"
        ).fetchone()[0]
        logging.info("Hotels LOO : %s", n_hotels)

        logging.info("Iteration LOO i_v1_loo_evaluation…")
        cp.process_with_requires("i_v1_loo_evaluation")

        predictions = cp.con.execute(
            """
            SELECT
              hotel_code,
              solution,
              ca_reel_mensuel AS ca_reel,
              ca_ht_predit AS ca_pred,
              abs_erreur_ca AS ca_err_abs,
              marge_reelle_mensuelle AS marge_reel,
              marge_produit_predite AS marge_pred,
              abs_erreur_marge AS marge_err_abs,
              n_mois,
              clients_hotel,
              taux_acheteurs,
              mix_steps,
              r4_mode,
              r4_diff
            FROM t_v1_loo_results
            WHERE hotel_code IS NOT NULL
            ORDER BY solution, hotel_code
            """
        ).df()

        metrics = cp.p_table_view("v_v1_loo_metrics").df()
        hotel_params = cp.con.execute(
            "SELECT * FROM v_hotel_params ORDER BY solution, hotel_code"
        ).df()

        return {
            "predictions": predictions,
            "metrics": metrics,
            "data": hotel_params,
        }
    finally:
        cp.close()


def export_pipeline_excel(
    result: dict[str, pd.DataFrame],
    path: Path | None = None,
) -> Path:
    path = path or EXCEL_NEW
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        result["data"].to_excel(writer, sheet_name="data", index=False)
        result["predictions"].to_excel(
            writer, sheet_name="predictions", index=False
        )
        result["metrics"].to_excel(writer, sheet_name="metrics", index=False)
        # Schema compatible UI historique
        eval_rows = result["predictions"].rename(
            columns={
                "ca_reel": "ca_ht_reel",
                "ca_pred": "ca_ht_pred",
                "ca_err_abs": "erreur_abs_ca",
                "marge_reel": "marge_reel",
                "marge_pred": "marge_pred",
                "marge_err_abs": "erreur_abs_marge",
            }
        )
        metrics_footer = []
        m = result["metrics"]
        if not m.empty:
            all_row = m[m["perimetre"].astype(str) == "ALL"]
            if not all_row.empty:
                r = all_row.iloc[0]
                metrics_footer.append(
                    {
                        "hotel_code": "MAE_GLOBAL",
                        "erreur_abs_ca": r.get("mae_ca"),
                        "erreur_abs_marge": r.get("mae_marge"),
                    }
                )
                metrics_footer.append(
                    {
                        "hotel_code": "MAPE_CA_PCT",
                        "erreur_abs_ca": r.get("mape_ca_pct"),
                        "erreur_abs_marge": None,
                    }
                )
        eval_out = pd.concat(
            [eval_rows, pd.DataFrame(metrics_footer)],
            ignore_index=True,
        )
        eval_out.to_excel(writer, sheet_name="eval", index=False)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LOO sim_v1 via ConnectionPipeline DuckDB"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        default=True,
        help="Recree la base et les resultats LOO (defaut)",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Garde la base existante (append resultats)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    rebuild = not args.no_rebuild
    result = run_loo_pipeline(rebuild=rebuild)
    path = export_pipeline_excel(result)
    print(f"Excel pipeline : {path}")
    print(result["metrics"].to_string(index=False))
    print("--- predictions ---")
    print(result["predictions"].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
