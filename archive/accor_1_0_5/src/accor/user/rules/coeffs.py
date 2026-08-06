"""
Coefficients et tables de référence pour les règles ROD (iso simulateur_rules.html).
"""

from __future__ import annotations

from typing import Dict, Set

from archive.accor_1_0_5.src.accor.user.rules.pilot_table import CAT_FB, CAT_NFB, LIBERTY_LIFESTYLE

# Alias historiques (même contenu que pilot_table)
RULE3_FB_COEFFS: Dict[str, float] = dict(CAT_FB)
RULE3_NFB_COEFFS: Dict[str, float] = dict(CAT_NFB)

# Cumuls max si toutes catégories ON (R3 : mult = 1 + Σ±coeff)
RULE3_BASELINE_FB = sum(RULE3_FB_COEFFS.values())  # 0.48
RULE3_BASELINE_NF = sum(RULE3_NFB_COEFFS.values())  # 0.33 (somme des 7 coeffs Excel)

LIBERTY_NFB_NEEDS: Set[str] = set(LIBERTY_LIFESTYLE)

BRAND_TO_CODE: Dict[str, str] = {
    "IBIS BUDGET": "IBB",
    "IBIS STYLES": "IBS",
    "IBIS": "IBIS",
    "NOVOTEL": "NOV",
    "MERCURE": "MER",
}

BRANDS_REQUIRING_LIBERTY_PATH = {"NOV", "MER"}

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
