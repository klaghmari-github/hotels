"""Extraction des moyennes mensuelles depuis le fichier de ventes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry


class SalesMixExtractor:
    """Calcule les moyennes mensuelles par hôtel / mois / type / gamme.

    Jointure via ``hotel_id`` (registre d'identité) — jamais sur le nom brut.
    """

    def __init__(
        self,
        sales_path: str | Path,
        identity_registry: HotelIdentityRegistry,
    ) -> None:
        self.sales_path = Path(sales_path)
        self.identity_registry = identity_registry

    def load_sales(self) -> pd.DataFrame:
        if self.sales_path.suffix.lower() in {".xlsx", ".xlsm"}:
            return pd.read_excel(self.sales_path)
        return pd.read_csv(self.sales_path)

    def prepare(self, exclude_year: int | None = 2026) -> pd.DataFrame:
        """Charge les ventes ; si ``exclude_year`` est défini, exclut cette année (holdout test)."""
        frame = self.load_sales().copy()
        hotel_col = "NOM BOUTIQUE" if "NOM BOUTIQUE" in frame.columns else "HOTEL_NAME"
        date_col = "DATETIME" if "DATETIME" in frame.columns else "DATE"

        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
        frame["year"] = frame[date_col].dt.year
        frame["month"] = frame[date_col].dt.month

        if exclude_year is not None:
            frame = frame[frame["year"] < exclude_year]

        price_col = "PRIX TTC" if "PRIX TTC" in frame.columns else "PRIX HT"
        qty_col = "QUANTITE" if "QUANTITE" in frame.columns else "QTE"
        frame["montant"] = (
            pd.to_numeric(frame[price_col], errors="coerce").fillna(0)
            * pd.to_numeric(frame[qty_col], errors="coerce").fillna(0)
        )
        ticket_col = "ORDER ID (TICKET DE CAISSE)"
        frame["ticket_id"] = frame[ticket_col] if ticket_col in frame.columns else frame.index

        frame["hotel_id"] = frame[hotel_col].map(
            lambda name: self.identity_registry.resolve("ventes", str(name))
        )
        unresolved = frame[frame["hotel_id"].isna()][hotel_col].unique().tolist()
        if unresolved:
            raise ValueError(
                f"Hôtels ventes non résolus vers hotel_id: {unresolved}. "
                "Compléter data/reference/hotel_identity_registry.json."
            )
        frame["hotel_name_raw"] = frame[hotel_col]
        return frame

    def monthly_average_targets(self, exclude_year: int | None = 2026) -> pd.DataFrame:
        """Moyenne mensuelle d'entraînement par hotel_id (années < exclude_year si défini)."""
        frame = self.prepare(exclude_year=exclude_year)
        keys = ["hotel_id", "month", "TYPE", "GAMME"]
        annual = (
            frame.groupby(keys + ["year"], dropna=False)
            .agg(
                montant=("montant", "sum"),
                nbr_ventes=("ticket_id", "nunique"),
            )
            .reset_index()
        )
        return (
            annual.groupby(keys, dropna=False)
            .agg(
                avg_montant=("montant", "mean"),
                avg_nbr_ventes=("nbr_ventes", "mean"),
                nb_years_used=("year", "nunique"),
                nb_observations=("year", "count"),
            )
            .reset_index()
        )