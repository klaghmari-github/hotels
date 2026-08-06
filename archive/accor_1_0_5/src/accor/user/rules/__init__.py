"""
Règles métier ROD — fidèles à ``simulateur_rules.html``.

  pilot_table          constantes pilotes + coeffs R3 + agencement
  RevenueRules         R1→R2→R3→R4 + marge produit (2,6 / 1,45)
  CostRules            techno + annexes + agencement (+ cost_over_60m)
  RecommendationRules  arbre reco (chambres / lifestyle / ML / vitrine / TO)

Ordre d'exécution (§12) : reco → pour chaque concept P&L complet.
"""

from archive.accor_1_0_5.src.accor.user.rules.costs import CostRules
from archive.accor_1_0_5.src.accor.user.rules.recommendation import RecommendationRules
from archive.accor_1_0_5.src.accor.user.rules.revenue import RevenueRules

__all__ = ["RevenueRules", "CostRules", "RecommendationRules"]
