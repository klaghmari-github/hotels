"""
Règles métier ROD.

  RevenueRules         CA / mix / mètres linéaires / marge produit
  CostRules            capex + opex mensuel par concept
  RecommendationRules  concepts autorisés + choix meilleure marge nette

Voir les docstrings de chaque module et le README (section Règles ROD).
"""

from accor.user.rules.costs import CostRules
from accor.user.rules.recommendation import RecommendationRules
from accor.user.rules.revenue import RevenueRules

__all__ = ["RevenueRules", "CostRules", "RecommendationRules"]
