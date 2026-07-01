from dataclasses import dataclass
from typing import List
from app.domain.models.simulation import RodSimulationRequest
from app.domain.repositories.reference_repository import ReferenceRepository
from app.domain.rules.traceability import RuleTrace

@dataclass
class CostComputation:
    annual_cost: float
    monthly_cost: float
    capex: float
    opex_monthly: float
    trace: List[RuleTrace]
    warnings: List[str]

class RodCostRules:
    """Coûts ROD : technos, annexes, agencement, maintenance/licences."""
    def __init__(self, reference: ReferenceRepository):
        self.reference = reference

    def compute(self, req: RodSimulationRequest) -> CostComputation:
        concept = req.store.concept
        m_lin = req.store.m_lin
        warnings=[]
        cost_per_m = float(self.reference.get(f"concepts.{concept}.cost_per_m", 0.0) or 0.0)
        fixed_capex = float(self.reference.get(f"concepts.{concept}.fixed_capex", 0.0) or 0.0)
        opex_monthly = float(self.reference.get(f"concepts.{concept}.opex_monthly", 0.0) or 0.0)
        amort_months = float(self.reference.get(f"concepts.{concept}.amort_months", 84.0) or 84.0)
        if not cost_per_m and not fixed_capex and not opex_monthly:
            warnings.append("Références coûts absentes: charger les coûts Excel avant validation production.")
        capex = fixed_capex + cost_per_m * m_lin
        monthly_cost = (capex / amort_months if amort_months else 0.0) + opex_monthly
        annual_cost = monthly_cost * 12
        trace=[RuleTrace(
            rule_id="COST_CAPEX_OPEX_AMORT",
            workbook="ROD - Simulateurs + détail des coûts.xlsx",
            sheet="COUTS - TECHNOS / COUTS - ANNEXES / COUTS - AGENCEMENT",
            cells=["à valider cellule par cellule"],
            excel_formula=None,
            business_description="Coûts d'achat/installation + coûts récurrents + amortissement mensuel.",
            python_method="RodCostRules.compute",
            status="structure_ready_requires_excel_validation",
        )]
        return CostComputation(annual_cost, monthly_cost, capex, opex_monthly, trace, warnings)
