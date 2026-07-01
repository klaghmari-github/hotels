from typing import List
from app.domain.models.simulation import RodSimulationRequest
from app.domain.rules.traceability import RuleTrace

class RodRecommendationRules:
    """Règles de recommandation de concept.

    Source à auditer : feuille REGLES POUR RECO DU CONCEPT.
    """
    def allowed_concepts(self, req: RodSimulationRequest) -> tuple[List[str], List[RuleTrace], List[str]]:
        nb_ch = req.operating.nb_chambres
        desired_m_lin = req.store.m_lin
        concepts = ["SIMPLY", "LIBERTY", "CONNECTED"]
        if nb_ch < 50:
            concepts = ["SIMPLY"]
        elif desired_m_lin > 4:
            concepts = ["LIBERTY", "CONNECTED"]
        trace=[RuleTrace(
            rule_id="RECO_CONCEPT_SIZE_MLIN",
            workbook="ROD - Paramètres & règles + projections nb. d'hôtels.xlsx",
            sheet="REGLES POUR RECO DU CONCEPT",
            cells=["à mapper précisément"],
            excel_formula=None,
            business_description="Filtrage temporaire selon nombre de chambres et mètre linéaire, à valider Excel.",
            python_method="RodRecommendationRules.allowed_concepts",
            status="temporary_logic_requires_excel_validation",
        )]
        return concepts, trace, []
