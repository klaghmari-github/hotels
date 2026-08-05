"""
Simulateur unitaire : revenus + coûts → marge pour un concept.

  RevenueRules.compute  → CA, ventes, marge produit
  CostRules.compute     → techno, annexes, agencement
  ici                   → marge nette, amortissement, ConceptSimulation

Ordre (simulateur_rules.html §12) :
  R1→R2→R3→R4 → marge produits → coûts → marge nette + amort
  SI marge nette < 0 ou CA < 0 → status « not_profitable »
"""

from __future__ import annotations

from accor.user.models import ConceptSimulation, SimulationRequest
from accor.user.rules.costs import CostRules
from accor.user.rules.revenue import RevenueRules


class RodSimulator:
    """Agrège revenus et coûts pour un concept (iso Excel)."""

    SOURCE = "ROD_RULES"

    def __init__(self, revenue: RevenueRules, costs: CostRules) -> None:
        self.revenue = revenue
        self.costs = costs

    def simulate(self, request: SimulationRequest, concept: str) -> ConceptSimulation:
        concept = concept.upper()
        rev = self.revenue.compute(request, concept)
        cost = self.costs.compute(request, concept)

        ca_m = float(rev.ca_ht_mensuel or 0.0)
        ca_fb = float(rev.ca_fb_mensuel or 0.0)
        ca_nfb = float(rev.ca_nf_mensuel or 0.0)
        marge_prod_m = float(rev.marge_produit_mensuelle or 0.0)
        marge_prod_a = marge_prod_m * 12.0
        cout_m = float(cost.monthly_cost or 0.0)
        cout_a = float(cost.annual_cost or 0.0)
        marge_nette_m = marge_prod_m - cout_m
        marge_nette_a = marge_prod_a - cout_a
        cost_60 = float(getattr(cost, "cost_over_60m", 0.0) or 0.0)

        # Spec §11
        not_profitable = marge_nette_m < 0 or ca_m < 0 or ca_fb < 0 or ca_nfb < 0
        status = "not_profitable" if not_profitable else "ok"

        amort_months: float | None = None
        amort_years: float | None = None
        taux_marge: float | None = None
        roi: float | None = None

        if not not_profitable and marge_nette_m > 0:
            amort_months = cost_60 / marge_nette_m if cost_60 > 0 else None
            amort_years = (amort_months / 12.0) if amort_months is not None else None
            taux_marge = marge_nette_m / ca_m if ca_m > 0 else None
            if cost.capex > 0:
                roi = cost.capex / marge_nette_m

        return ConceptSimulation(
            source=self.SOURCE,
            concept=concept,
            store=request.store.to_dict() if request.store else {},
            ca_mensuel=ca_m,
            ca_annuel=ca_m * 12.0,
            ca_fb_mensuel=ca_fb,
            ca_nfb_mensuel=ca_nfb,
            ventes_mensuel=float(rev.nbr_ventes_mensuel or 0.0),
            ventes_annuel=float(rev.nbr_ventes_mensuel or 0.0) * 12.0,
            marge_produit_mensuelle=marge_prod_m,
            marge_produit_annuelle=marge_prod_a,
            cout_mensuel=cout_m,
            cout_annuel=cout_a,
            marge_nette_mensuelle=marge_nette_m,
            marge_nette_annuelle=marge_nette_a,
            capex=float(cost.capex or 0.0),
            roi_months=roi,
            revenue=rev.to_dict(),
            costs=cost.to_dict(),
            warnings=list(rev.warnings) + list(cost.warnings),
            techno_monthly=float(cost.techno_monthly or 0.0),
            annexes_monthly=float(cost.annexes_monthly or 0.0),
            agencement_monthly=float(cost.agencement_monthly or 0.0),
            cost_over_60m=cost_60,
            status=status,
            amort_months=amort_months,
            amort_years=amort_years,
            taux_marge=taux_marge,
        )
