"""
Moteur de revenus ROD — fidèle à ``simulateur_rules.html``.

Ordre d'exécution (§12) :
  R1 clients acheteurs → R2 mix ±10 % → R3 catégories ±coeff → R4 ML/frigos
  → marge produits (coeffs 2,6 / 1,45)

Pas d'étape « impact TO » hors spec (le TO n'agit que via clients hébergés en R1).
"""

from __future__ import annotations

from typing import Any, Tuple

from archive.accor_1_0_6.pipelines.src.accor.user.models import RevenueResult, SimulationRequest
from archive.accor_1_0_6.pipelines.src.accor.user.reference import RodReference
from archive.accor_1_0_6.pipelines.src.accor.user.rules.pilot_table import (
    CAT_FB,
    CAT_NFB,
    JOURS_MOIS,
    get_pilot,
)


class RevenueRules:
    """Moteur déterministe de CA HT / ventes / marge produit (iso Excel)."""

    def __init__(self, reference: RodReference | None = None) -> None:
        # reference conservée pour rétrocompat / overrides admin Excel
        self._ref = reference or RodReference()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def marge_produit(ca_fb: float, ca_nf: float, coef_fb: float, coef_nf: float) -> float:
        """Excel : marge = CA − CA/coef  (= CA × (1 − 1/coef))."""
        m_fb = ca_fb - (ca_fb / coef_fb) if coef_fb else 0.0
        m_nf = ca_nf - (ca_nf / coef_nf) if coef_nf else 0.0
        return m_fb + m_nf

    @staticmethod
    def rule1_buyers(
        *,
        clients_hotel: float,
        ventes_pilote: float,
        clients_pilote: float,
        ca_fb_pilote: float,
        ca_nfb_pilote: float,
    ) -> Tuple[float, float, float, float, float]:
        """
        R1 — clients acheteurs.

        taux_acheteurs = ventes_pilote / clients_heb_pilote
        nb_acheteurs   = clients_hotel × taux
        CA = (CA_pilote / ventes_pilote) × nb_acheteurs
        """
        if clients_pilote <= 0 or ventes_pilote <= 0:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        taux = ventes_pilote / clients_pilote
        acheteurs = clients_hotel * taux
        ca_fb = (ca_fb_pilote / ventes_pilote) * acheteurs
        ca_nfb = (ca_nfb_pilote / ventes_pilote) * acheteurs
        return ca_fb, ca_nfb, taux, acheteurs, clients_hotel / clients_pilote

    @staticmethod
    def rule2_mix(
        ca_fb: float,
        ca_nfb: float,
        *,
        mix_fb_user: float,
        mix_fb_ref: float,
        ca_10_fb: float,
        ca_10_nfb: float,
    ) -> Tuple[float, float, float]:
        """
        R2 — impact mix ±10 %.

        diff_FB = mix_user − mix_ref
        CA_FB  += CA_10_FB  × (diff_FB × 10)
        CA_NFB += CA_10_NFB × (−diff_FB × 10)
        """
        d_fb = float(mix_fb_user) - float(mix_fb_ref)
        steps = d_fb * 10.0
        ca_fb = ca_fb + ca_10_fb * steps
        ca_nfb = ca_nfb + ca_10_nfb * (-steps)
        return ca_fb, ca_nfb, steps

    @staticmethod
    def rule3_categories(
        ca_fb: float,
        ca_nfb: float,
        client_needs: dict[str, bool],
    ) -> Tuple[float, float, float, float]:
        """
        R3 — ±coeff selon toggle.

        mult = 1 + Σ(+coeff si ON, −coeff si OFF)
        """
        sum_fb = 0.0
        for key, coeff in CAT_FB.items():
            on = bool(client_needs.get(key, False))
            sum_fb += coeff if on else -coeff
        sum_nfb = 0.0
        for key, coeff in CAT_NFB.items():
            on = bool(client_needs.get(key, False))
            sum_nfb += coeff if on else -coeff

        mult_fb = 1.0 + sum_fb
        mult_nfb = 1.0 + sum_nfb
        return ca_fb * mult_fb, ca_nfb * mult_nfb, mult_fb, mult_nfb

    @staticmethod
    def rule4_surface(
        ca_fb: float,
        ca_nfb: float,
        *,
        concept: str,
        m_lin: float,
        ml_ref: float,
        ca_1ml_fb: float,
        ca_1ml_nfb: float,
        nb_frigos_froid: float,
        frigo_ref: float | None,
        ca_1frigo_fb: float,
        ca_1frigo_nfb: float,
    ) -> Tuple[float, float, float, str]:
        """
        R4 — Simply/Liberty : ML ; Connected : frigos froid.
        """
        concept = concept.upper()
        if concept == "CONNECTED" and frigo_ref is not None:
            diff = float(nb_frigos_froid) - float(frigo_ref)
            abs_d = abs(diff)
            sign = -1.0 if diff < 0 else 1.0
            return (
                ca_fb + sign * ca_1frigo_fb * abs_d,
                ca_nfb + sign * ca_1frigo_nfb * abs_d,
                diff,
                "frigos_froid",
            )
        diff = float(m_lin) - float(ml_ref)
        abs_d = abs(diff)
        if diff < 0:
            return ca_fb - ca_1ml_fb * abs_d, ca_nfb - ca_1ml_nfb * abs_d, diff, "m_lin"
        return ca_fb + ca_1ml_fb * abs_d, ca_nfb + ca_1ml_nfb * abs_d, diff, "m_lin"

    # ------------------------------------------------------------------ main
    def compute(
        self,
        request: SimulationRequest,
        concept: str,
        *,
        pilot_overrides: dict | None = None,
    ) -> RevenueResult:
        """
        Calcule le CA projeté pour un concept (SIMPLY / LIBERTY / CONNECTED).

        ``pilot_overrides`` : réservé admin Excel (colonne gauche) — optionnel.
        """
        concept = (concept or "").upper().strip()
        if request.store is None:
            raise ValueError("store requis (m_lin, mix_fb, mix_nf, équipements)")

        pilot = dict(get_pilot(concept))
        ov = pilot_overrides if isinstance(pilot_overrides, dict) else {}

        # Overrides admin éventuels (ne cassent pas le schéma rules)
        def _ov(name: str, default: float) -> float:
            if name in ov and ov[name] not in (None, ""):
                return float(ov[name])
            return float(default)

        ventes = _ov("nb_ventes", pilot["ventes"])
        ca_fb_p = _ov("ca_fb", pilot["ca_fb"])
        ca_nfb_p = _ov("ca_nf", pilot["ca_nfb"])
        mix_ref = _ov("mix_fb", pilot["mix_fb"])
        if mix_ref > 1.0:
            mix_ref /= 100.0
        ml_ref = _ov("m_lin", pilot["ml_ref"] or 6.0)
        clients_pilote = _ov(
            "clients_heb",
            pilot.get("clients_heb")
            or (
                pilot["nb_chambres"]
                * pilot["guests"]
                * pilot["to"]
                * JOURS_MOIS
            ),
        )
        ca_10_fb = _ov("ca_10_fb", pilot["ca_10_fb"])
        ca_10_nfb = _ov("ca_10_nfb", pilot["ca_10_nfb"])
        ca_1ml_fb = _ov("ca_1ml_fb", pilot.get("ca_1ml_fb") or (ca_fb_p / ml_ref if ml_ref else 0.0))
        ca_1ml_nfb = _ov(
            "ca_1ml_nfb", pilot.get("ca_1ml_nfb") or (ca_nfb_p / ml_ref if ml_ref else 0.0)
        )
        frigo_ref = pilot.get("frigo_ref")
        if "frigo_ref" in ov and ov["frigo_ref"] not in (None, ""):
            frigo_ref = float(ov["frigo_ref"])
        ca_1frigo_fb = float(pilot.get("ca_1frigo_fb") or (ca_fb_p / 3.0))
        ca_1frigo_nfb = float(pilot.get("ca_1frigo_nfb") or (ca_nfb_p / 3.0))
        coeff_fb = _ov("margin_fb", pilot["coeff_fb"])
        # Spec simu : 1,45 pour les 3 (pas le 2,0 pilote Liberty)
        coeff_nfb = _ov("margin_nf", pilot["coeff_nfb"])

        store = request.store
        m_lin = float(store.m_lin)
        mix_fb = float(store.mix_fb)
        if mix_fb > 1.0:
            mix_fb /= 100.0
        mix_fb = min(max(mix_fb, 0.0), 1.0)
        mix_nf = 1.0 - mix_fb

        op = request.operating
        clients_hotel = float(op.clients_mois)

        needs = dict(request.client_profile.client_needs or {})

        warnings: list[str] = []
        # Garde-fou ML min 2 (S/L) — Connected peut avoir ML décoratif
        if concept != "CONNECTED" and m_lin < 2.0:
            warnings.append(
                f"Mètres linéaires < 2 ({m_lin}) — minimum métier = 2 (calcul forcé)."
            )
            m_lin = 2.0

        # Si aucune catégorie F&B active → CA F&B forcé vers 0 après R3 (spec garde-fou)
        any_fb = any(bool(needs.get(k, False)) for k in CAT_FB)
        any_nfb = any(bool(needs.get(k, False)) for k in CAT_NFB)
        if not any_fb and not any_nfb:
            warnings.append("Aucune catégorie produit active.")

        # --- R1 ---
        ca_fb, ca_nfb, taux, acheteurs, factor = self.rule1_buyers(
            clients_hotel=clients_hotel,
            ventes_pilote=ventes,
            clients_pilote=clients_pilote,
            ca_fb_pilote=ca_fb_p,
            ca_nfb_pilote=ca_nfb_p,
        )
        r1_fb, r1_nfb = ca_fb, ca_nfb

        # --- R2 ---
        ca_fb, ca_nfb, mix_steps = self.rule2_mix(
            ca_fb,
            ca_nfb,
            mix_fb_user=mix_fb,
            mix_fb_ref=mix_ref,
            ca_10_fb=ca_10_fb,
            ca_10_nfb=ca_10_nfb,
        )
        r2_fb, r2_nfb = ca_fb, ca_nfb

        # --- R3 ---
        ca_fb, ca_nfb, mult_fb, mult_nfb = self.rule3_categories(ca_fb, ca_nfb, needs)
        r3_fb, r3_nfb = ca_fb, ca_nfb

        # --- R4 ---
        nb_frigos = float(getattr(store, "nb_frigos_froid", None) or 3)
        # visibilité métier Connected : frigo froid seulement si mix F&B ≥ 10 %
        if concept == "CONNECTED" and mix_fb < 0.10:
            nb_frigos = 0.0
            warnings.append("Mix F&B < 10 % — frigos froid non comptés (Connected).")

        ca_fb, ca_nfb, r4_diff, r4_mode = self.rule4_surface(
            ca_fb,
            ca_nfb,
            concept=concept,
            m_lin=m_lin,
            ml_ref=ml_ref,
            ca_1ml_fb=ca_1ml_fb,
            ca_1ml_nfb=ca_1ml_nfb,
            nb_frigos_froid=nb_frigos,
            frigo_ref=float(frigo_ref) if frigo_ref is not None else None,
            ca_1frigo_fb=ca_1frigo_fb,
            ca_1frigo_nfb=ca_1frigo_nfb,
        )

        if not any_fb:
            ca_fb = 0.0
        if not any_nfb:
            ca_nfb = 0.0

        ca_ht = ca_fb + ca_nfb
        marge = self.marge_produit(ca_fb, ca_nfb, coeff_fb, coeff_nfb)
        taux_acheteur = ventes / clients_pilote if clients_pilote else 0.0
        nbr_ventes = acheteurs  # = taux × clients_hotel

        if ca_ht < 0:
            warnings.append("CA HT négatif après règles — statut « Not profitable ».")

        return RevenueResult(
            concept=concept,
            ca_ht_mensuel=ca_ht,
            ca_fb_mensuel=ca_fb,
            ca_nf_mensuel=ca_nfb,
            nbr_ventes_mensuel=nbr_ventes,
            marge_produit_mensuelle=marge,
            breakdown={
                "nb_chambres": float(op.nb_chambres),
                "taux_occupation": float(op.taux_occupation),
                "guests_per_chambre": float(op.guests_per_chambre),
                "m_lin": float(m_lin),
                "mix_fb": float(mix_fb),
                "mix_nf": float(mix_nf),
                "mix_fb_ref": float(mix_ref),
                "clients_hotel": float(clients_hotel),
                "clients_pilote": float(clients_pilote),
                "taux_acheteur": float(taux_acheteur),
                "nb_acheteurs": float(acheteurs),
                "client_factor": float(factor),
                "ventes_ref_pilote": float(ventes),
                "ca_fb_ref_pilote": float(ca_fb_p),
                "ca_nf_ref_pilote": float(ca_nfb_p),
                "ca_r1_fb": float(r1_fb),
                "ca_r1_nfb": float(r1_nfb),
                "ca_r2_fb": float(r2_fb),
                "ca_r2_nfb": float(r2_nfb),
                "mix_steps_fb": float(mix_steps),
                "ca_r3_fb": float(r3_fb),
                "ca_r3_nfb": float(r3_nfb),
                "mult_rule3_fb": float(mult_fb),
                "mult_rule3_nfb": float(mult_nfb),
                "r4_mode": r4_mode,  # type: ignore[dict-item]
                "r4_diff": float(r4_diff),
                "nb_frigos_froid": float(nb_frigos),
                "coeff_fb": float(coeff_fb),
                "coeff_nfb": float(coeff_nfb),
                "marge_fb": float(ca_fb - ca_fb / coeff_fb) if coeff_fb else 0.0,
                "marge_nfb": float(ca_nfb - ca_nfb / coeff_nfb) if coeff_nfb else 0.0,
            },
            warnings=warnings,
        )

    # Alias historiques (admin Excel / tests) — délégation vers le nouveau moteur
    @staticmethod
    def apply_to_impact(
        ca_fb: float, ca_nf: float, to_delta: float, impact_per_point: float
    ) -> Tuple[float, float]:
        """DEPRECATED — l'impact TO hors R1 n'est plus dans le schéma rules."""
        return ca_fb, ca_nf

    @staticmethod
    def rule1_clients(
        ca_fb: float, ca_nf: float, clients_hotel: float, clients_pilote: float
    ) -> Tuple[float, float, float]:
        factor = clients_hotel / clients_pilote if clients_pilote else 1.0
        return ca_fb * factor, ca_nf * factor, factor

    @classmethod
    def rule2_mix_legacy(cls, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Utiliser rule2_mix (signature rules).")

    @staticmethod
    def cumul_rule3(
        client_needs: dict[str, bool],
        *,
        shares_fb: dict[str, float] | None = None,
        shares_nfb: dict[str, float] | None = None,
    ) -> Tuple[float, float]:
        """Rétrocompat : renvoie la somme ±coeffs (pas le mult)."""
        del shares_fb, shares_nfb  # parts hors spec Excel pure
        s_fb = sum(
            c if client_needs.get(k, False) else -c for k, c in CAT_FB.items()
        )
        s_nf = sum(
            c if client_needs.get(k, False) else -c for k, c in CAT_NFB.items()
        )
        return s_fb, s_nf
