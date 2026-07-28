"""
Recommandation de concept (logique type Excel « règles pour reco »).

Règles d'affichage / reco (audit + Excel) — **les 3 solutions sont toujours
calculées** à titre informatif ; la reco choisit l'ordre / le libellé :

1. Nb. chambres ≤ 49 → **SIMPLY** recommandé
2. Nb. chambres ≥ 50 **et** au moins 1 des 5 catégories lifestyle N-F&B
   (Cosmétiques, Kids, PAP, Accessoires, Souvenirs) cochée → **LIBERTY**
3. Sinon (chemins secondaires Excel) : ML > 4 / vitrine déjà présente /
   TO < 70 % → LIBERTY ; sinon CONNECTED

La « meilleure marge » est fournie à part (informative), elle ne force
pas la reco si l'arbre métier impose une solution.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from accor.user.models import ConceptSimulation, SimulationRequest
from accor.user.rules.coeffs import (
    BRAND_TO_CODE,
    BRANDS_REQUIRING_LIBERTY_PATH,
    CLIENT_NEED_LABELS,
    LIBERTY_NFB_NEEDS,
)


class RecommendationRules:
    """Arbre de reco + sélection informative de la meilleure marge."""

    CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")

    @staticmethod
    def brand_code(brand: str) -> str:
        b = (brand or "").upper().replace("_", " ").strip()
        if b in BRAND_TO_CODE:
            return BRAND_TO_CODE[b]
        for name, code in BRAND_TO_CODE.items():
            if name in b:
                return code
        return ""

    @staticmethod
    def has_liberty_nfb(request: SimulationRequest) -> bool:
        """Au moins une catégorie N-F&B lifestyle active (Règle reco #2)."""
        needs = request.client_profile.client_needs or {}
        return any(bool(needs.get(k, False)) for k in LIBERTY_NFB_NEEDS)

    @staticmethod
    def _has_vitrine(request: SimulationRequest) -> bool:
        services = getattr(request, "services", None)
        if services is None:
            return False
        if isinstance(services, dict):
            return bool(
                services.get("lobby_fridge")
                or services.get("has_vitrine")
                or services.get("corner_fb_frigo")
            )
        return bool(
            getattr(services, "lobby_fridge", False)
            or getattr(services, "corner_fb_frigo", False)
        )

    def allowed_concepts(
        self, request: SimulationRequest
    ) -> Tuple[List[str], List[str]]:
        """
        Les 3 solutions restent toujours **autorisées au calcul** (informatif).
        Les warnings expliquent le chemin de reco.
        """
        n = int(request.operating.nb_chambres or 0)
        has_lib = self.has_liberty_nfb(request)
        warnings: list[str] = []

        if n <= 49:
            warnings.append(
                f"Hôtel ≤ 49 chambres ({n}) — reco métier = SIMPLY "
                "(les autres solutions restent calculées à titre informatif)."
            )
        elif has_lib:
            active = [
                CLIENT_NEED_LABELS.get(k, k)
                for k in LIBERTY_NFB_NEEDS
                if bool((request.client_profile.client_needs or {}).get(k, False))
            ]
            warnings.append(
                f"Hôtel ≥ 50 ch. + catégorie(s) lifestyle N-F&B "
                f"({', '.join(active) or '—'}) → reco métier = LIBERTY."
            )
        else:
            warnings.append(
                "Hôtel ≥ 50 ch. sans catégorie lifestyle N-F&B cochée — "
                "LIBERTY non imposé par la règle des 5 catégories "
                "(autres critères ML / vitrine / TO peuvent s'appliquer)."
            )

        brand = self.brand_code(request.identity.hotel_brand)
        if brand in BRANDS_REQUIRING_LIBERTY_PATH and n >= 50 and not has_lib:
            warnings.append(
                f"Marque {brand} : chemin nominal LIBERTY si au moins 1 des 5 "
                "catégories lifestyle N-F&B est cochée."
            )

        # Toujours les 3 pour le P&L informatif
        return list(self.CONCEPTS), warnings

    def recommend_tree(
        self,
        request: SimulationRequest,
        *,
        m_lin: float | None = None,
        to: float | None = None,
    ) -> Tuple[str, List[str], List[str]]:
        """
        Arbre de reco (même logique que le simulateur Excel).

        Returns
        -------
        (recommended, ordered_3, reasons)
        """
        rooms = float(request.operating.nb_chambres or 0)
        ml = float(
            m_lin
            if m_lin is not None
            else (request.store.m_lin if request.store else 6.0)
            or 6.0
        )
        to_rate = float(
            to if to is not None else request.operating.taux_occupation or 0.0
        )
        if to_rate > 1.0:
            to_rate /= 100.0
        has_lib = self.has_liberty_nfb(request)
        has_vitrine = self._has_vitrine(request)
        reasons: list[str] = []

        if rooms <= 49:
            recommended = "SIMPLY"
            reasons.append(
                f"Nb. chambres ≤ 49 ({int(round(rooms))}) → SIMPLY recommandé."
            )
        elif has_lib:
            recommended = "LIBERTY"
            active = [
                CLIENT_NEED_LABELS.get(k, k)
                for k in LIBERTY_NFB_NEEDS
                if bool((request.client_profile.client_needs or {}).get(k, False))
            ]
            reasons.append(
                "Hôtel ≥ 50 ch. + au moins 1 des 5 catégories lifestyle N-F&B "
                f"cochée ({', '.join(active) or '—'}) → LIBERTY recommandé."
            )
        elif ml > 4:
            recommended = "LIBERTY"
            reasons.append(
                f"Mètres linéaires > 4 ({ml:.1f}) → LIBERTY recommandé."
            )
        elif has_vitrine:
            recommended = "LIBERTY"
            reasons.append(
                "Vitrine / frigo lobby déjà présent → LIBERTY recommandé."
            )
        elif to_rate < 0.70:
            recommended = "LIBERTY"
            reasons.append(
                f"TO moyen < 70 % ({to_rate * 100:.1f} %) → LIBERTY recommandé."
            )
        else:
            recommended = "CONNECTED"
            reasons.append(
                "Hôtel ≥ 50 ch., sans lifestyle N-F&B, ML ≤ 4, sans vitrine, "
                f"TO ≥ 70 % → CONNECTED recommandé."
            )

        ordered = [recommended] + [c for c in self.CONCEPTS if c != recommended]
        return recommended, ordered, reasons

    def recommend(
        self,
        by_concept: Dict[str, ConceptSimulation],
        allowed: List[str] | None = None,
        *,
        request: SimulationRequest | None = None,
    ) -> Tuple[str, str, str]:
        """
        Returns
        -------
        (concept_recommandé, concept_meilleure_marge, raison)

        La reco suit l'arbre métier si ``request`` est fourni.
        La meilleure marge est toujours calculée (informative).
        """
        candidates = {
            k: v
            for k, v in (by_concept or {}).items()
            if v is not None and (not allowed or k in allowed)
        }
        if not candidates:
            candidates = {k: v for k, v in (by_concept or {}).items() if v is not None}
        if not candidates:
            return "SIMPLY", "SIMPLY", "Aucun concept simulé."

        best_margin = max(
            candidates.items(),
            key=lambda kv: float(getattr(kv[1], "marge_nette_annuelle", 0) or 0),
        )[0]

        if request is not None:
            recommended, _order, reasons = self.recommend_tree(request)
            # Si la reco n'a pas de simu (cas rare), fallback meilleure marge
            if recommended not in candidates:
                recommended = best_margin
            reason = " ".join(reasons)
            if best_margin != recommended:
                bm = candidates[best_margin]
                reason += (
                    f" Meilleure marge estimée (informatif) = {best_margin} "
                    f"({float(bm.marge_nette_annuelle or 0):,.0f} €/an) — "
                    "n'impose pas la reco métier."
                )
            else:
                reason += (
                    f" {recommended} offre aussi la meilleure marge nette "
                    f"parmi les 3 solutions."
                )
            return recommended, best_margin, reason

        # Sans request : ancienne logique marge seule
        recommended = best_margin
        reason = (
            f"{recommended} offre la meilleure marge nette annuelle "
            f"({candidates[recommended].marge_nette_annuelle:,.0f} €)."
        )
        return recommended, best_margin, reason
