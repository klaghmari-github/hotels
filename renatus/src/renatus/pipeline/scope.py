"""
Perimetre hotels partage (sim_v1 / sim_v2 / ml).

Note F0001 : module domaine-specifique hotels, copie tel quel.
F0006 reorganisera ce perimetre hors du coeur pipeline generique.

H5586 est exclu : donnees insuffisantes pour le LOO / la comparaison.
"""

from __future__ import annotations

# Hotels exclus du perimetre d'evaluation et des tables de modelisation.
EXCLUDED_HOTEL_CODES: tuple[str, ...] = ("H5586",)

# 6 hotels pilotes (alignes sim_v1).
PILOT_HOTEL_CODES: tuple[str, ...] = (
    "H2075",
    "HB6A3",
    "H6188",
    "HB5I0",
    "H0373",
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
