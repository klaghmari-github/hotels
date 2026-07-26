"""
Utilitaires partages pour les rebuilds geo (weather / proximity / holidays).

Regles communes:
  hotels = hotel_data.xlsx
  annees = hotel_sales_data.xlsx
  mois termines seulement (mois courant exclu)
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from data_io import DATA_DIR, filter_france_hotels, read_excel

# re-export pour compatibilite
__all__ = [
    "DATA_DIR",
    "load_hotels",
    "load_sales",
    "sales_years",
    "months_for_year",
    "year_month_pairs",
    "filter_frame_to_pairs",
    "filter_france_hotels",
]


def load_hotels() -> pd.DataFrame:
    """Charge hotel_data.xlsx."""
    return read_excel(DATA_DIR / "hotel_data.xlsx", sheet=0)


def load_sales() -> pd.DataFrame:
    """Charge les ventes mensuelles hotel_sales_data."""
    path = DATA_DIR / "hotel_sales_data.xlsx"
    return read_excel(path, sheet="hotel_sales")


def sales_years(sales: pd.DataFrame | None = None) -> list[int]:
    """Annees presentes dans les ventes (fallback: 2 dernieres annees)."""
    if sales is None:
        sales = load_sales()
    if sales is None or sales.empty or "annee" not in sales.columns:
        today = date.today()
        return [today.year - 2, today.year - 1]
    years = sorted(
        {
            int(y)
            for y in pd.to_numeric(sales["annee"], errors="coerce").dropna().unique()
        }
    )
    return years


def months_for_year(year: int, *, today: date | None = None) -> list[int]:
    """
    Mois a generer pour une annee.

    annee passee → 1..12
    annee courante → 1..(mois-1)
    annee future → []
    """
    today = today or date.today()
    y = int(year)
    if y < today.year:
        return list(range(1, 13))
    if y == today.year:
        last = today.month - 1
        return list(range(1, last + 1)) if last >= 1 else []
    return []


def year_month_pairs(
    years: list[int] | None = None, *, today: date | None = None
) -> list[tuple[int, int]]:
    """Liste (annee, mois) pour weather / holidays."""
    today = today or date.today()
    if years is None:
        years = sales_years()
    pairs: list[tuple[int, int]] = []
    for y in years:
        for m in months_for_year(y, today=today):
            pairs.append((int(y), int(m)))
    return pairs


def filter_frame_to_pairs(
    frame: pd.DataFrame,
    pairs: list[tuple[int, int]],
) -> pd.DataFrame:
    """Ne garde que les lignes (annee, mois) dans pairs."""
    if frame is None or frame.empty:
        return frame
    if not pairs or "annee" not in frame.columns or "mois" not in frame.columns:
        return frame
    allowed = set(pairs)
    an = pd.to_numeric(frame["annee"], errors="coerce")
    mo = pd.to_numeric(frame["mois"], errors="coerce")
    mask = [
        (int(a), int(m)) in allowed if pd.notna(a) and pd.notna(m) else False
        for a, m in zip(an, mo)
    ]
    return frame.loc[mask].reset_index(drop=True)
