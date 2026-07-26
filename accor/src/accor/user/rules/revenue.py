"""
Règles de **revenus** ROD (sans coûts).

Enchaînement Excel SIMULATEUR * :
  impact TO → Règle 1 (clients) → Règle 2 (mix) → Règle 3 (catégories) → Règle 4 (m_lin)
  puis marge produit (coefs J9/J10).

Isolé volontairement de ``CostRules`` pour permettre un swap IA sur les seuls
revenus tout en réutilisant le même moteur de coûts.
"""

from __future__ import annotations

from typing import Tuple

from accor.user.models import RevenueResult, SimulationRequest
from accor.user.reference import RodReference
from accor.user.rules.coeffs import (
    RULE3_BASELINE_FB,
    RULE3_BASELINE_NF,
    RULE3_FB_COEFFS,
    RULE3_NFB_COEFFS,
)


class RevenueRules:
    """Moteur déterministe de CA HT / ventes / marge produit."""

    MIX_STEP = 0.10

    def __init__(self, reference: RodReference) -> None:
        self._ref = reference

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def marge_produit(ca_fb: float, ca_nf: float, coef_fb: float, coef_nf: float) -> float:
        """Excel E132/E133 : marge = CA − CA/coef."""
        m_fb = ca_fb - (ca_fb / coef_fb) if coef_fb else 0.0
        m_nf = ca_nf - (ca_nf / coef_nf) if coef_nf else 0.0
        return m_fb + m_nf

    @staticmethod
    def apply_to_impact(
        ca_fb: float, ca_nf: float, to_delta: float, impact_per_point: float
    ) -> Tuple[float, float]:
        to_impact = (to_delta / 0.01) * impact_per_point
        total = ca_fb + ca_nf
        if total <= 0:
            half = to_impact / 2.0
            return ca_fb + half, ca_nf + half
        share = ca_fb / total
        return ca_fb + to_impact * share, ca_nf + to_impact * (1.0 - share)

    @staticmethod
    def rule1_clients(
        ca_fb: float, ca_nf: float, clients_hotel: float, clients_pilote: float
    ) -> Tuple[float, float, float]:
        factor = clients_hotel / clients_pilote if clients_pilote else 1.0
        return ca_fb * factor, ca_nf * factor, factor

    @classmethod
    def rule2_mix(
        cls,
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
        unit_fb = (ca_fb_ref * cls.MIX_STEP) / ref_mix_fb if ref_mix_fb else 0.0
        unit_nf = (ca_nf_ref * cls.MIX_STEP) / ref_mix_nf if ref_mix_nf else 0.0
        steps_fb = (user_mix_fb - ref_mix_fb) * 10.0
        steps_nf = (user_mix_nf - ref_mix_nf) * 10.0
        return ca_fb + unit_fb * steps_fb, ca_nf + unit_nf * steps_nf, steps_fb, steps_nf

    @staticmethod
    def rule3_categories(
        ca_fb: float, ca_nf: float, cumul_fb: float, cumul_nf: float
    ) -> Tuple[float, float, float, float]:
        """Applique le delta de cumuls besoins vs baseline Excel (× CA canal)."""
        delta_fb = cumul_fb - RULE3_BASELINE_FB
        delta_nf = cumul_nf - RULE3_BASELINE_NF
        ca_fb = ca_fb * (1.0 + delta_fb)
        ca_nf = ca_nf * (1.0 + delta_nf)
        return ca_fb, ca_nf, delta_fb, delta_nf

    @staticmethod
    def rule4_m_lin(
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
            return ca_fb - unit_fb * abs_diff, ca_nf - unit_nf * abs_diff, diff
        return ca_fb + unit_fb * abs_diff, ca_nf + unit_nf * abs_diff, diff

    @staticmethod
    def cumul_rule3(client_needs: dict[str, bool]) -> Tuple[float, float]:
        cumul_fb = sum(
            c for k, c in RULE3_FB_COEFFS.items() if client_needs.get(k, True)
        )
        cumul_nf = sum(
            c for k, c in RULE3_NFB_COEFFS.items() if client_needs.get(k, True)
        )
        return cumul_fb, cumul_nf

    # ------------------------------------------------------------------ main
    def compute(self, request: SimulationRequest, concept: str) -> RevenueResult:
        concept = concept.upper()
        if request.store is None:
            raise ValueError("store requis (fourni par l'orchestrateur)")

        key = f"concepts.{concept}"
        pivot_nb = float(self._ref.get(f"{key}.pivot_nb_chambres", 129) or 129)
        pivot_guests = float(self._ref.get(f"{key}.pivot_guests_per_chambre", 1.7) or 1.7)
        pivot_m_lin = float(self._ref.get(f"{key}.pivot_m_lin", 6) or 6)
        pivot_to = float(self._ref.get(f"{key}.pivot_to", 0.75) or 0.75)
        ca_fb_ref = float(self._ref.get(f"{key}.base_monthly_ca_fb", 0) or 0)
        ca_nf_ref = float(self._ref.get(f"{key}.base_monthly_ca_nf", 0) or 0)
        ventes_ref = float(self._ref.get(f"{key}.base_monthly_sales", 0) or 0)
        margin_fb = float(self._ref.get(f"{key}.margin_fb_pct", 2.6) or 2.6)
        margin_nf = float(self._ref.get(f"{key}.margin_nf_pct", 1.45) or 1.45)
        ref_mix_fb = float(self._ref.get(f"{key}.mix_fb", 0.7) or 0.7)
        ref_mix_nf = float(self._ref.get(f"{key}.mix_nf", 0.3) or 0.3)
        impact_to = float(self._ref.get("impact_to.ht_per_0_01_to", 9.233974) or 9.233974)

        store = request.store
        user_mix_fb = float(store.mix_fb)
        user_mix_nf = float(store.mix_nf)
        total_mix = user_mix_fb + user_mix_nf
        if total_mix > 0:
            user_mix_fb /= total_mix
            user_mix_nf /= total_mix

        mix_customized = (
            abs(user_mix_fb - ref_mix_fb) > 0.02 or abs(user_mix_nf - ref_mix_nf) > 0.02
        )
        effective_fb = user_mix_fb if mix_customized else ref_mix_fb
        effective_nf = user_mix_nf if mix_customized else ref_mix_nf

        op = request.operating
        clients_pilote = pivot_nb * pivot_to * pivot_guests * op.JOURS_MOIS
        clients_hotel = op.clients_mois
        to_delta = op.taux_occupation - pivot_to

        ca_fb, ca_nf = self.apply_to_impact(ca_fb_ref, ca_nf_ref, to_delta, impact_to)
        ca_fb, ca_nf, client_factor = self.rule1_clients(
            ca_fb, ca_nf, clients_hotel, clients_pilote
        )
        ca_fb, ca_nf, steps_fb, steps_nf = self.rule2_mix(
            ca_fb,
            ca_nf,
            user_mix_fb=effective_fb,
            user_mix_nf=effective_nf,
            ref_mix_fb=ref_mix_fb,
            ref_mix_nf=ref_mix_nf,
            ca_fb_ref=ca_fb_ref,
            ca_nf_ref=ca_nf_ref,
        )
        # Plancher par canal apres R2 (evite un mix extreme d annuler tout le CA)
        ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)
        cumul_fb, cumul_nf = self.cumul_rule3(request.client_profile.client_needs)
        ca_fb, ca_nf, delta_fb, delta_nf = self.rule3_categories(
            ca_fb, ca_nf, cumul_fb, cumul_nf
        )
        ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)
        ca_fb, ca_nf, m_lin_diff = self.rule4_m_lin(
            ca_fb,
            ca_nf,
            m_lin=store.m_lin,
            pivot_m_lin=pivot_m_lin,
            ca_fb_ref=ca_fb_ref,
            ca_nf_ref=ca_nf_ref,
        )
        ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)

        ca_ht = ca_fb + ca_nf
        ca_fb_m = ca_fb
        ca_nf_m = ca_nf
        taux_acheteur = ventes_ref / clients_pilote if clients_pilote else 0.0
        nbr_ventes = taux_acheteur * clients_hotel
        marge = self.marge_produit(ca_fb_m, ca_nf_m, margin_fb, margin_nf)

        warnings: list[str] = []
        if ca_ht <= 0:
            warnings.append(f"CA HT nul pour {concept} — vérifier les paramètres pilote.")

        return RevenueResult(
            concept=concept,
            ca_ht_mensuel=ca_ht,
            ca_fb_mensuel=ca_fb_m,
            ca_nf_mensuel=ca_nf_m,
            nbr_ventes_mensuel=nbr_ventes,
            marge_produit_mensuelle=marge,
            breakdown={
                # Entrées
                "nb_chambres": float(op.nb_chambres),
                "taux_occupation": float(op.taux_occupation),
                "guests_per_chambre": float(op.guests_per_chambre),
                "m_lin": float(store.m_lin),
                "mix_fb_effective": float(effective_fb),
                "mix_nf_effective": float(effective_nf),
                # Pilote concept (rod_reference)
                "pivot_nb_chambres": pivot_nb,
                "pivot_to": pivot_to,
                "pivot_guests": pivot_guests,
                "pivot_m_lin": pivot_m_lin,
                "ca_fb_ref_pilote": ca_fb_ref,
                "ca_nf_ref_pilote": ca_nf_ref,
                "ca_ht_ref_pilote": ca_fb_ref + ca_nf_ref,
                "ventes_ref_pilote": ventes_ref,
                # REV-01/02 clients
                "clients_hotel": clients_hotel,
                "clients_pilote": clients_pilote,
                "client_factor": client_factor,
                "taux_acheteur": taux_acheteur,
                # Ajustements
                "to_delta": to_delta,
                "mix_steps_fb": steps_fb,
                "mix_steps_nf": steps_nf,
                "cumul_rule3_fb": cumul_fb,
                "cumul_rule3_nf": cumul_nf,
                "rule3_delta_fb": delta_fb,
                "rule3_delta_nf": delta_nf,
                "m_lin_diff": m_lin_diff,
                "m_lin_factor": store.m_lin / pivot_m_lin if pivot_m_lin else 1.0,
                "margin_fb_coef": margin_fb,
                "margin_nf_coef": margin_nf,
                "mix_customized": float(mix_customized),
            },
            warnings=warnings,
        )
