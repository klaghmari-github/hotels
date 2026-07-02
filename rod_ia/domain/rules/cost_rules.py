"""Coûts ROD — technos, annexes, agencement (feuilles COUTS *)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.traceability import RuleTrace


@dataclass
class CostComputation:
    annual_cost: float
    monthly_cost: float
    capex: float
    opex_monthly: float
    techno_monthly: float
    annexes_monthly: float
    agencement_monthly: float
    trace: List[RuleTrace]
    warnings: List[str]


class RodCostRules:
    """Capex + opex mensuels amortis selon références Excel."""

    def __init__(self, reference: ReferenceRepository) -> None:
        self._reference = reference

    def compute(self, request: RodSimulationRequest, concept: str) -> CostComputation:
        store = request.store
        if store is None:
            raise ValueError("store requis pour le calcul coûts")
        warnings: list[str] = []
        key = f"concepts.{concept}"

        fixed_capex = float(self._reference.get(f"{key}.fixed_capex", 0.0) or 0.0)
        techno_monthly = float(self._reference.get(f"{key}.techno_monthly", 0.0) or 0.0)
        annexes_monthly = float(self._reference.get(f"{key}.annexes_monthly", 0.0) or 0.0)
        agencement_per_m = float(self._reference.get(f"{key}.agencement_per_m", 1000.0) or 1000.0)
        amort_months = float(self._reference.get(f"{key}.amort_months", 84.0) or 84.0)

        agencement_capex = agencement_per_m * store.m_lin
        capex = fixed_capex + agencement_capex
        agencement_monthly = agencement_capex / amort_months if amort_months else 0.0
        monthly_cost = techno_monthly + annexes_monthly + agencement_monthly

        if monthly_cost == 0:
            warnings.append(f"Coûts mensuels nuls pour {concept} — vérifier références Excel.")

        trace = [
            RuleTrace(
                rule_id="COST_TECHNOS_ANNEXES_AGENCEMENT",
                workbook="ROD - Simulateurs + détail des coûts.xlsx",
                sheet="COUTS - TECHNOS / ANNEXES / AGENCEMENT",
                cells=["à valider cellule par cellule"],
                excel_formula="marge_nette = marge_produit - coûts_mensuels",
                business_description="Technos + annexes + agencement amorti 84 mois.",
                python_method="RodCostRules.compute",
                status="implemented_from_documentation",
            )
        ]
        return CostComputation(
            annual_cost=monthly_cost * 12,
            monthly_cost=monthly_cost,
            capex=capex,
            opex_monthly=techno_monthly + annexes_monthly,
            techno_monthly=techno_monthly,
            annexes_monthly=annexes_monthly,
            agencement_monthly=agencement_monthly,
            trace=trace,
            warnings=warnings,
        )