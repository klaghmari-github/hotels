"""Coefficients Règle 3 Excel — mapping besoins clients ↔ catégories SIMULATEUR *."""

from __future__ import annotations

from typing import Dict, Set

# Règle 3 — colonnes H (F&B) et O (NON-F&B), feuille SIMULATEUR SIMPLY
RULE3_FB_COEFFS: Dict[str, float] = {
    "fb_soft_drinks": 0.10,
    "fb_alcohol": 0.05,
    "fb_sweet_snacks": 0.10,
    "fb_sweet_desserts": 0.05,
    "fb_salty_snacks": 0.10,
    "fb_salty_meals": 0.05,
    "fb_gourmet": 0.03,
}

RULE3_NFB_COEFFS: Dict[str, float] = {
    "nfb_sos": 0.08,
    "nfb_hygiene": 0.05,
    "nfb_cosmetics": 0.03,
    "nfb_kids": 0.05,  # Excel H67 ; colonne O67 vide
    "nfb_apparel": 0.05,  # Excel H68 / Ready-to-wear
    "nfb_accessories": 0.05,  # Excel H69
    "nfb_souvenirs": 0.03,
}

# Règle #2 reco concept — au moins une catégorie NON-F&B parmi ces besoins
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

# Cumuls pilote « toutes catégories cochées » (H75 / P75 Excel SIMPLY)
RULE3_BASELINE_FB = sum(RULE3_FB_COEFFS.values())
RULE3_BASELINE_NF = sum(RULE3_NFB_COEFFS.values())