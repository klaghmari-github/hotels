"""
Constantes LOO sim_v1 — hotels evalues et chemins.

H5586 (Connected) exclu : donnees trop faibles (3e Connected).
"""

from __future__ import annotations

from pathlib import Path

# Racine projet accor/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PIPELINES_SRC = PROJECT_ROOT / "pipelines" / "src"

# Fichiers source
PILOT_MAP_PATH = DATA_DIR / "rod_pilot_concepts.json"
SALES_PATH = DATA_DIR / "hotel_sales_data.xlsx"
HOTEL_PATH = DATA_DIR / "hotel_data.xlsx"
SIM_DATA_PATH = DATA_DIR / "simulateur_data.xlsx"

# Exports LOO
EXCEL_OLD = DATA_DIR / "eval_sim_v1_old_loo.xlsx"
EXCEL_NEW = DATA_DIR / "eval_sim_v1_new_loo.xlsx"
EXCEL_COMPARE = DATA_DIR / "eval_sim_v1_old_vs_new.xlsx"

# Base DuckDB dediee (ConnectionPipeline)
DB_DIR = PROJECT_ROOT / "duckdb" / "pilotes" / "sim_v1"
DB_PATH = DB_DIR / "sim_v1.duckdb"
PIPELINE_DIR = PROJECT_ROOT / "pipeline_sim_v1"

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")

# Hotel a exclure (Connected, donnees faibles)
EXCLUDED_HOTELS: frozenset[str] = frozenset({"H5586"})

# Hotels evalues (6)
EVAL_HOTELS: dict[str, str] = {
    "H2075": "SIMPLY",
    "HB6A3": "SIMPLY",
    "H6188": "LIBERTY",
    "HB5I0": "LIBERTY",
    "H0373": "CONNECTED",
    "H3546": "CONNECTED",
}

EVAL_CODES: tuple[str, ...] = tuple(EVAL_HOTELS.keys())

# Coeffs marge produits (spec simu)
COEFF_FB = 2.6
COEFF_NFB = 1.45

JOURS_MOIS = 30.5

# Defauts marque (alignes hotel_context / FeatureImputer)
BRAND_GUESTS_DEFAULT: dict[str, float] = {
    "IBIS BUDGET": 1.7,
    "IBIS STYLES": 2.0,
    "NOVOTEL": 1.8,
    "MERCURE": 2.0,
    "IBIS": 1.8,
}

BRAND_TO_DEFAULT: dict[str, float] = {
    "IBIS BUDGET": 0.78,
    "IBIS STYLES": 0.85,
    "NOVOTEL": 0.75,
    "MERCURE": 0.72,
    "IBIS": 0.80,
}

# Coeffs R3 — + si ON, - si OFF (toutes ON en LOO)
CAT_FB: dict[str, float] = {
    "fb_soft_drinks": 0.10,
    "fb_alcohol": 0.05,
    "fb_sweet_snacks": 0.10,
    "fb_sweet_desserts": 0.05,
    "fb_salty_snacks": 0.10,
    "fb_salty_meals": 0.05,
    "fb_gourmet": 0.03,
}

CAT_NFB: dict[str, float] = {
    "nfb_sos": 0.08,
    "nfb_hygiene": 0.05,
    "nfb_cosmetics": 0.03,
    "nfb_kids": 0.08,
    "nfb_apparel": 0.03,
    "nfb_accessories": 0.03,
    "nfb_souvenirs": 0.03,
}

# Pilotes Excel (fallback si aucun pair)
PILOT_FALLBACK: dict[str, dict[str, float]] = {
    "SIMPLY": {
        "nb_chambres": 129.0,
        "guests": 1.7,
        "to": 0.80,
        "ml_ref": 6.0,
        "frigo_ref": 0.0,
        "mix_fb": 0.40,
        "ventes": 231.0,
        "ca_fb": 533.0,
        "ca_nfb": 187.0,
        "ca_10_fb": 133.25,
        "ca_10_nfb": 31.17,
        "ca_1ml_fb": 88.83,
        "ca_1ml_nfb": 31.17,
        "coeff_fb": 2.6,
        "coeff_nfb": 1.45,
        "clients_heb": 129.0 * 1.7 * 0.80 * 30.5,
    },
    "LIBERTY": {
        "nb_chambres": 142.0,
        "guests": 2.2,
        "to": 0.70,
        "ml_ref": 8.0,
        "frigo_ref": 0.0,
        "mix_fb": 0.70,
        "ventes": 312.0,
        "ca_fb": 1055.0,
        "ca_nfb": 424.0,
        "ca_10_fb": 1055.0 * 0.10 / 0.70,
        "ca_10_nfb": 424.0 * 0.10 / 0.30,
        "ca_1ml_fb": 1055.0 / 8.0,
        "ca_1ml_nfb": 424.0 / 8.0,
        "coeff_fb": 2.6,
        "coeff_nfb": 1.45,
        "clients_heb": 142.0 * 2.2 * 0.70 * 30.5,
    },
    "CONNECTED": {
        "nb_chambres": 305.0,
        "guests": 1.8,
        "to": 0.75,
        "ml_ref": 7.0,
        "frigo_ref": 3.0,
        "mix_fb": 0.80,
        "ventes": 534.0,
        "ca_fb": 3503.0,
        "ca_nfb": 131.0,
        "ca_10_fb": 437.875,
        "ca_10_nfb": 65.50,
        "ca_1ml_fb": 3503.0 / 7.0,
        "ca_1ml_nfb": 131.0 / 7.0,
        "ca_1frigo_fb": 3503.0 / 3.0,
        "ca_1frigo_nfb": 131.0 / 3.0,
        "coeff_fb": 2.6,
        "coeff_nfb": 1.45,
        "clients_heb": 305.0 * 1.8 * 0.75 * 30.5,
    },
}
