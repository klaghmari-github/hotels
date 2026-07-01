"""Répartitions en pourcentage depuis les moyennes mensuelles de ventes."""

from __future__ import annotations

import pandas as pd

from rod_ia.domain.services.ml_column_naming import MLColumnNaming


class SalesPercentageService:
    """Construit les répartitions % à 3 niveaux depuis ``monthly_average_targets``.

    Niveau 1 : % par mois (saisonnalité globale)
    Niveau 2 : % par TYPE dans chaque mois
    Niveau 3 : % par GAMME dans chaque mois × TYPE
    """

    def __init__(self, monthly_avg: pd.DataFrame) -> None:
        self.monthly_avg = monthly_avg.copy()

    def compute_all(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Retourne (wide_descriptives, long_percentages)."""
        long_pct = self._compute_long_percentages()
        wide = self._to_wide_descriptives(long_pct)
        return wide, long_pct

    def _compute_long_percentages(self) -> pd.DataFrame:
        frame = self.monthly_avg.copy()
        rows: list[dict] = []

        for hotel_id, hotel_df in frame.groupby("hotel_id"):
            total_by_month = hotel_df.groupby("month")["avg_montant"].sum()
            grand_total = total_by_month.sum()
            if grand_total <= 0:
                continue

            for month, month_total in total_by_month.items():
                month_int = int(month)
                rows.append(
                    {
                        "hotel_id": hotel_id,
                        "level": 1,
                        "month": month_int,
                        "TYPE": None,
                        "GAMME": None,
                        "column": MLColumnNaming.pct_month(month_int),
                        "pct": float(month_total / grand_total),
                    }
                )

            for (month, type_label), type_df in hotel_df.groupby(["month", "TYPE"]):
                month_int = int(month)
                month_total = float(total_by_month.get(month, 0.0))
                type_total = float(type_df["avg_montant"].sum())
                if month_total <= 0:
                    continue
                rows.append(
                    {
                        "hotel_id": hotel_id,
                        "level": 2,
                        "month": month_int,
                        "TYPE": type_label,
                        "GAMME": None,
                        "column": MLColumnNaming.pct_month_type(month_int, str(type_label)),
                        "pct": type_total / month_total,
                    }
                )

                for _, gamme_row in type_df.iterrows():
                    gamme = gamme_row["GAMME"]
                    gamme_val = float(gamme_row["avg_montant"])
                    if type_total <= 0:
                        continue
                    rows.append(
                        {
                            "hotel_id": hotel_id,
                            "level": 3,
                            "month": month_int,
                            "TYPE": type_label,
                            "GAMME": gamme,
                            "column": MLColumnNaming.pct_month_type_gamme(
                                month_int, str(type_label), str(gamme)
                            ),
                            "pct": gamme_val / type_total,
                        }
                    )

        return pd.DataFrame(rows)

    def _to_wide_descriptives(self, long_pct: pd.DataFrame) -> pd.DataFrame:
        if long_pct.empty:
            return pd.DataFrame()
        wide = (
            long_pct.pivot_table(
                index="hotel_id", columns="column", values="pct", aggfunc="first"
            )
            .fillna(0.0)
            .reset_index()
        )
        wide.columns.name = None
        return wide