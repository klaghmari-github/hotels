"""
Service sim_v2 — restitution coefficients + LOO (pipeline YAML).
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pandas as pd

from src.pipeline.connection import PipelineFactory
from src.pipeline.engine import ConnectionPipeline
from src.pipeline.paths import Paths


def normalized_mix_name(family: str, label: str) -> str:
    """Meme convention que main.py pour les colonnes de parts."""
    import re
    import unicodedata

    raw = f"{family}_{label}_part_natures"
    text = (
        unicodedata.normalize("NFKD", str(raw))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    text = text.lower().replace("&", " et ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


class SimV2Service:
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
        cp = self.open(rebuild=False)
        try:
            if rebuild:
                try:
                    cp.con.sql("DROP TABLE IF EXISTS t_loo_results")
                except Exception:
                    pass
            cp.p_iteration("i_loo_evaluation")
            results = cp.table_view("t_loo_results").df()
            metrics = cp.p_table_view("v_loo_metrics").df()
            comparison = cp.p_table_view("v_loo_method_comparison").df()
            return {
                "predictions": results,
                "metrics": metrics,
                "method_comparison": comparison,
            }
        finally:
            cp.close()

    def export_loo(self, result: dict[str, pd.DataFrame] | None = None):
        result = result or self.run_loo(rebuild=True)
        path = self.paths.out_sim_v2("eval_sim_v2_loo.xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            result["predictions"].to_excel(
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
        """Restitution A/B pour les 3 solutions (API prediction)."""
        # Import local pour garder le service leger
        from src.pipeline.engine import register_dataframe_as_relation

        cp = self.open(read_only=False)
        try:
            default_mix = cp.p_table_view(
                "v_restitution_default_input_mix"
            ).df()

            def family_rows(
                family: str,
                supplied: dict[str, float] | None,
            ) -> list[tuple[str, str, float]]:
                if supplied is None:
                    family_default = default_mix[
                        default_mix["variable_family"] == family
                    ]
                    return [
                        (
                            family,
                            str(row.variable_name),
                            float(row.target_part),
                        )
                        for row in family_default.itertuples(index=False)
                    ]
                if not supplied:
                    raise ValueError(f"Le mix {family} ne peut pas etre vide")
                if any(v < 0 for v in supplied.values()):
                    raise ValueError(f"Le mix {family} contient une part negative")
                if not math.isclose(
                    sum(supplied.values()), 1.0, rel_tol=1e-6, abs_tol=1e-6
                ):
                    raise ValueError(f"La somme du mix {family} doit etre egale a 1")
                return [
                    (family, normalized_mix_name(family, label), float(part))
                    for label, part in supplied.items()
                ]

            cp.con.sql(
                f"""
                CREATE OR REPLACE TEMP VIEW v_restitution_input_hotel AS
                SELECT
                    {float(hotel_nb_chambres)}::DOUBLE AS hotel_nb_chambres,
                    {float(hotel_to_annuel)}::DOUBLE AS hotel_to_annuel,
                    {float(hotel_guests_per_chambre)}::DOUBLE
                        AS hotel_guests_per_chambre,
                    {float(metres_lineaires)}::DOUBLE AS metres_lineaires
                """
            )
            rows = [
                *family_rows("type", type_mix),
                *family_rows("gamme", gamme_mix),
            ]
            input_df = pd.DataFrame(
                rows,
                columns=["variable_family", "variable_name", "target_part"],
            )
            register_dataframe_as_relation(
                cp.con,
                "__restitution_input_mix_buffer",
                input_df,
                "table",
                replace=True,
            )
            cp.con.sql(
                """
                CREATE OR REPLACE TEMP VIEW v_restitution_input_mix AS
                SELECT * FROM __restitution_input_mix_buffer
                """
            )
            cp.process_with_requires(
                "v_restitution_prediction", processed=set()
            )
            return cp.table_view("v_restitution_prediction").df()
        finally:
            cp.close()

    def list_pilot_hotels(self) -> pd.DataFrame:
        cp = self.open(read_only=False)
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
