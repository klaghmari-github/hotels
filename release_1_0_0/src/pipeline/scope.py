"""
Perimetre hotels partage (sim_v1 / sim_v2 / ml).

H5586 est exclu : donnees insuffisantes pour le LOO / la comparaison.
"""

from __future__ import annotations

# Hotels exclus du perimetre d'evaluation et des tables de modelisation.
# H5586 : donnees insuffisantes. H6188 Boulogne : plus dans la liste metier (remplace par H1249 Rennes).
EXCLUDED_HOTEL_CODES: tuple[str, ...] = ("H5586", "H6188")

# Pilotes concepts (mapping solution) — H1249 Rennes inclus (ventes pas encore en t_sales).
PILOT_HOTEL_CODES: tuple[str, ...] = (
    "H2075",   # SIMPLY / Adixon
    "HB6A3",   # CONNECTED / Selfly
    "H0373",   # CONNECTED / Selfly
    "H1249",   # CONNECTED / Boost (Rennes)
    "HB5I0",   # LIBERTY / Adixon
    "H3546",   # CONNECTED / Digitizme
)

# Sous-ensemble avec tickets dans t_sales (LOO / modelisation).
PILOT_HOTEL_CODES_WITH_SALES: tuple[str, ...] = (
    "H2075",
    "HB6A3",
    "H0373",
    "HB5I0",
    "H3546",
)


def sql_excluded_hotels_list() -> str:
    """Liste SQL quotee pour NOT IN (...)."""
    return ", ".join(f"'{code}'" for code in EXCLUDED_HOTEL_CODES)


def sql_hotel_not_excluded(column: str = "hotel_code") -> str:
    """Clause SQL : colonne hors hotels exclus."""
    return (
        f"CAST({column} AS VARCHAR) NOT IN ({sql_excluded_hotels_list()})"
    )


def is_excluded(hotel_code: str | None) -> bool:
    if hotel_code is None:
        return False
    return str(hotel_code).strip().upper() in {
        c.upper() for c in EXCLUDED_HOTEL_CODES
    }
