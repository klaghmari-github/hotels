"""
Utilitaires partagés pour les rebuilds geo (weather / proximity / holidays).

Règles communes
---------------
* Liste des hôtels = ``hotel_data.xlsx``
* Années à couvrir = années présentes dans ``hotel_sales_data.xlsx``
* Mois = 1..12 pour les années passées ; pour l'année en cours, 1..(mois-1)
  (le mois courant est exclu car incomplet).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"


def load_hotels() -> pd.DataFrame:
    """Charge la fiche hôtels (coords + codes)."""
    path = DATA_DIR / "hotel_data.xlsx"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=0)
    except Exception:
        return pd.DataFrame()


def load_sales() -> pd.DataFrame:
    """Charge les ventes mensuelles."""
    path = DATA_DIR / "hotel_sales_data.xlsx"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name="hotel_sales")
    except ValueError:
        try:
            return pd.read_excel(path, sheet_name=0)
        except Exception:
            return pd.DataFrame()


def sales_years(sales: pd.DataFrame | None = None) -> list[int]:
    """Années pour lesquelles on dispose d'info de ventes."""
    if sales is None:
        sales = load_sales()
    if sales is None or sales.empty or "annee" not in sales.columns:
        # fallback : 3 dernières années calendaires (hors année en cours si besoin)
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
    Mois à générer pour une année.

    * année < année courante → 1..12
    * année == année courante → 1..(mois_courant - 1)  [mois en cours exclu]
    * année > année courante → []
    """
    today = today or date.today()
    y = int(year)
    if y < today.year:
        return list(range(1, 13))
    if y == today.year:
        last = today.month - 1
        return list(range(1, last + 1)) if last >= 1 else []
    return []


def year_month_pairs(years: list[int] | None = None, *, today: date | None = None) -> list[tuple[int, int]]:
    """Liste (année, mois) à produire pour weather / holidays."""
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
    """Ne garde que les lignes (annee, mois) ∈ pairs."""
    if frame is None or frame.empty:
        return frame
    if not pairs or "annee" not in frame.columns or "mois" not in frame.columns:
        return frame
    allowed = set(pairs)
    an = pd.to_numeric(frame["annee"], errors="coerce")
    mo = pd.to_numeric(frame["mois"], errors="coerce")
    mask = [
        (int(a), int(m)) in allowed
        if pd.notna(a) and pd.notna(m)
        else False
        for a, m in zip(an, mo)
    ]
    return frame.loc[mask].reset_index(drop=True)
