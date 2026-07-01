"""Règles de coûts ROD (technos, annexes, agencement)."""

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
    trace: List[RuleTrace]
    warnings: List[str]


class RodCostRules:
    """Coûts capex, opex et amortissement par concept retail."""

    def __init__(self, reference: ReferenceRepository) -> None:
        self._reference = reference

    def compute(self, request: RodSimulationRequest) -> CostComputation:
        concept = request.store.concept
        m_lin = request.store.m_lin
        warnings: list[str] = []
        key = f"concepts.{concept}"

        cost_per_m = float(self._reference.get(f"{key}.cost_per_m", 0.0) or 0.0)
        fixed_capex = float(self._reference.get(f"{key}.fixed_capex", 0.0) or 0.0)
        opex_monthly = float(self._reference.get(f"{key}.opex_monthly", 0.0) or 0.0)
        amort_months = float(self._reference.get(f"{key}.amort_months", 84.0) or 84.0)

        if not any((cost_per_m, fixed_capex, opex_monthly)):
            warnings.append(
                "Références coûts absentes — exécuter l'extraction Excel avant production."
            )

        capex = fixed_capex + cost_per_m * m_lin
        monthly_cost = (capex / amort_months if amort_months else 0.0) + opex_monthly
        trace = [
            RuleTrace(
                rule_id="COST_CAPEX_OPEX_AMORT",
                workbook="ROD - Simulateurs + détail des coûts.xlsx",
                sheet="COUTS - TECHNOS / ANNEXES / AGENCEMENT",
                cells=["à valider cellule par cellule"],
                excel_formula=None,
                business_description="Capex + opex + amortissement mensuel.",
                python_method="RodCostRules.compute",
                status="structure_ready_requires_excel_validation",
            )
        ]
        return CostComputation(
            annual_cost=monthly_cost * 12,
            monthly_cost=monthly_cost,
            capex=capex,
            opex_monthly=opex_monthly,
            trace=trace,
            warnings=warnings,
        )