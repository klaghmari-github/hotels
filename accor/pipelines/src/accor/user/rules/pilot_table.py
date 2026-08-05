"""
Constantes pilotes fidèles à ``simulateur_rules.html`` (zone gauche Excel).

Utilisées par le moteur de revenus / coûts user (run_user).
Les valeurs « simu » de marge N-F&B sont 1,45 pour les 3 concepts
(même si le pilote Liberty/Connected affiche d'autres coeffs en zone gauche).
"""

from __future__ import annotations

from typing import Any

JOURS_MOIS = 30.5

# Coefficients Règle 3 (Excel) — + si coché, − si non coché
CAT_FB: dict[str, float] = {
    "fb_soft_drinks": 0.10,  # Drinks without alcohol
    "fb_alcohol": 0.05,  # Drinks with alcohol
    "fb_sweet_snacks": 0.10,  # Sugary dry
    "fb_sweet_desserts": 0.05,  # Sugary fresh
    "fb_salty_snacks": 0.10,  # Salty dry
    "fb_salty_meals": 0.05,  # Salty fresh
    "fb_gourmet": 0.03,  # Gourmet
}

CAT_NFB: dict[str, float] = {
    "nfb_sos": 0.08,
    "nfb_hygiene": 0.05,
    "nfb_cosmetics": 0.03,
    "nfb_kids": 0.08,
    "nfb_apparel": 0.03,  # Ready-to-wear
    "nfb_accessories": 0.03,
    "nfb_souvenirs": 0.03,
}

# Lifestyle N-F&B pour arbre reco
LIBERTY_LIFESTYLE = frozenset(
    {
        "nfb_cosmetics",
        "nfb_kids",
        "nfb_apparel",
        "nfb_accessories",
        "nfb_souvenirs",
    }
)

# Agencement € / ML (amorti 84 mois)
AGENCEMENT_EUR_PER_ML: dict[str, dict[str, float]] = {
    "SIMPLY": {"CLASSIC": 1000.0, "PREMIUM": 1200.0, "BESPOKE": 2200.0},
    "LIBERTY": {"CLASSIC": 1000.0, "PREMIUM": 1200.0, "BESPOKE": 2200.0},
    "CONNECTED": {"CLASSIC": 800.0, "PREMIUM": 1000.0, "BESPOKE": 1600.0},
}
AGENCEMENT_AMORT_MONTHS = 84.0

# PILOT table — source : simulateur_rules.html §4 + §14
PILOT: dict[str, dict[str, Any]] = {
    "SIMPLY": {
        "nb_chambres": 129.0,
        "guests": 1.7,
        "to": 0.80,
        "ml_ref": 6.0,
        "frigo_ref": None,
        "mix_fb": 0.40,
        "ventes": 231.0,
        "ca_fb": 533.0,
        "ca_nfb": 187.0,
        # CA HT pour ±10 % de mix (zone gauche R2)
        "ca_10_fb": 133.25,
        "ca_10_nfb": 31.17,
        # CA HT par mètre linéaire (zone gauche R4)
        "ca_1ml_fb": 88.83,
        "ca_1ml_nfb": 31.17,
        "coeff_fb": 2.6,
        "coeff_nfb": 1.45,
        # clients hébergés pilote = ch × guests × TO × 30.5
        "clients_heb": 129.0 * 1.7 * 0.80 * JOURS_MOIS,  # 5350.92
    },
    "LIBERTY": {
        "nb_chambres": 142.0,
        "guests": 2.2,
        "to": 0.70,
        "ml_ref": 8.0,
        "frigo_ref": None,
        "mix_fb": 0.70,
        "ventes": 312.0,
        "ca_fb": 1055.0,
        "ca_nfb": 424.0,
        # dérivés : CA×0.1/mix
        "ca_10_fb": 1055.0 * 0.10 / 0.70,  # ≈ 150.714
        "ca_10_nfb": 424.0 * 0.10 / 0.30,  # ≈ 141.333
        "ca_1ml_fb": 1055.0 / 8.0,  # ≈ 131.875
        "ca_1ml_nfb": 424.0 / 8.0,  # 53.0
        "coeff_fb": 2.6,
        "coeff_nfb": 1.45,  # simu (pilote Excel = 2.0 hors simu)
        "clients_heb": 142.0 * 2.2 * 0.70 * JOURS_MOIS,
    },
    "CONNECTED": {
        "nb_chambres": 305.0,
        "guests": 1.8,
        "to": 0.75,
        "ml_ref": 7.0,  # info ; R4 utilise frigos
        "frigo_ref": 3.0,
        "mix_fb": 0.80,
        "ventes": 534.0,
        "ca_fb": 3503.0,
        "ca_nfb": 131.0,
        "ca_10_fb": 437.875,
        "ca_10_nfb": 65.50,
        # CA unitaire par frigo froid (CA_pilote / 3)
        "ca_1frigo_fb": 3503.0 / 3.0,
        "ca_1frigo_nfb": 131.0 / 3.0,
        "coeff_fb": 2.6,
        "coeff_nfb": 1.45,
        "clients_heb": 305.0 * 1.8 * 0.75 * JOURS_MOIS,
    },
}


def get_pilot(concept: str) -> dict[str, Any]:
    c = (concept or "").upper().strip()
    if c not in PILOT:
        raise KeyError(f"Concept inconnu: {concept}")
    return PILOT[c]
