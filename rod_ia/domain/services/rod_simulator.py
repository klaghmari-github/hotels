"""Orchestrateur de simulation ROD déterministe."""

from __future__ import annotations

from rod_ia.domain.models.simulation import MonthlyProjection, RodSimulationRequest, SimulationResult
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

    def simulate(
        self, request: RodSimulationRequest, concept: str | None = None
    ) -> SimulationResult:
        store = request.store
        if store is None:
            raise ValueError("store requis — fourni par SimulationOrchestrator")
        concept = concept or store.concept

        revenue = self.revenue_rules.compute(request, concept)
        cost = self.cost_rules.compute(request, concept)

        ca_mensuel = revenue.ca_ht_mensuel_base
        ventes_mensuel = revenue.nbr_ventes_mensuel_base
        ca_annuel = ca_mensuel * 12
        nbr_ventes_annuel = ventes_mensuel * 12
        marge_produit_annuelle = revenue.breakdown.get("marge_produit_mensuelle", 0.0) * 12
        marge_nette_annuelle = marge_produit_annuelle - cost.annual_cost

        roi_months = None
        if marge_nette_annuelle > 0 and cost.capex > 0:
            roi_months = cost.capex / (marge_nette_annuelle / 12)

        monthly: list[MonthlyProjection] = []
        for item in revenue.monthly:
            net = item.marge_produit - cost.monthly_cost
            monthly.append(
                MonthlyProjection(
                    month=item.month,
                    ca=ca_mensuel,
                    nbr_ventes=ventes_mensuel,
                    marge_produit=item.marge_produit,
                    cost=cost.monthly_cost,
                    marge_nette=net,
                    margin=net,
                )
            )

        breakdown = {
            **revenue.breakdown,
            "techno_monthly": cost.techno_monthly,
            "annexes_monthly": cost.annexes_monthly,
            "agencement_monthly": cost.agencement_monthly,
            "capex": cost.capex,
            "marge_produit_mensuelle": revenue.breakdown.get("marge_produit_mensuelle", 0.0),
            "marge_produit_annuelle": marge_produit_annuelle,
            "marge_nette_annuelle": marge_nette_annuelle,
        }

        return SimulationResult(
            source="ROD_EXCEL_RULES",
            concept=concept,
            m_lin=store.m_lin,
            ca_annuel=ca_annuel,
            nbr_ventes_annuel=nbr_ventes_annuel,
            ca_mensuel_moyen=ca_mensuel,
            nbr_ventes_mensuel_moyen=ventes_mensuel,
            marge_annuelle=marge_nette_annuelle,
            cout_annuel=cost.annual_cost,
            roi_months=roi_months,
            monthly=monthly,
            store_config=store.to_dict(),
            breakdown=breakdown,
            warnings=revenue.warnings + cost.warnings,
            trace=[entry.to_dict() for entry in revenue.trace + cost.trace],
        )