"""Règles de revenus ROD — formules Excel (SIMULATEUR * + IMPACT TO + Règle 1 clients)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from rod_ia.domain.models.simulation import MonthlyProjection, RodSimulationRequest
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.traceability import RuleTrace


@dataclass
class RevenueComputation:
    monthly: List[MonthlyProjection]
    breakdown: Dict[str, float]
    trace: List[RuleTrace]
    warnings: List[str]
    ca_ht_mensuel_base: float = 0.0
    nbr_ventes_mensuel_base: float = 0.0


class RodRevenueRules:
    """Reproduit la logique pilote Excel : clients hébergés, m_lin, impact TO, marges.

    Règle 1 Excel : ``C21 = C19/C17`` puis ventes = taux acheteur × clients hôtel.
    Les clients/mois intègrent nb chambres × TO × guests/ch (C17 = C16 × 30.5).
    """

    CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")
    JOURS_MOIS = 30.5

    def __init__(self, reference: ReferenceRepository) -> None:
        self._reference = reference

    @staticmethod
    def _marge_produit_excel(ca_fb: float, ca_nf: float, coef_fb: float, coef_nf: float) -> float:
        marge_fb = ca_fb - (ca_fb / coef_fb) if coef_fb else 0.0
        marge_nf = ca_nf - (ca_nf / coef_nf) if coef_nf else 0.0
        return marge_fb + marge_nf

    @staticmethod
    def _clients_mois(nb_chambres: float, to: float, guests: float) -> float:
        return nb_chambres * to * guests * RodRevenueRules.JOURS_MOIS

    def compute(self, request: RodSimulationRequest, concept: str) -> RevenueComputation:
        operating = request.operating
        store = request.store
        if store is None:
            raise ValueError("store requis pour le calcul revenus (fourni par l'orchestrateur)")

        trace: list[RuleTrace] = []
        warnings: list[str] = []
        key = f"concepts.{concept}"

        pivot_nb = float(self._reference.get(f"{key}.pivot_nb_chambres", 129) or 129)
        pivot_guests = float(self._reference.get(f"{key}.pivot_guests_per_chambre", 1.7) or 1.7)
        pivot_m_lin = float(self._reference.get(f"{key}.pivot_m_lin", 1.0) or 1.0)
        pivot_to = float(self._reference.get(f"{key}.pivot_to", 0.75) or 0.75)
        ca_fb_ref = float(self._reference.get(f"{key}.base_monthly_ca_fb", 0.0) or 0.0)
        ca_nf_ref = float(self._reference.get(f"{key}.base_monthly_ca_nf", 0.0) or 0.0)
        ventes_ref = float(self._reference.get(f"{key}.base_monthly_sales", 0.0) or 0.0)
        margin_fb = float(self._reference.get(f"{key}.margin_fb_pct", 2.6) or 2.6)
        margin_nf = float(self._reference.get(f"{key}.margin_nf_pct", 1.45) or 1.45)
        mix_fb = float(self._reference.get(f"{key}.mix_fb", store.mix.fb_share) or store.mix.fb_share)
        mix_nf = float(self._reference.get(f"{key}.mix_nf", store.mix.non_fb_share) or store.mix.non_fb_share)
        impact_to = float(
            self._reference.get("impact_to.ht_per_0_01_to", 9.233974) or 9.233974
        )

        clients_pilote = self._clients_mois(pivot_nb, pivot_to, pivot_guests)
        clients_hotel = operating.clients_mois
        client_factor = clients_hotel / clients_pilote if clients_pilote else 1.0

        m_lin_factor = store.m_lin / pivot_m_lin if pivot_m_lin else 1.0
        to_delta = operating.taux_occupation - pivot_to
        to_impact = (to_delta / 0.01) * impact_to
        ca_ht_ref_total = ca_fb_ref + ca_nf_ref

        if ca_ht_ref_total > 0:
            ca_scaled = (ca_ht_ref_total + to_impact) * m_lin_factor * client_factor
            ca_fb_mensuel = ca_scaled * (ca_fb_ref / ca_ht_ref_total)
            ca_nf_mensuel = ca_scaled * (ca_nf_ref / ca_ht_ref_total)
        else:
            ca_fb_mensuel = 0.0
            ca_nf_mensuel = 0.0

        ca_ht_mensuel = ca_fb_mensuel + ca_nf_mensuel
        taux_acheteur = ventes_ref / clients_pilote if clients_pilote else 0.0
        nbr_ventes_mensuel = taux_acheteur * clients_hotel * m_lin_factor
        marge_produit_mensuelle = self._marge_produit_excel(
            ca_fb_mensuel, ca_nf_mensuel, margin_fb, margin_nf
        )

        trace.append(
            RuleTrace(
                rule_id="REV_EXCEL_CLIENTS_MLIN_TO",
                workbook="ROD - Simulateurs + détail des coûts.xlsx",
                sheet=f"SIMULATEUR {concept}",
                cells=["C17", "C19", "C21", "REVENUS - IMPACT TO"],
                excel_formula="ventes = (C19/C17_pilote) × C17_hôtel × (m_lin/m_lin_pilote)",
                business_description="Scaling par clients hébergés, m_lin et impact TO.",
                python_method="RodRevenueRules.compute",
                status="implemented_from_documentation",
            )
        )
        trace.append(
            RuleTrace(
                rule_id="REV_EXCEL_MARGE_PRODUIT",
                workbook="ROD - Simulateurs + détail des coûts.xlsx",
                sheet=f"SIMULATEUR {concept}",
                cells=["E132", "E133", "E134"],
                excel_formula="E132 = E120 - (E120/E128) ; E133 = E121 - (E121/E129)",
                business_description="Marge produit mensuelle (mois moyen pilote).",
                python_method="RodRevenueRules._marge_produit_excel",
                status="implemented_from_documentation",
            )
        )

        monthly: list[MonthlyProjection] = []
        for month in range(1, 13):
            monthly.append(
                MonthlyProjection(
                    month=month,
                    ca=ca_ht_mensuel,
                    nbr_ventes=nbr_ventes_mensuel,
                    marge_produit=marge_produit_mensuelle,
                )
            )

        return RevenueComputation(
            monthly=monthly,
            breakdown={
                "display_mode": "monthly_average",
                "ca_fb_ht_mensuel": ca_fb_mensuel,
                "ca_nf_ht_mensuel": ca_nf_mensuel,
                "mix_fb": mix_fb,
                "mix_nf": mix_nf,
                "margin_fb_coef": margin_fb,
                "margin_nf_coef": margin_nf,
                "marge_produit_mensuelle": marge_produit_mensuelle,
                "m_lin_factor": m_lin_factor,
                "client_factor": client_factor,
                "clients_mois_hotel": clients_hotel,
                "clients_mois_pilote": clients_pilote,
                "taux_acheteur_pilote": taux_acheteur,
                "to_impact": to_impact,
                "nb_chambres": float(operating.nb_chambres),
                "taux_occupation": operating.taux_occupation,
                "guests_per_chambre": operating.guests_per_chambre,
            },
            trace=trace,
            warnings=warnings,
            ca_ht_mensuel_base=ca_ht_mensuel,
            nbr_ventes_mensuel_base=nbr_ventes_mensuel,
        )