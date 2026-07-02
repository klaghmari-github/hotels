"""Règles de recommandation de concept retail."""

from __future__ import annotations

from typing import Dict, List, Tuple

from rod_ia.domain.models.simulation import RodSimulationRequest, SimulationResult
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.traceability import RuleTrace


class RodRecommendationRules:
    """Filtre et recommande le concept selon taille hôtel et marge nette."""

    def allowed_concepts(
        self,
        request: RodSimulationRequest,
        reference: ReferenceRepository | None = None,
    ) -> Tuple[List[str], List[RuleTrace], List[str]]:
        nb_chambres = request.operating.nb_chambres
        concepts = ["SIMPLY", "LIBERTY", "CONNECTED"]
        warnings: list[str] = []

        m_lin_simply = 2.0
        if reference:
            m_lin_simply = float(
                reference.get("concepts.SIMPLY.pivot_m_lin", 2.0) or 2.0
            )

        if nb_chambres < 50:
            concepts = ["SIMPLY"]
            warnings.append("Hôtel < 50 chambres — seul SIMPLY autorisé.")
        elif nb_chambres >= 200:
            concepts = ["LIBERTY", "CONNECTED"]

        trace = [
            RuleTrace(
                rule_id="RECO_CONCEPT_SIZE",
                workbook="ROD - Paramètres & règles + projections nb. d'hôtels.xlsx",
                sheet="REGLES POUR RECO DU CONCEPT",
                cells=["à mapper précisément"],
                excel_formula=None,
                business_description="Filtrage concept selon nombre de chambres.",
                python_method="RodRecommendationRules.allowed_concepts",
                status="temporary_logic_requires_excel_validation",
            )
        ]
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