#!/usr/bin/env python3
"""
Retire des fichiers **sources** les valeurs injectées par moyenne.

Règle produit
-------------
* hotel_data / brand / … : si manquant → **vide** (saisie ultérieure)
* model_data uniquement : imputation (voir ``impute_model.py``)

Pour ``hotel_data``, on vide les cellules dont la valeur est un **mode massif**
(≥ ``min_mode_count`` hôtels) sur des colonnes de profil (TO, mix clients…).
Les valeurs réellement distinctes (saisie manuelle) sont conservées.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HOTEL_XLSX = DATA / "hotel_data.xlsx"

# Profils souvent comblés par moyenne globale dans les prototypes
PROFILE_COLS = [
    "hotel_contrat_signe_annee",
    "hotel_derniere_reno",
    "hotel_lobby_derniere_reno",
    "hotel_to_annuel",
    "hotel_to_le_plus_bas_taux",
    "hotel_to_le_plus_haut_taux",
    "hotel_affaires_pct",
    "hotel_loisirs_pct",
    "hotel_international_pct",
    "hotel_national_pct",
    "hotel_corner_de_vente_actuel_metres_lineaires",
]


def clear_modal_fills(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    min_mode_count: int = 4,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Pour chaque colonne, si une valeur apparaît ≥ min_mode_count fois,
    on la considère comme un fill par défaut et on la remet à NaN.
    """
    out = frame.copy()
    report: dict[str, Any] = {}
    for col in columns:
        if col not in out.columns:
            continue
        s = pd.to_numeric(out[col], errors="coerce")
        if s.notna().sum() == 0:
            continue
        # mode
        vc = s.value_counts(dropna=True)
        if vc.empty:
            continue
        mode_val = vc.index[0]
        mode_n = int(vc.iloc[0])
        if mode_n < min_mode_count:
            report[col] = {"cleared": 0, "reason": f"mode_n={mode_n}<{min_mode_count}"}
            continue
        # année entière unique plausible (ex. 2020) : encore suspect si ≥4
        mask = s == mode_val
        n_clear = int(mask.sum())
        out.loc[mask, col] = pd.NA
        report[col] = {
            "cleared": n_clear,
            "mode_value": float(mode_val) if pd.notna(mode_val) else None,
            "mode_n": mode_n,
        }
    return out, report


def clean_hotel_data(
    path: Path | None = None,
    *,
    min_mode_count: int = 4,
) -> dict[str, Any]:
    path = path or HOTEL_XLSX
    df = pd.read_excel(path)
    cleaned, report = clear_modal_fills(
        df, PROFILE_COLS, min_mode_count=min_mode_count
    )
    # garder les booléens déjà NaN ; ne pas forcer 0
    cleaned.to_excel(path, index=False, sheet_name="Sheet1")
    return {
        "ok": True,
        "path": str(path),
        "n_rows": len(cleaned),
        "cleared": report,
        "n_nulls_after": int(cleaned.isna().sum().sum()),
    }


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Vide les moyennes injectées dans hotel_data")
    p.add_argument("--min-mode-count", type=int, default=4)
    args = p.parse_args()
    print(json.dumps(clean_hotel_data(min_mode_count=args.min_mode_count), indent=2))


if __name__ == "__main__":
    main()
