"""
Package user — simulateur ROD pour directeurs d'hôtel.

  models.py      dataclasses d'entrée / sortie (SimulationRequest, …)
  reference.py   constantes lues depuis data/rod_reference.json
  rules/         revenus, coûts, recommandation (modules séparés)
  services/      catalogue, géocode, enrich, contexte hôtel, orchestrateur
  app.py         Flask API + page wizard
  validate_rod.py  checks de non-régression sur les règles

Revenus et coûts sont séparés exprès : un futur moteur (ex. modèle) peut
remplacer RevenueRules sans retoucher CostRules.
"""

__all__ = ["__version__"]
__version__ = "1.0.0"
