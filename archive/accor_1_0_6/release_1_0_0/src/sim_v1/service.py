"""
Service sim_v1 — LOO R1–R4 via pipeline SQL + prediction ponctuelle.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.release_1_0_0.src.pipeline.connection import PipelineFactory
from archive.accor_1_0_6.release_1_0_0.src.pipeline.engine import ConnectionPipeline
from archive.accor_1_0_6.release_1_0_0.src.pipeline.paths import Paths


class SimV1Service:
    def __init__(
        self,
        paths: Paths | None = None,
        factory: PipelineFactory | None = None,
    ):
        self.paths = (paths or Paths()).ensure()
        self.factory = factory or PipelineFactory(self.paths)

    def open(self, *, rebuild: bool = False) -> ConnectionPipeline:
        return self.factory.open(rebuild=rebuild)

    def run_loo(self, *, rebuild: bool = True) -> dict[str, pd.DataFrame]:
        """Leave-one-out sur les 6 hotels pilotes (hors H5586)."""
        cp = self.open(rebuild=False)
        try:
            if rebuild:
                try:
                    cp.con.execute("DROP TABLE IF EXISTS t_v1_loo_results")
                except Exception:
                    pass

            cp.process_with_requires("t_v1_loo_hotels")
            cp.process_with_requires("t_v1_loo_results")
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
                  n_mois
                FROM t_v1_loo_results
                WHERE hotel_code IS NOT NULL
                ORDER BY solution, hotel_code
                """
            ).df()
            metrics = cp.p_table_view("v_v1_loo_metrics").df()
            data = cp.con.execute(
                "SELECT * FROM v_hotel_params ORDER BY solution, hotel_code"
            ).df()
            return {
                "predictions": predictions,
                "metrics": metrics,
                "data": data,
            }
        finally:
            cp.close()

    def export_loo(self, result: dict[str, pd.DataFrame] | None = None) -> Path:
        result = result or self.run_loo(rebuild=True)
        path = self.paths.out_sim_v1("eval_sim_v1_loo.xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            result["data"].to_excel(writer, sheet_name="data", index=False)
            result["predictions"].to_excel(
                writer, sheet_name="predictions", index=False
            )
            result["metrics"].to_excel(writer, sheet_name="metrics", index=False)
        logging.info("Export sim_v1 LOO : %s", path)
        return path

    def list_hotels(self) -> pd.DataFrame:
        cp = self.open(read_only=False)
        try:
            cp.process_with_requires("v_hotel_params")
            return cp.con.execute(
                "SELECT * FROM v_hotel_params ORDER BY solution, hotel_code"
            ).df()
        finally:
            cp.close()

    def predict_hotel(self, hotel_code: str) -> dict[str, Any]:
        """
        Prediction LOO-style pour un hotel : reference = pairs, R1-R4.
        Utilise la vue SQL avec v_loo_step force sur l hotel.
        """
        cp = self.open(read_only=False)
        try:
            cp.process_with_requires("t_hotel_params")
            row = cp.con.execute(
                """
                SELECT hotel_code, solution
                FROM t_hotel_params
                WHERE hotel_code = ?
                """,
                [hotel_code],
            ).df()
            if row.empty:
                raise ValueError(f"Hotel inconnu dans le perimetre v1 : {hotel_code}")

            step = row.iloc[0].to_dict()
            cp.replace_step_view("v_loo_step", step)
            cp.process_with_requires("v_v1_prediction", processed=set())
            pred = cp.table_view("v_v1_prediction").df()
            if pred.empty:
                raise ValueError(f"Aucune prediction pour {hotel_code}")
            rec = pred.iloc[0].to_dict()
            return {
                "ok": True,
                "model": "sim_v1",
                "hotel_code": hotel_code,
                "solution": rec.get("solution"),
                "montant_ventes_par_mois": float(rec.get("ca_ht_predit") or 0),
                "montant_marge_par_mois": float(
                    rec.get("marge_produit_predite") or 0
                ),
                "detail": {
                    k: (None if pd.isna(v) else v)
                    for k, v in rec.items()
                },
            }
        finally:
            cp.close()
