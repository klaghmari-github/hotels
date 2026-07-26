"""
Règles de **recommandation** de concept (Excel REGLES POUR RECO).

* #1 taille : < 50 ch → SIMPLY ; ≥ 50 → LIBERTY / CONNECTED
* #2 catégories N-F&B lifestyle → ouvre LIBERTY
* Choix final : meilleure marge nette parmi les concepts autorisés
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from accor.user.models import ConceptSimulation, SimulationRequest
from accor.user.rules.coeffs import (
    BRAND_TO_CODE,
    BRANDS_REQUIRING_LIBERTY_PATH,
    LIBERTY_NFB_NEEDS,
)


class RecommendationRules:
    """Filtre les concepts admissibles puis sélectionne la meilleure marge."""

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
        """Au moins une categorie N-F&B lifestyle active (Règle reco #2)."""
        needs = request.client_profile.client_needs or {}
        # defaut False si cle absente : ne pas ouvrir LIBERTY par omission
        return any(bool(needs.get(k, False)) for k in LIBERTY_NFB_NEEDS)

    def allowed_concepts(
        self, request: SimulationRequest
    ) -> Tuple[List[str], List[str]]:
        """Retourne (concepts autorisés, warnings)."""
        n = request.operating.nb_chambres
        brand = self.brand_code(request.identity.hotel_brand)
        has_lib = self.has_liberty_nfb(request)
        warnings: list[str] = []

        if n < 50:
            warnings.append("Hôtel < 50 chambres — seul SIMPLY est autorisé (Règle #1).")
            return ["SIMPLY"], warnings

        concepts: list[str] = []
        if brand == "IBB" and n < 200:
            concepts.append("SIMPLY")
        if has_lib:
            concepts.append("LIBERTY")
        else:
            warnings.append(
                "Aucune catégorie NON-F&B lifestyle — LIBERTY non proposé (Règle #2)."
            )
        concepts.append("CONNECTED")

        if brand in BRANDS_REQUIRING_LIBERTY_PATH and not has_lib:
            warnings.append(
                f"Marque {brand} : LIBERTY est le chemin nominal si catégories N-F&B actives."
            )

        # unique preserve order
        seen: set[str] = set()
        ordered: list[str] = []
        for c in concepts:
            if c not in seen:
                seen.add(c)
                ordered.append(c)
        return ordered, warnings

    def recommend(
        self,
        by_concept: Dict[str, ConceptSimulation],
        allowed: List[str] | None = None,
    ) -> Tuple[str, str, str]:
        """
        Returns
        -------
        (concept_recommandé, concept_meilleure_marge, raison)
        """
        allowed = allowed or list(by_concept.keys())
        candidates = {
            k: v for k, v in by_concept.items() if k in allowed and v is not None
        }
        if not candidates:
            candidates = dict(by_concept)
        if not candidates:
            return "SIMPLY", "SIMPLY", "Aucun concept simulé."

        best_margin = max(
            candidates.items(), key=lambda kv: kv[1].marge_nette_annuelle
        )[0]
        # Recommandation = meilleure marge parmi autorisés
        recommended = best_margin
        reason = (
            f"{recommended} offre la meilleure marge nette annuelle "
            f"({candidates[recommended].marge_nette_annuelle:,.0f} €) "
            f"parmi {', '.join(allowed)}."
        )
        return recommended, best_margin, reason
