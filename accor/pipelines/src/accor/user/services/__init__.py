"""
Services du parcours user.

  catalog          lecture datasets admin (marques, hôtels…)
  geocode          adresse → coordonnées
  enrich           comble features manquantes avant simu
  hotel_context    agrège fiche + pilote + model_data
  hotel_fetch      scrape Accor + upsert hotel_data si code inconnu
  simulator        enchaîne revenus + coûts pour un concept
  orchestrator     multi-concepts + recommandation (POST /api/simulate)
"""

from accor.user.services.orchestrator import SimulationOrchestrator

__all__ = ["SimulationOrchestrator"]
