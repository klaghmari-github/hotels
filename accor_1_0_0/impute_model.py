#!/usr/bin/env python3
"""
Imputation **uniquement pour model_data**.

Les fichiers sources (hotel_data, brand, sales, weather…) gardent les trous
vides. Après jointure (all_data peut encore contenir des nulls), model_data
comble les NaN numériques pour l'apprentissage :

* **comptages / ventes / flags** → 0
* **taux, TO, pourcentages, météo, lat/lon, tailles** → moyenne
  (priorité : moyenne **marque**, sinon moyenne **globale** de la colonne)
* **textes / id** → inchangés (ou ``""`` si purement textuel manquant)

Utilisé par ``model_data.build_model_dataframe``.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

# Colonnes où 0 est le bon « manque » (pas de moyenne)
ZERO_FILL_PATTERNS = (
    r"^nombre_",
    r"^montant_",
    r"^nb_",
    r"^Nb_",
    r"^commerce_",
    r"^pct_",
    r"^cat_",
    r"_is_eval$",
    r"^zone_scolaire_",
    r"^hotel_f_b_",
    r"^hotel_non_f_b_",
    r"^hotel_dispo_",
    r"^hotel_corner_",
    r"^hotel_loisirs_top_",
    r"^hotel_contrat_type_",
    r"^hotel_corner_actuel_existe",
)

# Colonnes où une moyenne a du sens
MEAN_FILL_PATTERNS = (
    r"^hotel_to_",
    r"^hotel_nb_chambres$",
    r"^hotel_affaires",
    r"^hotel_loisirs_pct",
    r"^hotel_international",
    r"^hotel_national",
    r"^hotel_metres",
    r"^hotel_contrat_signe",
    r"^hotel_derniere",
    r"^hotel_lobby",
    r"^hotel_lat$",
    r"^hotel_lon$",
    r"^meteo_",
    r"^plage_",
    r"^guests",
    r"^taux_",
    r"^ca_",
    r"^clients_",
)


def _match_any(name: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, name) for p in patterns)


def _is_id_or_text(col: str, series: pd.Series) -> bool:
    if col in {
        "hotel_code",
        "hotel_name",
        "nom_hotel",
        "hotel_brand",
        "Marque",
        "hotel_adresse_postale_1",
        "hotel_adresse_postale_2",
        "hotel_city",
        "departement",
        "commune",
        "localisation",
        "logo_path",
    }:
        return True
    if col.startswith("jours_"):
        return True
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        # object quasi-numérique → pas purement texte
        coerced = pd.to_numeric(series, errors="coerce")
        non_null = series.notna()
        if non_null.any() and coerced[non_null].notna().mean() >= 0.8:
            return False
        return True
    return False


def impute_for_model(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Remplit les trous numériques pour l'entraînement.

    Returns
    -------
    (frame_imputed, report)
    """
    if frame is None or frame.empty:
        return frame, {"n_filled": 0}

    out = frame.copy()
    brand_col = None
    for c in ("hotel_brand", "Marque"):
        if c in out.columns:
            brand_col = c
            break

    report: dict[str, Any] = {"columns": {}, "n_filled": 0}

    for col in list(out.columns):
        if col.startswith("_") and col != "_is_eval":
            continue
        series = out[col]

        if _is_id_or_text(col, series):
            if col.startswith("jours_"):
                out[col] = series.apply(
                    lambda v: v
                    if isinstance(v, (list, tuple))
                    else ("[]" if pd.isna(v) or v is None or str(v).strip() == "" else v)
                )
            continue

        # booléens
        if pd.api.types.is_bool_dtype(series):
            n = int(series.isna().sum())
            if n:
                out[col] = series.fillna(False)
                report["columns"][col] = {"strategy": "bool_false", "n": n}
                report["n_filled"] += n
            continue

        numeric = pd.to_numeric(series, errors="coerce")
        # si pas assez numérique, skip
        if series.notna().any() and numeric.notna().sum() == 0:
            continue
        if not pd.api.types.is_numeric_dtype(series) and numeric.notna().mean() < 0.5:
            continue

        n_miss = int(numeric.isna().sum())
        if n_miss == 0:
            out[col] = numeric
            continue

        # stratégie
        if _match_any(col, ZERO_FILL_PATTERNS) or col in {"annee", "mois"}:
            # annee/mois manquants → 0 est mauvais mais rare ; laisse mean si absents
            if col in {"annee", "mois"}:
                strategy = "global_mean"
            else:
                strategy = "zero"
        elif _match_any(col, MEAN_FILL_PATTERNS):
            strategy = "brand_or_global_mean"
        else:
            # défaut : counts-like → 0, sinon mean
            name = col.lower()
            if any(k in name for k in ("nombre", "montant", "nb_", "count", "flag", "has_")):
                strategy = "zero"
            else:
                strategy = "brand_or_global_mean"

        if strategy == "zero":
            filled = numeric.fillna(0)
            out[col] = filled
            report["columns"][col] = {"strategy": "zero", "n": n_miss}
            report["n_filled"] += n_miss
            continue

        # mean strategies
        global_mean = float(numeric.mean()) if numeric.notna().any() else 0.0
        if strategy == "global_mean" or brand_col is None:
            filled = numeric.fillna(global_mean)
            out[col] = filled
            report["columns"][col] = {
                "strategy": "global_mean",
                "n": n_miss,
                "value": global_mean,
            }
            report["n_filled"] += n_miss
            continue

        # brand then global
        brands = out[brand_col].astype(str)
        brand_means = numeric.groupby(brands).transform("mean")
        filled = numeric.copy()
        miss = filled.isna()
        filled = filled.where(~miss, brand_means)
        still = filled.isna()
        filled = filled.where(~still, global_mean)
        out[col] = filled
        report["columns"][col] = {
            "strategy": "brand_mean_then_global",
            "n": n_miss,
            "global_mean": global_mean,
        }
        report["n_filled"] += n_miss

    # filet final numériques restants
    for col in out.select_dtypes(include=["number"]).columns:
        if out[col].isna().any():
            n = int(out[col].isna().sum())
            out[col] = out[col].fillna(0)
            report["columns"][col] = report["columns"].get(col, {"strategy": "final_zero", "n": n})
            report["n_filled"] += n

    return out, report
