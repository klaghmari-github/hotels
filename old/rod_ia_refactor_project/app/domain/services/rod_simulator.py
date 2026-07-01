from app.domain.models.simulation import RodSimulationRequest, SimulationResult
from app.domain.rules.revenue_rules import RodRevenueRules
from app.domain.rules.cost_rules import RodCostRules
from app.domain.rules.recommendation_rules import RodRecommendationRules

class RodSimulator:
    """Simulateur ROD déterministe, traçable et extensible."""
    def __init__(self, revenue_rules: RodRevenueRules, cost_rules: RodCostRules, recommendation_rules: RodRecommendationRules | None = None):
        self.revenue_rules = revenue_rules
        self.cost_rules = cost_rules
        self.recommendation_rules = recommendation_rules

    def simulate(self, req: RodSimulationRequest) -> SimulationResult:
        rev = self.revenue_rules.compute(req)
        cost = self.cost_rules.compute(req)
        ca_annuel = sum(m.ca for m in rev.monthly)
        nbr_ventes_annuel = sum(m.nbr_ventes for m in rev.monthly)
        marge_annuelle = ca_annuel - cost.annual_cost  # peut être négative
        roi_months = None
        if marge_annuelle > 0 and cost.capex > 0:
            roi_months = cost.capex / (marge_annuelle / 12)
        monthly=[]
        for m in rev.monthly:
            m.cost = cost.monthly_cost
            m.margin = m.ca - cost.monthly_cost
            monthly.append(m)
        return SimulationResult(
            source="ROD_EXCEL_RULES",
            concept=req.store.concept,
            m_lin=req.store.m_lin,
            ca_annuel=ca_annuel,
            nbr_ventes_annuel=nbr_ventes_annuel,
            marge_annuelle=marge_annuelle,
            cout_annuel=cost.annual_cost,
            roi_months=roi_months,
            monthly=monthly,
            breakdown=rev.breakdown,
            warnings=rev.warnings + cost.warnings,
            trace=[t.to_dict() for t in rev.trace + cost.trace],
        )
