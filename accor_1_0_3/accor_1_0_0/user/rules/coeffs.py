"""Coefficients Règle 3 Excel + mapping marques (ROD Paramètres & règles)."""

from __future__ import annotations

from typing import Dict, Set

# F&B — colonnes H SIMULATEUR *
RULE3_FB_COEFFS: Dict[str, float] = {
    "fb_soft_drinks": 0.10,
    "fb_alcohol": 0.05,
    "fb_sweet_snacks": 0.10,
    "fb_sweet_desserts": 0.05,
    "fb_salty_snacks": 0.10,
    "fb_salty_meals": 0.05,
    "fb_gourmet": 0.03,
}

# NON-F&B — colonnes O
RULE3_NFB_COEFFS: Dict[str, float] = {
    "nfb_sos": 0.08,
    "nfb_hygiene": 0.05,
    "nfb_cosmetics": 0.03,
    "nfb_kids": 0.05,
    "nfb_apparel": 0.05,
    "nfb_accessories": 0.05,
    "nfb_souvenirs": 0.03,
}

RULE3_BASELINE_FB = sum(RULE3_FB_COEFFS.values())
RULE3_BASELINE_NF = sum(RULE3_NFB_COEFFS.values())

# Règle reco #2 — au moins une catégorie N-F&B « lifestyle »
LIBERTY_NFB_NEEDS: Set[str] = {
    "nfb_cosmetics",
    "nfb_kids",
    "nfb_apparel",
    "nfb_accessories",
    "nfb_souvenirs",
}

BRAND_TO_CODE: Dict[str, str] = {
    "IBIS BUDGET": "IBB",
    "IBIS STYLES": "IBS",
    "IBIS": "IBIS",
    "NOVOTEL": "NOV",
    "MERCURE": "MER",
}

BRANDS_REQUIRING_LIBERTY_PATH = {"NOV", "MER"}

# Libellés UI besoins clients
CLIENT_NEED_LABELS: Dict[str, str] = {
    "fb_soft_drinks": "Boissons non alcoolisées",
    "fb_alcohol": "Boissons alcoolisées",
    "fb_salty_snacks": "Nourriture salée (snacks)",
    "fb_salty_meals": "Nourriture salée (plats)",
    "fb_sweet_snacks": "Nourriture sucrée (snacks)",
    "fb_sweet_desserts": "Nourriture sucrée (desserts)",
    "fb_gourmet": "Épicerie fine",
    "nfb_sos": "Produits SOS",
    "nfb_hygiene": "Hygiène",
    "nfb_cosmetics": "Cosmétiques",
    "nfb_kids": "Articles pour enfants",
    "nfb_apparel": "Prêt-à-porter",
    "nfb_accessories": "Accessoires",
    "nfb_souvenirs": "Souvenirs",
}
