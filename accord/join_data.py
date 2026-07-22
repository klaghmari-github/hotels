"""
Jointure « All Data » — grille parfaite hotel × année × mois.

Règles métier
-------------
- **Base** = tous les hôtels de ``hotel_data`` (identité + lat/lon).
- **Grille** = chaque hôtel × chaque année pertinente × 12 mois.
- **Ventes** : peuvent rester vides (seul domaine « optionnel »).
- **Tout le reste** doit être rempli dès que l'on a des coords :
  - ``hotel_name`` / brand / adresse depuis hotel_data
  - météo via :class:`geo_weather.WeatherFromGeo`
  - proximité via :class:`geo_proximity.ProximityFromGeo`
  - holidays depuis le fichier (ou laissé si déjà présent)

Anti-doublons : une colonne déjà présente n'est jamais ré-ajoutée.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from geo_proximity import ProximityFromGeo, as_coord as prox_as_coord
from geo_weather import WeatherFromGeo, as_coord as weather_as_coord
from schemas import DATA_DIR, get_schema

DATA_FILENAME = "data.xlsx"
DATA_SHEET = "data"
JOIN_KEYS_MONTHLY = ("hotel_code", "annee", "mois")


def _read_source(dataset_id: str) -> pd.DataFrame:
    schema = get_schema(dataset_id)
    path = schema.path
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=schema.sheet)
    except ValueError:
        return pd.read_excel(path, sheet_name=0)


def _normalize_keys(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    out = frame.copy()
    if "hotel_code" in keys and "hotel_code" in out.columns:
        out["hotel_code"] = out["hotel_code"].astype(str).str.strip()
        out.loc[
            out["hotel_code"].isin(["", "nan", "None", "<NA>"]), "hotel_code"
        ] = pd.NA
    for col in ("annee", "mois"):
        if col in keys and col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    if "hotel_brand" in out.columns:
        out["hotel_brand"] = out["hotel_brand"].astype(str).str.strip()
    if "Marque" in out.columns:
        out["Marque"] = out["Marque"].astype(str).str.strip()
    return out


def _merge_new(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    on: list[str],
    how: str = "left",
) -> pd.DataFrame:
    """Merge en n'ajoutant que les colonnes absentes de ``left``."""
    if left is None or left.empty:
        return right.copy() if right is not None and not right.empty else pd.DataFrame()
    if right is None or right.empty:
        return left
    keys = [k for k in on if k in left.columns and k in right.columns]
    if not keys:
        return left
    left_c = _normalize_keys(left, keys)
    right_c = _normalize_keys(right, keys)
    new_cols = [c for c in right_c.columns if c not in left_c.columns and c not in keys]
    if not new_cols:
        return left_c
    right_slim = right_c[keys + new_cols].drop_duplicates(subset=keys, keep="first")
    return left_c.merge(right_slim, on=keys, how=how)


def _collect_years(*frames: pd.DataFrame) -> list[int]:
    years: set[int] = set()
    for frame in frames:
        if frame is None or frame.empty or "annee" not in frame.columns:
            continue
        for y in pd.to_numeric(frame["annee"], errors="coerce").dropna().unique():
            years.add(int(y))
    if not years:
        y = datetime.utcnow().year
        years = {y - 2, y - 1, y}
    return sorted(years)


