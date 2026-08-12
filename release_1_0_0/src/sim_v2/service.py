"""
Facade haut niveau sim_v2 — orchestre sans reimplementer le moteur.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pandas as pd

from src.pipeline.connection import PipelineFactory
from src.pipeline.engine import ConnectionPipeline
from src.pipeline.paths import Paths
from src.sim_v2.loo import run_leave_one_out
from src.sim_v2.modeling import run_modeling_simulation
from src.sim_v2.optimal_mix import (
    hotel_exposure_frame,
    recommend_optimal_mix,
)
from src.sim_v2.restitution import normalized_mix_name, run_restitution
from src.sim_v2.scenarios import ScenarioGenerator


class SimV2Service:
    def __init__(
        self,
        paths: Paths | None = None,
        factory: PipelineFactory | None = None,
    ):
        self.paths = (paths or Paths()).ensure()
        self.factory = factory or PipelineFactory(self.paths)

    def open(
        self,
        *,
        rebuild: bool = False,
        read_only: bool = False,
    ) -> ConnectionPipeline:
        return self.factory.open(rebuild=rebuild, read_only=read_only)

    def build_modeling(
        self,
        *,
        include_full_removal: bool = True,
    ) -> dict[str, Any]:
        """
        Pipeline complet modelisation : ranks → scenarios → simulation.
        Equivalent de l'ancien main() de main.py.
        """
        return run_modeling_simulation(
            db_con_str=self.paths.main_db,
            pipeline_path=self.paths.pipeline,
            scenarios_excel_path=self.paths.input / "scenarios.xlsx",
            include_full_removal=include_full_removal,
        )

    def generate_scenarios(
        self,
        *,
        include_full_removal: bool = True,
        write_excel: bool = True,
    ) -> pd.DataFrame:
        """Genere le catalogue de scenarios (set + Excel optionnel)."""
        cp = self.open(rebuild=False)
        try:
            generator = ScenarioGenerator(
                cp,
                self.paths.input / "scenarios.xlsx",
            )
            generator.generate_rank_scenarios(
                include_full_removal=include_full_removal
            )
            if write_excel:
                return generator.write_excel()
            rows = []
            for values in sorted(
                generator._scenarios,
                key=lambda item: (len(item), item),
            ):
                rows.append(
                    {
                        "scenario_id": generator.scenario_hash(values),
                        "scenario_removed_natures": list(values),
                    }
                )
            return pd.DataFrame(rows)
        finally:
            cp.close()

    def run_loo(self, *, rebuild: bool = True) -> dict[str, pd.DataFrame]:
        cp = self.open(rebuild=False)
        try:
            return run_leave_one_out(cp, rebuild=rebuild)
        finally:
            # run_leave_one_out leaves connection open intentionally in old API;
            # we own cp here so close after reading dataframes.
            try:
                cp.close()
            except Exception:
                pass

    def export_loo(self, result: dict[str, pd.DataFrame] | None = None):
        result = result or self.run_loo(rebuild=True)
        path = self.paths.out_sim_v2("eval_sim_v2_loo.xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            result["results"].to_excel(
                writer, sheet_name="predictions", index=False
            )
            result["metrics"].to_excel(writer, sheet_name="metrics", index=False)
            result["method_comparison"].to_excel(
                writer, sheet_name="method_comparison", index=False
            )
        logging.info("Export sim_v2 LOO : %s", path)
        return path

    def predict(
        self,
        *,
        hotel_nb_chambres: float = 100,
        hotel_to_annuel: float = 0.70,
        hotel_guests_per_chambre: float = 1.7,
        metres_lineaires: float = 6.0,
        type_mix: dict[str, float] | None = None,
        gamme_mix: dict[str, float] | None = None,
    ) -> pd.DataFrame:
        cp = self.open(rebuild=False)
        try:
            return run_restitution(
                cp,
                hotel_nb_chambres=hotel_nb_chambres,
                hotel_to_annuel=hotel_to_annuel,
                hotel_guests_per_chambre=hotel_guests_per_chambre,
                metres_lineaires=metres_lineaires,
                type_mix=type_mix,
                gamme_mix=gamme_mix,
            )
        finally:
            cp.close()

    def recommend_optimal_mix(
        self,
        *,
        solution: str,
        metres_lineaires: float,
        allowed_types: list[str] | None = None,
        allowed_gammes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Top N produits par rang de marge + mix F&B/gammes pour m_lin cible."""
        cp = self.open(rebuild=False)
        try:
            return recommend_optimal_mix(
                cp,
                solution=solution,
                metres_lineaires=metres_lineaires,
                allowed_types=allowed_types,
                allowed_gammes=allowed_gammes,
            )
        finally:
            cp.close()

    def product_exposure(self) -> pd.DataFrame:
        """Exposition produits / m_lin par hotel pilote."""
        cp = self.open(rebuild=False)
        try:
            return hotel_exposure_frame(cp)
        finally:
            cp.close()

    def list_pilot_hotels(self) -> pd.DataFrame:
        cp = self.open(rebuild=False)
        try:
            return cp.con.execute(
                """
                SELECT
                  HOTEL_CODE AS hotel_code,
                  ANY_VALUE(SOLUTION) AS solution,
                  MAX(HOTEL_NB_CHAMBRES)::DOUBLE AS hotel_nb_chambres,
                  MAX(HOTEL_TO_ANNUEL)::DOUBLE AS hotel_to_annuel,
                  MAX(HOTEL_GUESTS_PER_CHAMBRE)::DOUBLE
                    AS hotel_guests_per_chambre
                FROM t_sales
                GROUP BY HOTEL_CODE
                ORDER BY HOTEL_CODE
                """
            ).df()
        except Exception:
            return pd.DataFrame()
        finally:
            cp.close()
