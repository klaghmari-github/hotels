from dataclasses import dataclass
from typing import Dict, List
from app.domain.models.simulation import RodSimulationRequest, MonthlyProjection
from app.domain.repositories.reference_repository import ReferenceRepository
from app.domain.rules.traceability import RuleTrace

@dataclass
class RevenueComputation:
    monthly: List[MonthlyProjection]
    breakdown: Dict[str, float]
    trace: List[RuleTrace]
    warnings: List[str]

class RodRevenueRules:
    """Règles de revenus ROD.

    À valider contre les feuilles : SIMULATEUR SIMPLY/LIBERTY/CONNECTED,
    REVENUS - MIX & MARGES, REVENUS - IMPACT TO.
    """
    def __init__(self, reference: ReferenceRepository):
        self.reference = reference

    def compute(self, req: RodSimulationRequest) -> RevenueComputation:
        op = req.operating
        store = req.store
        trace: list[RuleTrace] = []
        warnings: list[str] = []

        base_monthly_ca = float(self.reference.get(f"concepts.{store.concept}.base_monthly_ca", 0.0) or 0.0)
        base_monthly_sales = float(self.reference.get(f"concepts.{store.concept}.base_monthly_sales", 0.0) or 0.0)
        pivot_m_lin = float(self.reference.get(f"concepts.{store.concept}.pivot_m_lin", 1.0) or 1.0)
        pivot_clients_mois = float(self.reference.get(f"concepts.{store.concept}.pivot_clients_mois", 0.0) or 0.0)

        if base_monthly_ca == 0:
            warnings.append("Référence base_monthly_ca absente: résultat revenu à zéro tant que les constantes Excel/recalculées ne sont pas chargées.")

        mlin_factor = store.m_lin / pivot_m_lin if pivot_m_lin else 1.0
        client_factor = (op.clients_mois / pivot_clients_mois) if pivot_clients_mois else 1.0

        trace.append(RuleTrace(
            rule_id="REV_MLIN_SCALE",
            workbook="ROD - Simulateurs + détail des coûts.xlsx",
            sheet="SIMULATEUR *",
            cells=["à valider: mètre linéaire pivot / mètre linéaire projet"],
            excel_formula=None,
            business_description="Projection des revenus selon les mètres linéaires choisis.",
            python_method="RodRevenueRules.compute",
            status="structure_ready_requires_excel_validation",
        ))
        trace.append(RuleTrace(
            rule_id="REV_CLIENTS_MONTH",
            workbook="ROD - Simulateurs + détail des coûts.xlsx",
            sheet="SIMULATEUR *",
            cells=["à valider: clients hébergés par mois"],
            excel_formula="clients_mois = nb_chambres * taux_occupation * guests_per_chambre * 30.5",
            business_description="Calcul des clients mensuels à partir des chambres, TO et guests/chambre.",
            python_method="HotelOperatingState",
            status="implemented_formula_to_validate",
        ))

        seasonality = self.reference.get("seasonality.monthly", {}) or {}
        monthly=[]
        for month in range(1, 13):
            s = float(seasonality.get(f"m{month:02d}", 1.0))
            ca = base_monthly_ca * mlin_factor * client_factor * s
            sales = base_monthly_sales * mlin_factor * client_factor * s
            monthly.append(MonthlyProjection(month=month, ca=ca, nbr_ventes=sales))

        return RevenueComputation(
            monthly=monthly,
            breakdown={"F&B": store.mix.fb_share, "Non-F&B": store.mix.non_fb_share},
            trace=trace,
            warnings=warnings,
        )
