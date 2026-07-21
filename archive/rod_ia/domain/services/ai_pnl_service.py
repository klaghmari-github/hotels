"""Pipeline IA : ventes prédites → % → CA → marge produit → coûts → marge nette."""

from __future__ import annotations

from rod_ia.domain.models.simulation import MonthlyProjection, RodSimulationRequest, SimulationResult
from rod_ia.domain.rules.cost_rules import RodCostRules
from rod_ia.domain.rules.revenue_rules import RodRevenueRules
from rod_ia.domain.services.ai_predictor import AIRodRevenuePredictor


class AIPnlService:
    """Enrichit les prédictions IA avec le P&L complet et les étapes du pipeline."""

    def __init__(
        self,
        predictor: AIRodRevenuePredictor,
        revenue_rules: RodRevenueRules,
        cost_rules: RodCostRules,
    ) -> None:
        self._predictor = predictor
        self._revenue = revenue_rules
        self._cost = cost_rules

    def predict_pnl(self, request: RodSimulationRequest, concept: str) -> SimulationResult:
        store = request.store
        if store is None:
            raise ValueError("store requis pour le pipeline IA")

        pipeline: list[dict] = []
        warnings: list[str] = list(self._predictor.load_warnings)

        raw = self._predictor.predict_raw(request)
        ventes_monthly = list(raw["ventes_monthly"])
        ca_monthly = list(raw["ca_monthly"])
        model_available = raw["model_available"]

        pipeline.append(
            {
                "step": "predict_ventes",
                "label": "Prédiction ventes IA (targets t_*)",
                "monthly_ventes": ventes_monthly,
                "model_available": model_available,
            }
        )

        if not model_available or sum(ca_monthly) == 0:
            rod_rev = self._revenue.compute(request, concept)
            ca_monthly = [rod_rev.ca_ht_mensuel_base] * 12
            ventes_monthly = [rod_rev.nbr_ventes_mensuel_base] * 12
            warnings.append("Modèle IA indisponible — fallback ROD (mois moyen).")
            pipeline[-1]["fallback"] = "ROD_EXCEL_RULES"
            pipeline[-1]["monthly_ventes"] = ventes_monthly

        total_ventes = sum(ventes_monthly)
        ventes_pct = [
            (v / total_ventes * 100.0) if total_ventes > 0 else 0.0 for v in ventes_monthly
        ]
        pipeline.append(
            {
                "step": "ventes_to_pct",
                "label": "Conversion ventes → % mensuels",
                "monthly_pct": ventes_pct,
                "annual_ventes": total_ventes,
            }
        )

        ca_annuel = sum(ca_monthly)
        ca_mensuel_moyen = ca_annuel / 12 if ca_annuel else 0.0
        pipeline.append(
            {
                "step": "pct_to_ca",
                "label": "CA HT mensuel (profil 12 mois)",
                "monthly_ca": ca_monthly,
                "ca_mensuel_moyen": ca_mensuel_moyen,
                "ca_annuel": ca_annuel,
                "source": "AI_MODEL" if model_available and sum(raw["ca_monthly"]) > 0 else "ROD_EXCEL_RULES",
            }
        )

        revenue = self._revenue.compute(request, concept)
        coef_fb = float(revenue.breakdown.get("margin_fb_coef", 2.6))
        coef_nf = float(revenue.breakdown.get("margin_nf_coef", 1.45))
        ca_fb_base = float(revenue.breakdown.get("ca_fb_ht_mensuel", 0.0))
        ca_nf_base = float(revenue.breakdown.get("ca_nf_ht_mensuel", 0.0))
        rod_ca_base = revenue.ca_ht_mensuel_base or 1.0

        marge_produit_monthly: list[float] = []
        for ca in ca_monthly:
            ratio = ca / rod_ca_base if rod_ca_base else 1.0
            marge_produit_monthly.append(
                RodRevenueRules._marge_produit_excel(
                    ca_fb_base * ratio,
                    ca_nf_base * ratio,
                    coef_fb,
                    coef_nf,
                )
            )

        pipeline.append(
            {
                "step": "ca_to_marge_produit",
                "label": "Marge produit (E132/E133 Excel)",
                "margin_fb_coef": coef_fb,
                "margin_nf_coef": coef_nf,
                "monthly_marge_produit": marge_produit_monthly,
            }
        )

        cost = self._cost.compute(request, concept)
        pipeline.append(
            {
                "step": "apply_couts",
                "label": "Coûts mensuels (technos + annexes + agencement)",
                "techno_monthly": cost.techno_monthly,
                "annexes_monthly": cost.annexes_monthly,
                "agencement_monthly": cost.agencement_monthly,
                "monthly_cost": cost.monthly_cost,
                "capex": cost.capex,
            }
        )

        monthly: list[MonthlyProjection] = []
        for month in range(1, 13):
            idx = month - 1
            mp = marge_produit_monthly[idx]
            mc = cost.monthly_cost
            monthly.append(
                MonthlyProjection(
                    month=month,
                    ca=ca_monthly[idx],
                    nbr_ventes=ventes_monthly[idx],
                    marge_produit=mp,
                    cost=mc,
                    marge_nette=mp - mc,
                    margin=mp - mc,
                )
            )

        ventes_annuel = sum(ventes_monthly)
        ventes_mensuel_moyen = ventes_annuel / 12 if ventes_annuel else 0.0
        marge_produit_annuelle = sum(marge_produit_monthly)
        marge_nette_annuelle = marge_produit_annuelle - cost.annual_cost

        pipeline.append(
            {
                "step": "marge_nette",
                "label": "Marge nette annuelle",
                "marge_produit_annuelle": marge_produit_annuelle,
                "cout_annuel": cost.annual_cost,
                "marge_nette_annuelle": marge_nette_annuelle,
            }
        )

        roi_months = None
        if marge_nette_annuelle > 0 and cost.capex > 0:
            roi_months = cost.capex / (marge_nette_annuelle / 12)

        breakdown = {
            **revenue.breakdown,
            "display_mode": "monthly_profile",
            "ca_mensuel_moyen": ca_mensuel_moyen,
            "techno_monthly": cost.techno_monthly,
            "annexes_monthly": cost.annexes_monthly,
            "agencement_monthly": cost.agencement_monthly,
            "capex": cost.capex,
            "marge_produit_annuelle": marge_produit_annuelle,
            "marge_nette_annuelle": marge_nette_annuelle,
        }

        return SimulationResult(
            source="AI_PNL_PIPELINE",
            concept=concept,
            m_lin=store.m_lin,
            ca_annuel=ca_annuel,
            nbr_ventes_annuel=ventes_annuel,
            ca_mensuel_moyen=ca_mensuel_moyen,
            nbr_ventes_mensuel_moyen=ventes_mensuel_moyen,
            marge_annuelle=marge_nette_annuelle,
            cout_annuel=cost.annual_cost,
            roi_months=roi_months,
            monthly=monthly,
            store_config=store.to_dict(),
            breakdown=breakdown,
            warnings=warnings + revenue.warnings + cost.warnings,
            trace=[entry.to_dict() for entry in revenue.trace + cost.trace],
            pipeline=pipeline,
        )