"""Règles de revenus ROD (simulateurs Simply / Liberty / Connected)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from rod_ia.domain.models.simulation import MonthlyProjection, RodSimulationRequest
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.traceability import RuleTrace


@dataclass
class RevenueComputation:
    monthly: List[MonthlyProjection]
    breakdown: Dict[str, float]
    trace: List[RuleTrace]
    warnings: List[str]


class RodRevenueRules:
    """Calcule les revenus mensuels à partir des références Excel.

    À valider cellule par cellule contre les feuilles SIMULATEUR *.
    """

    def __init__(self, reference: ReferenceRepository) -> None:
        self._reference = reference

    def compute(self, request: RodSimulationRequest) -> RevenueComputation:
        operating = request.operating
        store = request.store
        trace: list[RuleTrace] = []
        warnings: list[str] = []

        concept_key = f"concepts.{store.concept}"
        base_monthly_ca = float(self._reference.get(f"{concept_key}.base_monthly_ca", 0.0) or 0.0)
        base_monthly_sales = float(
            self._reference.get(f"{concept_key}.base_monthly_sales", 0.0) or 0.0
        )
        pivot_m_lin = float(self._reference.get(f"{concept_key}.pivot_m_lin", 1.0) or 1.0)
        pivot_clients_mois = float(
            self._reference.get(f"{concept_key}.pivot_clients_mois", 0.0) or 0.0
        )

        if base_monthly_ca == 0:
            warnings.append(
                "Référence base_monthly_ca absente — charger les constantes Excel "
                "via scripts/extract_excel_rules.py."
            )

        m_lin_factor = store.m_lin / pivot_m_lin if pivot_m_lin else 1.0
        client_factor = (
            operating.clients_mois / pivot_clients_mois if pivot_clients_mois else 1.0
        )

        trace.append(
            RuleTrace(
                rule_id="REV_MLIN_SCALE",
                workbook="ROD - Simulateurs + détail des coûts.xlsx",
                sheet="SIMULATEUR *",
                cells=["à valider: mètre linéaire pivot / projet"],
                excel_formula=None,
                business_description="Projection des revenus selon les mètres linéaires.",
                python_method="RodRevenueRules.compute",
                status="structure_ready_requires_excel_validation",
            )
        )
        trace.append(
            RuleTrace(
                rule_id="REV_CLIENTS_MONTH",
                workbook="ROD - Simulateurs + détail des coûts.xlsx",
                sheet="SIMULATEUR *",
                cells=["clients hébergés / mois"],
                excel_formula="clients_mois = nb_chambres * TO * guests/ch * 30.5",
                business_description="Clients mensuels depuis l'état opérationnel.",
                python_method="HotelOperatingState",
                status="implemented_formula_to_validate",
            )
        )

        seasonality: dict = self._reference.get("seasonality.monthly", {}) or {}
        monthly: list[MonthlyProjection] = []
        for month in range(1, 13):
            factor = float(seasonality.get(f"m{month:02d}", 1.0))
            ca = base_monthly_ca * m_lin_factor * client_factor * factor
            sales = base_monthly_sales * m_lin_factor * client_factor * factor
            monthly.append(MonthlyProjection(month=month, ca=ca, nbr_ventes=sales))

        return RevenueComputation(
            monthly=monthly,
            breakdown={"F&B": store.mix.fb_share, "Non-F&B": store.mix.non_fb_share},
            trace=trace,
            warnings=warnings,
        )