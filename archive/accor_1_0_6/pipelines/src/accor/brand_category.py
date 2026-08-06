"""
Catégories de marque Accor et moyennes « pilotes » pour l'imputation ML.

Catégories (dummies cat_* dans hotel_brand_data / jointure) :
  economy, midscale, premium, luxury,
  lifestyle_by_ennismore, partner_brands

Échelle de gamme pour voisins directs :
  economy < midscale < premium < luxury
  lifestyle_by_ennismore  →  midscale + premium
  partner_brands          →  economy + midscale

Un hôtel **pilote** = présent dans hotel_sales_data (a déjà des ventes).
Les moyennes d'imputation se calculent d'abord sur ce sous-ensemble,
pour coller au parc qui a réellement un corner / un historique.

Utilisé par impute_model ; pas d'écriture fichier ici.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.data_io import DATA_DIR, read_excel

# Ordre de gamme (voisins = indices adjacents)
CATEGORY_LADDER: list[str] = [
    "economy",
    "midscale",
    "premium",
    "luxury",
]

# Toutes les categories connues (dummies cat_*)
ALL_CATEGORIES: tuple[str, ...] = (
    "economy",
    "midscale",
    "premium",
    "luxury",
    "lifestyle_by_ennismore",
    "partner_brands",
)

CAT_DUMMY_COLS: tuple[str, ...] = tuple(f"cat_{c}" for c in ALL_CATEGORIES)


def normalize_brand_name(brand: Any) -> str:
    return str(brand or "").strip().upper().replace("_", " ")


def category_from_dummies(row: pd.Series | dict[str, Any]) -> str | None:
    """Premiere categorie active parmi les dummies cat_*."""
    for cat in ALL_CATEGORIES:
        col = f"cat_{cat}"
        try:
            val = row.get(col) if hasattr(row, "get") else row[col]
        except Exception:
            val = None
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        try:
            if int(float(val)) == 1:
                return cat
        except (TypeError, ValueError):
            if str(val).strip() in {"1", "True", "true"}:
                return cat
    return None


def adjacent_categories(category: str | None) -> list[str]:
    """
    Categories directement inferieure et superieure.

    Pour lifestyle / partner : les deux voisins de gamme les plus proches.
    """
    if not category:
        return []
    cat = str(category).strip().lower().removeprefix("cat_")
    if cat in CATEGORY_LADDER:
        i = CATEGORY_LADDER.index(cat)
        out: list[str] = []
        if i > 0:
            out.append(CATEGORY_LADDER[i - 1])
        if i < len(CATEGORY_LADDER) - 1:
            out.append(CATEGORY_LADDER[i + 1])
        return out
    if cat == "lifestyle_by_ennismore":
        return ["midscale", "premium"]
    if cat == "partner_brands":
        return ["economy", "midscale"]
    return []


@lru_cache(maxsize=1)
def brand_to_category_map() -> dict[str, str]:
    """Marque (upper) → categorie depuis hotel_brand_data.xlsx."""
    path = DATA_DIR / "hotel_brand_data.xlsx"
    df = read_excel(path, sheet=0)
    out: dict[str, str] = {}
    if df.empty:
        return out
    name_col = "Marque" if "Marque" in df.columns else None
    if name_col is None:
        for c in ("marque", "hotel_brand", "brand"):
            if c in df.columns:
                name_col = c
                break
    if name_col is None:
        return out
    for _, row in df.iterrows():
        name = normalize_brand_name(row.get(name_col))
        if not name or name in {"NAN", "NONE"}:
            continue
        cat = category_from_dummies(row)
        if cat:
            out[name] = cat
    return out


@lru_cache(maxsize=1)
def pilot_hotel_codes() -> frozenset[str]:
    """Hotels pilotes = au moins une ligne de vente."""
    path = DATA_DIR / "hotel_sales_data.xlsx"
    df = read_excel(path, sheet=0, dtype={"hotel_code": str})
    if df.empty or "hotel_code" not in df.columns:
        return frozenset()
    codes = (
        df["hotel_code"]
        .astype(str)
        .str.strip()
        .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
        .dropna()
        .unique()
        .tolist()
    )
    return frozenset(str(c) for c in codes)


def resolve_category_series(frame: pd.DataFrame) -> pd.Series:
    """
    Serie de categories par ligne (economy, midscale, …).

    Priorite : dummies cat_* deja jointes, sinon map marque → categorie.
    """
    if frame is None or frame.empty:
        return pd.Series(dtype=object)

    # 1) dummies
    present = [c for c in CAT_DUMMY_COLS if c in frame.columns]
    if present:
        cats: list[str | None] = []
        for _, row in frame[present].iterrows():
            cats.append(category_from_dummies(row))
        series = pd.Series(cats, index=frame.index, dtype=object)
        if series.notna().any():
            # complete trous via marque
            if series.isna().any() and "hotel_brand" in frame.columns:
                bmap = brand_to_category_map()
                brands = frame["hotel_brand"].map(normalize_brand_name)
                fill = brands.map(bmap)
                series = series.fillna(fill)
            return series

    # 2) marque seule
    if "hotel_brand" in frame.columns:
        bmap = brand_to_category_map()
        return frame["hotel_brand"].map(normalize_brand_name).map(bmap)

    return pd.Series([None] * len(frame), index=frame.index, dtype=object)


def pilot_mask_for_frame(frame: pd.DataFrame) -> pd.Series:
    """Masque lignes appartenant a un hotel pilote (ventes)."""
    pilots = pilot_hotel_codes()
    if not pilots or "hotel_code" not in frame.columns:
        # si pas de code : toutes les lignes non-eval ou toutes
        return pd.Series(True, index=frame.index)
    codes = frame["hotel_code"].astype(str).str.strip()
    return codes.isin(pilots)


def mean_for_category(
    values: pd.Series,
    categories: pd.Series,
    pilot_mask: pd.Series,
    category: str | None,
) -> tuple[float | None, str]:
    """
    Moyenne des valeurs pilotes pour une categorie.

    Returns
    -------
    (mean_or_None, strategy_label)
    """
    vals = pd.to_numeric(values, errors="coerce")
    if category:
        m = pilot_mask & (categories.astype(str) == str(category)) & vals.notna()
        if m.any():
            return float(vals.loc[m].mean()), f"pilot_category:{category}"

    # Voisins : moyenne combinee inferieure + superieure
    neigh = adjacent_categories(category)
    if neigh:
        m = pilot_mask & categories.astype(str).isin(neigh) & vals.notna()
        if m.any():
            return float(vals.loc[m].mean()), f"pilot_adjacent:{'+'.join(neigh)}"

    # Tous les pilotes
    m = pilot_mask & vals.notna()
    if m.any():
        return float(vals.loc[m].mean()), "pilot_global"

    # Toute la colonne
    if vals.notna().any():
        return float(vals.mean()), "global_mean"

    return None, "none"


def impute_series_by_brand_category(
    values: pd.Series,
    categories: pd.Series,
    pilot_mask: pd.Series,
) -> tuple[pd.Series, dict[str, Any]]:
    """
    Remplit les NaN d'une serie numerique par moyenne categorie pilote
    (puis categories adjacentes, puis global pilote).
    """
    vals = pd.to_numeric(values, errors="coerce")
    out = vals.copy()
    miss = out.isna()
    if not miss.any():
        return out, {"n": 0, "strategies": {}}

    # Precompute means per category among pilots
    cat_means: dict[str, float] = {}
    for cat in ALL_CATEGORIES:
        m = pilot_mask & (categories.astype(str) == cat) & vals.notna()
        if m.any():
            cat_means[cat] = float(vals.loc[m].mean())

    pilot_global = (
        float(vals.loc[pilot_mask & vals.notna()].mean())
        if (pilot_mask & vals.notna()).any()
        else (float(vals.mean()) if vals.notna().any() else 0.0)
    )
    global_mean = float(vals.mean()) if vals.notna().any() else 0.0

    strategies: dict[str, int] = {}
    for idx in out.index[miss]:
        cat = categories.loc[idx]
        cat_s = str(cat) if cat is not None and not (isinstance(cat, float) and pd.isna(cat)) else None
        if cat_s in cat_means:
            out.loc[idx] = cat_means[cat_s]
            strategies["pilot_category"] = strategies.get("pilot_category", 0) + 1
            continue
        neigh = adjacent_categories(cat_s)
        neigh_vals = [cat_means[n] for n in neigh if n in cat_means]
        if neigh_vals:
            out.loc[idx] = float(sum(neigh_vals) / len(neigh_vals))
            # also pool raw pilots of neighbors (more accurate if uneven n)
            m = pilot_mask & categories.astype(str).isin(neigh) & vals.notna()
            if m.any():
                out.loc[idx] = float(vals.loc[m].mean())
            strategies["pilot_adjacent"] = strategies.get("pilot_adjacent", 0) + 1
            continue
        out.loc[idx] = pilot_global if (pilot_mask & vals.notna()).any() else global_mean
        strategies["pilot_or_global"] = strategies.get("pilot_or_global", 0) + 1

    return out, {"n": int(miss.sum()), "strategies": strategies, "category_means": cat_means}


def clear_caches() -> None:
    brand_to_category_map.cache_clear()
    pilot_hotel_codes.cache_clear()