def _build_grid(hotels: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """
    Grille complète : 1 ligne par (hôtel, année, mois).

    Identité toujours présente : code, name, brand, lat, lon.
    """
    id_cols = [
        c
        for c in (
            "hotel_code",
            "hotel_name",
            "hotel_brand",
            "hotel_lat",
            "hotel_lon",
            "hotel_city",
        )
        if c in hotels.columns
    ]
    rows: list[dict[str, Any]] = []
    for _, h in hotels.iterrows():
        base = {c: h.get(c) for c in id_cols}
        code = base.get("hotel_code")
        if code is None or (isinstance(code, float) and pd.isna(code)):
            continue
        base["hotel_code"] = str(code).strip()
        for year in years:
            for month in range(1, 13):
                rows.append({**base, "annee": int(year), "mois": int(month)})
    return pd.DataFrame(rows)


def _fill_identity(result: pd.DataFrame, hotels: pd.DataFrame) -> pd.DataFrame:
    """Force hotel_name / brand / lat / lon depuis hotel_data (jamais vide si connu)."""
    if hotels.empty or "hotel_code" not in result.columns:
        return result
    out = result.copy()
    hotel_idx = hotels.drop_duplicates(subset=["hotel_code"]).set_index(
        hotels["hotel_code"].astype(str).str.strip()
    )
    for col in ("hotel_name", "hotel_brand", "hotel_lat", "hotel_lon", "hotel_city"):
        if col not in hotel_idx.columns:
            continue
        if col not in out.columns:
            out[col] = pd.NA
        mapped = out["hotel_code"].astype(str).str.strip().map(hotel_idx[col])
        # Remplir les trous + forcer la valeur canonique du master hotel
        out[col] = mapped.where(mapped.notna(), out[col])
    # nom_hotel = hotel_name si manquant
    if "hotel_name" in out.columns:
        if "nom_hotel" not in out.columns:
            out["nom_hotel"] = out["hotel_name"]
        else:
            out["nom_hotel"] = out["nom_hotel"].where(
                out["nom_hotel"].notna() & (out["nom_hotel"].astype(str).str.strip() != ""),
                out["hotel_name"],
            )
    return out


def _meteo_missing_mask(frame: pd.DataFrame) -> pd.Series:
    """True si aucune colonne meteo_* n'est renseignée sur la ligne."""
    meteo_cols = [c for c in frame.columns if c.startswith("meteo_")]
    if not meteo_cols:
        return pd.Series(True, index=frame.index)
    return frame[meteo_cols].isna().all(axis=1)


def _proximity_missing_mask(frame: pd.DataFrame) -> pd.Series:
    prox_cols = [
        c
        for c in frame.columns
        if c.startswith("commerce_") or c.startswith("plage_")
    ]
    if not prox_cols:
        return pd.Series(True, index=frame.index)
    return frame[prox_cols].isna().all(axis=1)


def _fill_weather_gaps(
    result: pd.DataFrame,
    *,
    years: list[int],
    fetch: bool = True,
) -> pd.DataFrame:
    """Complète les lignes sans météo via WeatherFromGeo(lat, lon)."""
    if not fetch or result.empty:
        return result
    out = result.copy()
    mask = _meteo_missing_mask(out)
    if not mask.any():
        return out

    # Points uniques à interroger
    need = out.loc[mask, ["hotel_code", "hotel_lat", "hotel_lon"]].drop_duplicates(
        subset=["hotel_code"]
    )
    need = need[
        need["hotel_lat"].map(lambda v: weather_as_coord(v) is not None)
        & need["hotel_lon"].map(lambda v: weather_as_coord(v) is not None)
    ]
    if need.empty:
        return out

    engine = WeatherFromGeo(years=years)
    fetched = engine.for_hotels(
        need,
        lat_col="hotel_lat",
        lon_col="hotel_lon",
        id_cols=("hotel_code",),
    )
    if fetched.empty:
        return out

    meteo_cols = [c for c in fetched.columns if c.startswith("meteo_")]
    # Ajouter colonnes manquantes
    for c in meteo_cols:
        if c not in out.columns:
            out[c] = pd.NA

    # Index (hotel_code, annee, mois) → métriques
    fetched = _normalize_keys(fetched, list(JOIN_KEYS_MONTHLY))
    lookup = fetched.set_index(["hotel_code", "annee", "mois"])

    for idx in out.index[mask]:
        code = str(out.at[idx, "hotel_code"]).strip()
        year = int(out.at[idx, "annee"]) if pd.notna(out.at[idx, "annee"]) else None
        month = int(out.at[idx, "mois"]) if pd.notna(out.at[idx, "mois"]) else None
        if year is None or month is None:
            continue
        key = (code, year, month)
        if key not in lookup.index:
            continue
        row = lookup.loc[key]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        for c in meteo_cols:
            if c in row.index and pd.isna(out.at[idx, c]):
                out.at[idx, c] = row[c]
    return out


def _fill_proximity_gaps(
    result: pd.DataFrame,
    hotels: pd.DataFrame,
    *,
    fetch: bool = True,
) -> pd.DataFrame:
    """Complète les colonnes proximité (statiques par hôtel) via ProximityFromGeo."""
    if not fetch or result.empty:
        return result
    out = result.copy()

    # S'assurer que les colonnes proximité existent
    engine = ProximityFromGeo()
    prox_cols = ProximityFromGeo.proximity_columns()
    for c in prox_cols:
        if c not in out.columns:
            out[c] = pd.NA

    mask = _proximity_missing_mask(out)
    if not mask.any():
        return out

    codes_need = (
        out.loc[mask, "hotel_code"].astype(str).str.strip().dropna().unique().tolist()
    )
    if not codes_need:
        return out

    hotel_src = hotels.copy() if not hotels.empty else out.drop_duplicates("hotel_code")
    hotel_src["hotel_code"] = hotel_src["hotel_code"].astype(str).str.strip()
    targets = hotel_src[hotel_src["hotel_code"].isin(codes_need)][
        [c for c in ("hotel_code", "hotel_name", "hotel_lat", "hotel_lon") if c in hotel_src.columns]
    ].drop_duplicates("hotel_code")
    targets = targets[
        targets["hotel_lat"].map(lambda v: prox_as_coord(v) is not None)
        & targets["hotel_lon"].map(lambda v: prox_as_coord(v) is not None)
    ]
    if targets.empty:
        return out

    prox_df = engine.for_hotels(
        targets,
        lat_col="hotel_lat",
        lon_col="hotel_lon",
        id_cols=("hotel_code",),
        pause_s=0.8,
    )
    if prox_df.empty:
        return out

    prox_df = _normalize_keys(prox_df, ["hotel_code"])
    lookup = prox_df.set_index("hotel_code")

    for idx in out.index[mask]:
        code = str(out.at[idx, "hotel_code"]).strip()
        if code not in lookup.index:
            continue
        row = lookup.loc[code]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        for c in prox_cols:
            if c in row.index and pd.isna(out.at[idx, c]):
                out.at[idx, c] = row[c]
    return out


def build_joined_dataframe(
    *,
    fill_weather: bool = True,
    fill_proximity: bool = True,
) -> pd.DataFrame:
    """
    Construit la table All Data complète.

    1. Grille parfaite depuis hotel_data × années × 12 mois
    2. Jointure sales / holidays / weather / brand (left)
    3. Identité forcée depuis hotel_data
    4. Comblement météo + proximité via lat/lon
    """
    hotels = _read_source("hotel")
    sales = _read_source("sales")
    holidays = _read_source("holidays")
    weather = _read_source("weather")
    brand = _read_source("brand")

    if hotels.empty:
        # Sans master hôtel on ne peut pas garantir l'identité
        base = sales if not sales.empty else (holidays if not holidays.empty else weather)
        if base.empty:
            return pd.DataFrame()
        result = base.copy()
    else:
        years = _collect_years(sales, holidays, weather)
        result = _build_grid(hotels, years)

    # Jointures left (ventes peuvent rester vides)
    if not sales.empty:
        result = _merge_new(result, sales, on=list(JOIN_KEYS_MONTHLY), how="left")
    if not holidays.empty:
        result = _merge_new(result, holidays, on=list(JOIN_KEYS_MONTHLY), how="left")
    if not weather.empty:
        result = _merge_new(result, weather, on=list(JOIN_KEYS_MONTHLY), how="left")

    # Hotel master (toutes colonnes fiche)
    if not hotels.empty:
        result = _merge_new(result, hotels, on=["hotel_code"], how="left")
        result = _fill_identity(result, hotels)

    # Brand
    if not brand.empty and "Marque" in brand.columns and "hotel_brand" in result.columns:
        brand_r = brand.rename(columns={"Marque": "hotel_brand"})
        result = _merge_new(result, brand_r, on=["hotel_brand"], how="left")

    years = _collect_years(result)

    # Comblement auto météo / proximité
    result = _fill_weather_gaps(result, years=years, fetch=fill_weather)
    result = _fill_proximity_gaps(result, hotels, fetch=fill_proximity)

    # Ré-identité au cas où
    if not hotels.empty:
        result = _fill_identity(result, hotels)

    # Ordre colonnes
    key_order = [
        c
        for c in (
            "hotel_code",
            "hotel_name",
            "nom_hotel",
            "hotel_brand",
            "annee",
            "mois",
            "hotel_lat",
            "hotel_lon",
        )
        if c in result.columns
    ]
    other = [c for c in result.columns if c not in key_order]
    result = result[key_order + other]

    sort_cols = [c for c in ("hotel_code", "annee", "mois") if c in result.columns]
    if sort_cols:
        result = result.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
    else:
        result = result.reset_index(drop=True)

    # Dedup colonnes au cas où
    result = result.loc[:, ~result.columns.duplicated(keep="first")]
    return result


def data_xlsx_path() -> Path:
    return DATA_DIR / DATA_FILENAME


def save_joined_excel(frame: pd.DataFrame | None = None, **build_kwargs: Any) -> Path:
    """Écrit ``accord/data/data.xlsx`` (All Data)."""
    if frame is None:
        frame = build_joined_dataframe(**build_kwargs)
    path = data_xlsx_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=DATA_SHEET)
    return path


def ensure_data_xlsx(*, force_rebuild: bool = False, **build_kwargs: Any) -> Path:
    path = data_xlsx_path()
    if force_rebuild or not path.exists():
        return save_joined_excel(**build_kwargs)
    return path


def join_meta() -> dict[str, Any]:
    path = ensure_data_xlsx(force_rebuild=False)
    try:
        frame = pd.read_excel(path, sheet_name=DATA_SHEET)
    except Exception:
        frame = pd.read_excel(path, sheet_name=0)
    return {
        "path": str(path),
        "rows": len(frame),
        "columns": list(frame.columns),
        "n_columns": len(frame.columns),
    }
