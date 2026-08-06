"""
Simulateur unitaire : revenus + coûts → marge pour **un** concept.

Séparation claire :
* ``RevenueRules.compute`` → CA / ventes / marge produit
* ``CostRules.compute``    → techno / annexes / agencement
* agrégation ici          → marge nette, ROI
"""

from __future__ import annotations

from archive.accor_1_0_5.accor_1_0_0.user.models import ConceptSimulation, SimulationRequest
from archive.accor_1_0_5.accor_1_0_0.user.rules.costs import CostRules
from archive.accor_1_0_5.accor_1_0_0.user.rules.revenue import RevenueRules


class RodSimulator:
    """Agrège revenus et coûts pour un concept."""

    SOURCE = "ROD_RULES"

    def __init__(self, revenue: RevenueRules, costs: CostRules) -> None:
        self.revenue = revenue
        self.costs = costs

    def simulate(self, request: SimulationRequest, concept: str) -> ConceptSimulation:
        concept = concept.upper()
        rev = self.revenue.compute(request, concept)
        cost = self.costs.compute(request, concept)

        marge_prod_m = rev.marge_produit_mensuelle
        marge_prod_a = marge_prod_m * 12
        marge_nette_m = marge_prod_m - cost.monthly_cost
        marge_nette_a = marge_prod_a - cost.annual_cost

        roi = None
        if marge_nette_a > 0 and cost.capex > 0:
            roi = cost.capex / (marge_nette_a / 12)

        return ConceptSimulation(
            source=self.SOURCE,
            concept=concept,
            store=request.store.to_dict() if request.store else {},
            ca_mensuel=rev.ca_ht_mensuel,
            ca_annuel=rev.ca_ht_mensuel * 12,
            ventes_mensuel=rev.nbr_ventes_mensuel,
            ventes_annuel=rev.nbr_ventes_mensuel * 12,
            marge_produit_mensuelle=marge_prod_m,
            marge_produit_annuelle=marge_prod_a,
            cout_mensuel=cost.monthly_cost,
            cout_annuel=cost.annual_cost,
            marge_nette_mensuelle=marge_nette_m,
            marge_nette_annuelle=marge_nette_a,
            capex=cost.capex,
            roi_months=roi,
            revenue=rev.to_dict(),
            costs=cost.to_dict(),
            warnings=list(rev.warnings) + list(cost.warnings),
        )
