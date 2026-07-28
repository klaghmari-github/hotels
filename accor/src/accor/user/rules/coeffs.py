"""
Coefficients et tables de référence pour les règles ROD.

  RULE3_FB_COEFFS / RULE3_NFB_COEFFS  poids catégories (Excel simu)
  RULE3_BASELINE_*                    sommes de référence règle 3
  LIBERTY_NFB_NEEDS                   besoins qui ouvrent le chemin LIBERTY
  CLIENT_NEED_LABELS                  libellés UI
  BRAND_TO_CODE                       marque texte → code court
  BRANDS_REQUIRING_LIBERTY_PATH       marques avec contrainte reco

Utilisé par revenue, recommendation et /api/meta.
"""

from __future__ import annotations

from typing import Dict, Set

# ---------------------------------------------------------------------------
# Règle 3 — poids d'impact (Excel SIMULATEUR)
#
# Dans l'Excel ce sont des **exemples** de parts sur le **total** des ventes
# (pas seulement au sein de F&B ou N-F&B). Leur somme n'atteint pas 100 %
# (≈ 48 % F&B + 34 % N-F&B) : ce sont des leviers ±X % sur le CA canal.
#
# Dans le simulateur data / modélisation, les % réels par sous-catégorie
# sont recalculés : nb_ventes(sous_cat) / nb_ventes(total) → somme ≈ 100 %.
# ---------------------------------------------------------------------------
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
    "nfb_kids": 0.05,
    "nfb_apparel": 0.05,
    "nfb_accessories": 0.05,
    "nfb_souvenirs": 0.03,
}

RULE3_BASELINE_FB = sum(RULE3_FB_COEFFS.values())
RULE3_BASELINE_NF = sum(RULE3_NFB_COEFFS.values())

# Règle reco : hôtel ≥ 50 ch. + ≥ 1 des 5 lifestyle → LIBERTY
# (Cosmétiques, Kids, Ready-to-wear, Accessories, Souvenirs)
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
