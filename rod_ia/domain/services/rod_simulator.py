"""Orchestrateur de simulation ROD déterministe."""

from __future__ import annotations

from rod_ia.domain.models.simulation import RodSimulationRequest, SimulationResult
from rod_ia.domain.rules.cost_rules import RodCostRules
from rod_ia.domain.rules.recommendation_rules import RodRecommendationRules
from rod_ia.domain.rules.revenue_rules import RodRevenueRules


class RodSimulator:
    """Agrège revenus, coûts et trace pour produire un ``SimulationResult``."""

    def __init__(
        self,
        revenue_rules: RodRevenueRules,
        cost_rules: RodCostRules,
        recommendation_rules: RodRecommendationRules | None = None,
    ) -> None:
        self.revenue_rules = revenue_rules
        self.cost_rules = cost_rules
        self.recommendation_rules = recommendation_rules

    def simulate(self, request: RodSimulationRequest) -> SimulationResult:
        revenue = self.revenue_rules.compute(request)
        cost = self.cost_rules.compute(request)

        ca_annuel = sum(item.ca for item in revenue.monthly)
        nbr_ventes_annuel = sum(item.nbr_ventes for item in revenue.monthly)
        marge_annuelle = ca_annuel - cost.annual_cost
        roi_months = None
        if marge_annuelle > 0 and cost.capex > 0:
            roi_months = cost.capex / (marge_annuelle / 12)

        monthly = []
        for item in revenue.monthly:
            item.cost = cost.monthly_cost
            item.margin = item.ca - cost.monthly_cost
            monthly.append(item)

        return SimulationResult(
            source="ROD_EXCEL_RULES",
            concept=request.store.concept,
            m_lin=request.store.m_lin,
            ca_annuel=ca_annuel,
            nbr_ventes_annuel=nbr_ventes_annuel,
            marge_annuelle=marge_annuelle,
            cout_annuel=cost.annual_cost,
            roi_months=roi_months,
            monthly=monthly,
            breakdown=revenue.breakdown,
            warnings=revenue.warnings + cost.warnings,
            trace=[entry.to_dict() for entry in revenue.trace + cost.trace],
        )