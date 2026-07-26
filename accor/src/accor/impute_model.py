#!/usr/bin/env python3
"""
Imputation réservée à model_data (entraînement / prédiction).

Important : on ne remplit pas hotel_data, sales ni all_data. Les sources
gardent les trous ; seule la table ML est complétée.

Règle pour une moyenne numérique manquante
------------------------------------------
1. Moyenne des hôtels **pilotes** (présents dans hotel_sales_data) de la
   **même** catégorie de marque.
2. Sinon moyenne des pilotes des catégories **directement** inférieure
   et supérieure (échelle economy → luxury ; lifestyle / partner ont
   leurs voisins dédiés — voir brand_category).
3. Sinon moyenne tous pilotes, puis moyenne globale, puis 0.

Comptages, flags, montants de vente, dummies → 0 (pas de moyenne).

Point d'entrée : impute_for_model(frame). Appelé par model_data lors
du rebuild.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from accor.brand_category import (
    impute_series_by_brand_category,
    pilot_mask_for_frame,
    resolve_category_series,
)

# Colonnes ou 0 est le bon « manque » (pas de moyenne)
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
    r"^hotel_has_",
    r"^weather_ok$",
    r"^proximity_ok$",
    r"^shard_id$",
)

# Colonnes ou une moyenne a du sens
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
        "brand_category",
        "geo_source",
        "weather_error",
        "proximity_error",
    }:
        return True
    if col.startswith("jours_"):
        return True
    if col.endswith("_error") or col.endswith("_source"):
        return True
    if col.startswith("cat_"):
        # dummies categorie : traite a part (zero-fill)
        return False
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        coerced = pd.to_numeric(series, errors="coerce")
        non_null = series.notna()
        if non_null.any() and coerced[non_null].notna().mean() >= 0.8:
            return False
        return True
    return False


def impute_for_model(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Remplit les trous numeriques pour l'apprentissage / prediction.

    Returns
    -------
    (frame_imputed, report)
    """
    if frame is None or frame.empty:
        return frame, {"n_filled": 0, "strategy": "category_pilot"}

    out = frame.copy()
    categories = resolve_category_series(out)
    # expose pour debug / model (non target)
    out["brand_category"] = categories
    pilot_mask = pilot_mask_for_frame(out)

    report: dict[str, Any] = {
        "columns": {},
        "n_filled": 0,
        "strategy": "pilot_category_then_adjacent",
        "n_pilots_rows": int(pilot_mask.sum()),
        "categories_present": sorted(
            {str(c) for c in categories.dropna().unique()}
        ),
    }

    for col in list(out.columns):
        if col in {"brand_category"}:
            continue
        if col.startswith("_") and col != "_is_eval":
            continue
        series = out[col]

        if col.startswith("cat_"):
            # dummies : NaN → 0
            n = int(pd.to_numeric(series, errors="coerce").isna().sum())
            if n:
                out[col] = pd.to_numeric(series, errors="coerce").fillna(0)
                report["columns"][col] = {"strategy": "cat_dummy_zero", "n": n}
                report["n_filled"] += n
            continue

        if _is_id_or_text(col, series):
            if col.startswith("jours_"):
                out[col] = series.apply(
                    lambda v: v
                    if isinstance(v, (list, tuple))
                    else (
                        "[]"
                        if pd.isna(v) or v is None or str(v).strip() == ""
                        else v
                    )
                )
            continue

        if pd.api.types.is_bool_dtype(series):
            n = int(series.isna().sum())
            if n:
                out[col] = series.fillna(False)
                report["columns"][col] = {"strategy": "bool_false", "n": n}
                report["n_filled"] += n
            continue

        numeric = pd.to_numeric(series, errors="coerce")
        if series.notna().any() and numeric.notna().sum() == 0:
            continue
        if not pd.api.types.is_numeric_dtype(series) and numeric.notna().mean() < 0.5:
            continue

        n_miss = int(numeric.isna().sum())
        if n_miss == 0:
            out[col] = numeric
            continue

        if _match_any(col, ZERO_FILL_PATTERNS) or col in {"annee", "mois"}:
            if col in {"annee", "mois"}:
                # rare : moyenne globale pilote
                filled, detail = impute_series_by_brand_category(
                    numeric, categories, pilot_mask
                )
                out[col] = filled
                report["columns"][col] = {
                    "strategy": "category_pilot_mean",
                    **detail,
                }
                report["n_filled"] += n_miss
            else:
                out[col] = numeric.fillna(0)
                report["columns"][col] = {"strategy": "zero", "n": n_miss}
                report["n_filled"] += n_miss
            continue

        if _match_any(col, MEAN_FILL_PATTERNS):
            use_category = True
        else:
            name = col.lower()
            if any(
                k in name
                for k in ("nombre", "montant", "nb_", "count", "flag", "has_")
            ):
                out[col] = numeric.fillna(0)
                report["columns"][col] = {"strategy": "zero", "n": n_miss}
                report["n_filled"] += n_miss
                continue
            use_category = True

        if use_category:
            filled, detail = impute_series_by_brand_category(
                numeric, categories, pilot_mask
            )
            out[col] = filled
            report["columns"][col] = {
                "strategy": "pilot_category_then_adjacent",
                **detail,
            }
            report["n_filled"] += n_miss

    # filet final numeriques restants
    for col in out.select_dtypes(include=["number"]).columns:
        if out[col].isna().any():
            n = int(out[col].isna().sum())
            out[col] = out[col].fillna(0)
            prev = report["columns"].get(col, {})
            report["columns"][col] = {
                **prev,
                "strategy": prev.get("strategy", "final_zero") + "+final_zero",
                "n_final_zero": n,
            }
            report["n_filled"] += n

    return out, report


def impute_hotel_features(
    features: dict[str, Any],
    *,
    hotel_brand: str | None = None,
    brand_category: str | None = None,
    reference_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Impute un dict de features pour **un** hotel (inference).

    Utilise model_data ou all_data comme reference pilote si fourni,
    sinon recharge model_data.xlsx.
    """
    from accor.data_io import DATA_DIR, read_excel

    ref = reference_frame
    if ref is None or ref.empty:
        path = DATA_DIR / "model_data.xlsx"
        ref = read_excel(path, sheet=0)
        if ref.empty:
            path = DATA_DIR / "all_data.xlsx"
            ref = read_excel(path, sheet=0)

    out = dict(features)
    if not ref.empty:
        # fake one-row frame to reuse category logic
        row = {**out}
        if hotel_brand and "hotel_brand" not in row:
            row["hotel_brand"] = hotel_brand
        if brand_category:
            for c in (
                "economy",
                "midscale",
                "premium",
                "luxury",
                "lifestyle_by_ennismore",
                "partner_brands",
            ):
                row[f"cat_{c}"] = 1 if c == brand_category else 0

        # Build combined frame: reference + target row
        target = pd.DataFrame([row])
        # align columns
        for c in ref.columns:
            if c not in target.columns:
                target[c] = pd.NA
        combined = pd.concat([ref, target[ref.columns.intersection(target.columns)]], ignore_index=True)
        # mark last row as non-pilot if hotel not in sales — still fill from pilots
        imputed, _ = impute_for_model(combined)
        last = imputed.iloc[-1]
        for k in out:
            if k in last.index:
                val = last[k]
                if out.get(k) is None or (isinstance(out.get(k), float) and pd.isna(out.get(k))):
                    if pd.notna(val):
                        out[k] = val.item() if hasattr(val, "item") else val
    return out
