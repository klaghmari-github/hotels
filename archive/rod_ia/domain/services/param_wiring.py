"""Registre des paramètres UI → moteurs (ROD / IA / optimiseur)."""

from __future__ import annotations

from typing import List


def param_wiring_registry() -> List[dict]:
    """Décrit quels champs du wizard alimentent chaque moteur."""
    return [
        {"id": "nb_chambres", "rod": True, "ai": True, "optimizer": True, "label": "# Chambres"},
        {"id": "taux_occupation", "rod": True, "ai": True, "optimizer": True, "label": "TO annuel"},
        {"id": "adults_per_room", "rod": True, "ai": True, "optimizer": True, "label": "Adultes / chambre"},
        {"id": "children_per_room", "rod": True, "ai": True, "optimizer": True, "label": "Enfants / chambre"},
        {"id": "sim_guests", "rod": True, "ai": True, "optimizer": True, "label": "Guests / chambre"},
        {"id": "sim_occ", "rod": True, "ai": True, "optimizer": True, "label": "Occupation (étape 5)"},
        {"id": "m_lin", "rod": True, "ai": True, "optimizer": True, "label": "Mètres linéaires"},
        {"id": "client_needs", "rod": True, "ai": True, "optimizer": True, "label": "Besoins clients (toggles)"},
        {"id": "hotel_name", "rod": False, "ai": True, "optimizer": False, "label": "Nom hôtel", "note": "Enrichissement POI → IA"},
        {"id": "city", "rod": False, "ai": True, "optimizer": False, "label": "Ville", "note": "Enrichissement POI → IA"},
        {"id": "address", "rod": False, "ai": True, "optimizer": False, "label": "Adresse", "note": "Enrichissement POI → IA"},
        {"id": "brand", "rod": False, "ai": False, "optimizer": False, "label": "Marque", "note": "Registre hôtel uniquement"},
        {"id": "contract_year", "rod": False, "ai": False, "optimizer": False, "label": "Contrat signé"},
        {"id": "contract_type", "rod": False, "ai": False, "optimizer": False, "label": "Type de contrat"},
        {"id": "owner", "rod": False, "ai": False, "optimizer": False, "label": "Propriétaire"},
        {"id": "dom_dof", "rod": False, "ai": False, "optimizer": False, "label": "DOM / DOF"},
        {"id": "panier_moyen", "rod": False, "ai": False, "optimizer": False, "label": "Panier moyen"},
        {"id": "reno_hotel", "rod": False, "ai": False, "optimizer": False, "label": "Rénovation hôtel"},
        {"id": "reno_lobby", "rod": False, "ai": False, "optimizer": False, "label": "Rénovation lobby"},
        {"id": "pms", "rod": False, "ai": False, "optimizer": False, "label": "PMS"},
        {"id": "occ_min_month", "rod": False, "ai": False, "optimizer": False, "label": "TO min (mois)"},
        {"id": "occ_max_month", "rod": False, "ai": False, "optimizer": False, "label": "TO max (mois)"},
        {"id": "occ_min_pct", "rod": False, "ai": False, "optimizer": False, "label": "TO min (%)"},
        {"id": "occ_max_pct", "rod": False, "ai": False, "optimizer": False, "label": "TO max (%)"},
        {"id": "services_step", "rod": False, "ai": False, "optimizer": False, "label": "Services & équipements"},
        {"id": "client_profile_pct", "rod": False, "ai": False, "optimizer": False, "label": "Répartition clients (%)"},
        {"id": "has_corner", "rod": False, "ai": False, "optimizer": False, "label": "Boutique existante"},
        {"id": "emplacement", "rod": False, "ai": False, "optimizer": False, "label": "Emplacement corner"},
        {"id": "analyze_with_ai", "rod": False, "ai": False, "optimizer": False, "label": "Analyser avec l'IA"},
    ]