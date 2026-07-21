"""Statistiques mensuelles pour la normalisation SalesPrep."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class YearMonthStats:
    nombre_mois: int
    premier_mois: int
    dernier_mois: int
    mois_actifs: int
    mois_manquants: int


def compute_year_month_stats(months_with_sales: set[int]) -> YearMonthStats:
    """Calcule les indicateurs annuels à partir des mois ayant des ventes."""
    if not months_with_sales:
        return YearMonthStats(0, 0, 0, 0, 12)

    premier = min(months_with_sales)
    dernier = max(months_with_sales)
    nombre = len(months_with_sales)
    manquants = (premier - 1) + (12 - dernier)
    actifs = 12 - manquants
    return YearMonthStats(nombre, premier, dernier, actifs, manquants)


def missing_boundary_months(premier_mois: int, dernier_mois: int) -> list[int]:
    """Mois hors de la plage [premier, dernier] à imputer."""
    before = list(range(1, premier_mois))
    after = list(range(dernier_mois + 1, 13))
    return before + after