"""Règles de recommandation de concept retail — alignées Excel REGLES POUR RECO."""

from __future__ import annotations

from typing import Dict, List, Tuple

from rod_ia.domain.models.simulation import RodSimulationRequest, SimulationResult
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.excel_category_coeffs import (
    BRAND_TO_CODE,
    BRANDS_REQUIRING_LIBERTY_PATH,
    LIBERTY_NFB_NEEDS,
)
from rod_ia.domain.rules.traceability import RuleTrace


class RodRecommendationRules:
    """Filtre et recommande le concept selon taille, catégories N-F&B et marge nette."""

    @staticmethod
    def _brand_code(request: RodSimulationRequest) -> str:
        brand = (request.identity.brand or "").upper().replace("_", " ").strip()
        return BRAND_TO_CODE.get(brand, "")

    @staticmethod
    def _has_liberty_nfb_category(request: RodSimulationRequest) -> bool:
        needs = request.client_profile.client_needs
        return any(needs.get(key, True) for key in LIBERTY_NFB_NEEDS)

    def allowed_concepts(
        self,
        request: RodSimulationRequest,
        reference: ReferenceRepository | None = None,
    ) -> Tuple[List[str], List[RuleTrace], List[str]]:
        nb_chambres = request.operating.nb_chambres
        concepts: list[str] = []
        warnings: list[str] = []
        trace: list[RuleTrace] = []
        brand_code = self._brand_code(request)
        has_liberty_cats = self._has_liberty_nfb_category(request)

        if nb_chambres < 50:
            concepts = ["SIMPLY"]
            warnings.append("Hôtel < 50 chambres — seul SIMPLY autorisé (Règle #1 Excel).")
            trace.append(
                RuleTrace(
                    rule_id="RECO_RULE1_SIZE_SIMPLY",
                    workbook="ROD - Paramètres & règles + projections nb. d'hôtels.xlsx",
                    sheet="REGLES POUR RECO DU CONCEPT",
                    cells=["Règle #1 — 0 à 49 chambres"],
                    excel_formula=None,
                    business_description="Entre 0 et 49 chambres → SIMPLY uniquement.",
                    python_method="RodRecommendationRules.allowed_concepts",
                    status="implemented_from_documentation",
                )
            )
        else:
            concepts.append("CONNECTED")
            # Ibis budget : corners existants souvent en SIMPLY (Excel = stats déploiement neuf)
            if brand_code == "IBB" and nb_chambres < 200 and "SIMPLY" not in concepts:
                concepts.insert(0, "SIMPLY")
            if has_liberty_cats:
                concepts.insert(0, "LIBERTY")
                trace.append(
                    RuleTrace(
                        rule_id="RECO_RULE2_LIBERTY_CATEGORIES",
                        workbook="ROD - Paramètres & règles + projections nb. d'hôtels.xlsx",
                        sheet="REGLES POUR RECO DU CONCEPT",
                        cells=["Règle #2 — Cosmetics/Kids/Apparel/Accessories/Souvenirs"],
                        excel_formula=None,
                        business_description="LIBERTY si au moins une catégorie NON-F&B éligible.",
                        python_method="RodRecommendationRules._has_liberty_nfb_category",
                        status="implemented_from_documentation",
                    )
                )
            else:
                warnings.append(
                    "Aucune catégorie NON-F&B éligible pour LIBERTY — CONNECTED seul."
                )
                trace.append(
                    RuleTrace(
                        rule_id="RECO_RULE2_LIBERTY_BLOCKED",
                        workbook="ROD - Paramètres & règles + projections nb. d'hôtels.xlsx",
                        sheet="REGLES POUR RECO DU CONCEPT",
                        cells=["Règle #2"],
                        excel_formula=None,
                        business_description="LIBERTY exclu — catégories N-F&B insuffisantes.",
                        python_method="RodRecommendationRules._has_liberty_nfb_category",
                        status="implemented_from_documentation",
                    )
                )

            if brand_code in BRANDS_REQUIRING_LIBERTY_PATH and not has_liberty_cats:
                warnings.append(
                    f"Marque {brand_code} : LIBERTY requis si catégories éligibles "
                    "(note Excel NOV/MER)."
                )

            trace.append(
                RuleTrace(
                    rule_id="RECO_RULE1_SIZE_50_PLUS",
                    workbook="ROD - Paramètres & règles + projections nb. d'hôtels.xlsx",
                    sheet="REGLES POUR RECO DU CONCEPT",
                    cells=["Règle #1 — + de 50 chambres"],
                    excel_formula=None,
                    business_description="Plus de 50 chambres → LIBERTY et/ou CONNECTED.",
                    python_method="RodRecommendationRules.allowed_concepts",
                    status="implemented_from_documentation",
                )
            )

        return concepts, trace, warnings

    def recommend(
        self,
        rod_by_concept: Dict[str, SimulationResult],
        allowed: List[str] | None = None,
    ) -> Tuple[str, str, str]:
        """Retourne (concept_recommandé, meilleure_marge, raison)."""
        allowed = allowed or list(rod_by_concept.keys())
        candidates = {
            k: v for k, v in rod_by_concept.items() if k in allowed
        }
        if not candidates:
            candidates = rod_by_concept

        best_margin_concept = max(
            candidates,
            key=lambda c: candidates[c].marge_annuelle,
        )
        recommended = best_margin_concept
        best = candidates[best_margin_concept]
        reason = (
            f"{recommended} offre la meilleure marge nette annuelle "
            f"({best.marge_annuelle:,.0f} €) parmi les concepts autorisés."
        )
        return recommended, best_margin_concept, reason