"""Règles de revenus ROD — enchaînement Excel Règles 1→4 + impact TO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from rod_ia.domain.models.simulation import MonthlyProjection, RodSimulationRequest
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.excel_category_coeffs import (
    RULE3_BASELINE_FB,
    RULE3_BASELINE_NF,
    RULE3_FB_COEFFS,
    RULE3_NFB_COEFFS,
)
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
    """Reproduit l'enchaînement Excel : clients, mix, catégories, m_lin, impact TO.

    Règle 1 : ``O34 = (M31×E34)/C31`` — scaling par clients acheteurs.
    Règle 2 : ajustement par pas de 10 % d'écart au mix pilote (``E51``, ``E52``).
    Règle 3 : ``O94/O95`` — bonus/malus selon cumul coefficients catégories.
    Règle 4 : ``O112/O113`` — ajustement par mètre linéaire (``E112 = E34/F9``).
    """

    CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")
    JOURS_MOIS = 30.5
    MIX_STEP = 0.10

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

    @staticmethod
    def _apply_to_impact(
        ca_fb: float, ca_nf: float, to_delta: float, impact_per_point: float
    ) -> Tuple[float, float]:
        to_impact = (to_delta / 0.01) * impact_per_point
        total = ca_fb + ca_nf
        if total <= 0:
            half = to_impact / 2.0
            return ca_fb + half, ca_nf + half
        share_fb = ca_fb / total
        return ca_fb + to_impact * share_fb, ca_nf + to_impact * (1.0 - share_fb)

    @staticmethod
    def _rule1_scale_by_clients(
        ca_fb: float, ca_nf: float, clients_hotel: float, clients_pilote: float
    ) -> Tuple[float, float, float]:
        factor = clients_hotel / clients_pilote if clients_pilote else 1.0
        return ca_fb * factor, ca_nf * factor, factor

    @staticmethod
    def _rule2_mix_adjust(
        ca_fb: float,
        ca_nf: float,
        *,
        user_mix_fb: float,
        user_mix_nf: float,
        ref_mix_fb: float,
        ref_mix_nf: float,
        ca_fb_ref: float,
        ca_nf_ref: float,
    ) -> Tuple[float, float, float, float]:
        unit_fb = (ca_fb_ref * RodRevenueRules.MIX_STEP) / ref_mix_fb if ref_mix_fb else 0.0
        unit_nf = (ca_nf_ref * RodRevenueRules.MIX_STEP) / ref_mix_nf if ref_mix_nf else 0.0
        steps_fb = (user_mix_fb - ref_mix_fb) * 10.0
        steps_nf = (user_mix_nf - ref_mix_nf) * 10.0
        return (
            ca_fb + unit_fb * steps_fb,
            ca_nf + unit_nf * steps_nf,
            steps_fb,
            steps_nf,
        )

    @staticmethod
    def _rule3_category_adjust(
        ca_fb: float, ca_nf: float, cumul_fb: float, cumul_nf: float
    ) -> Tuple[float, float, float, float]:
        """Ajustement relatif au pilote « toutes catégories » (E34/E35 déjà plein assortiment)."""
        delta_fb = cumul_fb - RULE3_BASELINE_FB
        delta_nf = cumul_nf - RULE3_BASELINE_NF
        if ca_fb < 0:
            ca_fb = ca_fb - ca_fb * delta_fb
        else:
            ca_fb = ca_fb + ca_fb * delta_fb
        if ca_nf < 0:
            ca_nf = ca_nf - ca_nf * delta_nf
        else:
            ca_nf = ca_nf + ca_nf * delta_nf
        return ca_fb, ca_nf, delta_fb, delta_nf

    @staticmethod
    def _rule4_m_lin_adjust(
        ca_fb: float,
        ca_nf: float,
        *,
        m_lin: float,
        pivot_m_lin: float,
        ca_fb_ref: float,
        ca_nf_ref: float,
    ) -> Tuple[float, float, float]:
        diff = m_lin - pivot_m_lin
        abs_diff = abs(diff)
        unit_fb = ca_fb_ref / pivot_m_lin if pivot_m_lin else 0.0
        unit_nf = ca_nf_ref / pivot_m_lin if pivot_m_lin else 0.0
        if diff < 0:
            return (
                ca_fb - unit_fb * abs_diff,
                ca_nf - unit_nf * abs_diff,
                diff,
            )
        return (
            ca_fb + unit_fb * abs_diff,
            ca_nf + unit_nf * abs_diff,
            diff,
        )

    @staticmethod
    def _cumul_rule3(client_needs: Dict[str, bool]) -> Tuple[float, float]:
        cumul_fb = sum(
            coeff
            for key, coeff in RULE3_FB_COEFFS.items()
            if client_needs.get(key, True)
        )
        cumul_nf = sum(
            coeff
            for key, coeff in RULE3_NFB_COEFFS.items()
            if client_needs.get(key, True)
        )
        return cumul_fb, cumul_nf

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
        ca_ht_ref_total = ca_fb_ref + ca_nf_ref
        ventes_ref = float(self._reference.get(f"{key}.base_monthly_sales", 0.0) or 0.0)
        margin_fb = float(self._reference.get(f"{key}.margin_fb_pct", 2.6) or 2.6)
        margin_nf = float(self._reference.get(f"{key}.margin_nf_pct", 1.45) or 1.45)
        ref_mix_fb = float(self._reference.get(f"{key}.mix_fb", 0.7) or 0.7)
        ref_mix_nf = float(self._reference.get(f"{key}.mix_nf", 0.3) or 0.3)

        user_mix_fb = float(store.mix.fb_share)
        user_mix_nf = float(store.mix.non_fb_share)
        mix_total = user_mix_fb + user_mix_nf
        if mix_total > 0:
            user_mix_fb /= mix_total
            user_mix_nf /= mix_total

        excluded = set(store.excluded_categories or [])
        mix_customized = bool(excluded) or (
            abs(user_mix_fb - ref_mix_fb) > 0.02
            or abs(user_mix_nf - ref_mix_nf) > 0.02
        )
        effective_mix_fb = user_mix_fb if mix_customized else ref_mix_fb
        effective_mix_nf = user_mix_nf if mix_customized else ref_mix_nf

        if ca_ht_ref_total > 0:
            split_fb = ca_fb_ref / ca_ht_ref_total
            split_nf = ca_nf_ref / ca_ht_ref_total
        else:
            split_fb, split_nf = ref_mix_fb, ref_mix_nf
        mix_fb, mix_nf = split_fb, split_nf

        impact_to = float(
            self._reference.get("impact_to.ht_per_0_01_to", 9.233974) or 9.233974
        )

        clients_pilote = self._clients_mois(pivot_nb, pivot_to, pivot_guests)
        clients_hotel = operating.clients_mois
        to_delta = operating.taux_occupation - pivot_to

        ca_fb, ca_nf = self._apply_to_impact(ca_fb_ref, ca_nf_ref, to_delta, impact_to)
        to_impact = (to_delta / 0.01) * impact_to

        ca_fb, ca_nf, client_factor = self._rule1_scale_by_clients(
            ca_fb, ca_nf, clients_hotel, clients_pilote
        )

        ca_fb, ca_nf, steps_fb, steps_nf = self._rule2_mix_adjust(
            ca_fb,
            ca_nf,
            user_mix_fb=effective_mix_fb,
            user_mix_nf=effective_mix_nf,
            ref_mix_fb=ref_mix_fb,
            ref_mix_nf=ref_mix_nf,
            ca_fb_ref=ca_fb_ref,
            ca_nf_ref=ca_nf_ref,
        )

        client_needs = request.client_profile.client_needs
        cumul_fb, cumul_nf = self._cumul_rule3(client_needs)
        ca_fb, ca_nf, delta_fb, delta_nf = self._rule3_category_adjust(
            ca_fb, ca_nf, cumul_fb, cumul_nf
        )

        ca_fb, ca_nf, m_lin_diff = self._rule4_m_lin_adjust(
            ca_fb,
            ca_nf,
            m_lin=store.m_lin,
            pivot_m_lin=pivot_m_lin,
            ca_fb_ref=ca_fb_ref,
            ca_nf_ref=ca_nf_ref,
        )
        m_lin_factor = store.m_lin / pivot_m_lin if pivot_m_lin else 1.0

        ca_ht_mensuel = max(ca_fb + ca_nf, 0.0)
        ca_fb_mensuel = ca_fb if ca_ht_mensuel else 0.0
        ca_nf_mensuel = ca_nf if ca_ht_mensuel else 0.0

        taux_acheteur = ventes_ref / clients_pilote if clients_pilote else 0.0
        nbr_ventes_mensuel = taux_acheteur * clients_hotel

        marge_produit_mensuelle = self._marge_produit_excel(
            ca_fb_mensuel, ca_nf_mensuel, margin_fb, margin_nf
        )

        trace.extend(
            [
                RuleTrace(
                    rule_id="REV_RULE1_CLIENTS",
                    workbook="ROD - Simulateurs + détail des coûts.xlsx",
                    sheet=f"SIMULATEUR {concept}",
                    cells=["C17", "C19", "C21", "O34", "O35"],
                    excel_formula="O34=(M31×E34)/C31 ; ventes=M17×C21",
                    business_description="Scaling CA par clients acheteurs (Règle 1).",
                    python_method="RodRevenueRules._rule1_scale_by_clients",
                    status="implemented_from_documentation",
                ),
                RuleTrace(
                    rule_id="REV_RULE2_MIX_10PCT",
                    workbook="ROD - Simulateurs + détail des coûts.xlsx",
                    sheet=f"SIMULATEUR {concept}",
                    cells=["E51", "E52", "O43", "O47", "O44", "O48"],
                    excel_formula="O44=E51×(écart_mix_fb×10)",
                    business_description="Ajustement mix F&B/NON-F&B par pas de 10 %.",
                    python_method="RodRevenueRules._rule2_mix_adjust",
                    status="implemented_from_documentation",
                ),
                RuleTrace(
                    rule_id="REV_RULE3_CATEGORIES",
                    workbook="ROD - Simulateurs + détail des coûts.xlsx",
                    sheet=f"SIMULATEUR {concept}",
                    cells=["H64:H70", "O64:O70", "O94", "O95"],
                    excel_formula="O94=O51+O51×H75 si O51≥0",
                    business_description="Bonus/malus catégories sélectionnées (Règle 3).",
                    python_method="RodRevenueRules._rule3_category_adjust",
                    status="implemented_from_documentation",
                ),
                RuleTrace(
                    rule_id="REV_RULE4_M_LIN",
                    workbook="ROD - Simulateurs + détail des coûts.xlsx",
                    sheet=f"SIMULATEUR {concept}",
                    cells=["E112", "E113", "O108", "O112", "O113"],
                    excel_formula="O112=O94±(E34/F9)×|Δm_lin|",
                    business_description="Ajustement CA par mètre linéaire (Règle 4).",
                    python_method="RodRevenueRules._rule4_m_lin_adjust",
                    status="implemented_from_documentation",
                ),
                RuleTrace(
                    rule_id="REV_IMPACT_TO",
                    workbook="ROD - Simulateurs + détail des coûts.xlsx",
                    sheet="REVENUS - IMPACT TO",
                    cells=["impact 9,234 €/0,01 TO"],
                    excel_formula="impact_to.ht_per_0_01_to",
                    business_description="Ajustement additif du CA HT selon écart TO pilote.",
                    python_method="RodRevenueRules._apply_to_impact",
                    status="implemented_from_documentation",
                ),
                RuleTrace(
                    rule_id="REV_EXCEL_MARGE_PRODUIT",
                    workbook="ROD - Simulateurs + détail des coûts.xlsx",
                    sheet=f"SIMULATEUR {concept}",
                    cells=["E132", "E133", "E134"],
                    excel_formula="E132 = E120 - (E120/E128) ; E133 = E121 - (E121/E129)",
                    business_description="Marge produit mensuelle (mois moyen pilote).",
                    python_method="RodRevenueRules._marge_produit_excel",
                    status="implemented_from_documentation",
                ),
            ]
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
                "m_lin_diff": m_lin_diff,
                "mix_steps_fb": steps_fb,
                "mix_steps_nf": steps_nf,
                "cumul_rule3_fb": cumul_fb,
                "cumul_rule3_nf": cumul_nf,
                "rule3_delta_fb": delta_fb,
                "rule3_delta_nf": delta_nf,
                "mix_customized": mix_customized,
                "excluded_gammes": sorted(excluded),
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