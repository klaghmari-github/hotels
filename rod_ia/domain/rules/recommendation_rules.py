"""Règles de recommandation de concept retail."""

from __future__ import annotations

from typing import List, Tuple

from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.rules.traceability import RuleTrace


class RodRecommendationRules:
    """Filtre les concepts autorisés selon la feuille REGLES POUR RECO DU CONCEPT."""

    def allowed_concepts(
        self, request: RodSimulationRequest
    ) -> Tuple[List[str], List[RuleTrace], List[str]]:
        nb_chambres = request.operating.nb_chambres
        m_lin = request.store.m_lin
        concepts = ["SIMPLY", "LIBERTY", "CONNECTED"]

        if nb_chambres < 50:
            concepts = ["SIMPLY"]
        elif m_lin > 4:
            concepts = ["LIBERTY", "CONNECTED"]

        trace = [
            RuleTrace(
                rule_id="RECO_CONCEPT_SIZE_MLIN",
                workbook="ROD - Paramètres & règles + projections nb. d'hôtels.xlsx",
                sheet="REGLES POUR RECO DU CONCEPT",
                cells=["à mapper précisément"],
                excel_formula=None,
                business_description="Filtrage concept selon chambres et mètres linéaires.",
                python_method="RodRecommendationRules.allowed_concepts",
                status="temporary_logic_requires_excel_validation",
            )
        ]
        return concepts, trace, []