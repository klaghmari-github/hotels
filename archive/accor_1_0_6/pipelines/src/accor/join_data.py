"""
Jointure All Data — grain hotel × année × mois.

Produit data/all_data.xlsx (feuille all_data).

Règles
------
- Table de gauche = hotel_sales_data : une ligne par
  (hotel_code, annee, mois) où il y a eu de l'activité.
- Left joins : holidays, weather (même clé mois), hotel_data + proximity
  (hotel_code), brand (hotel_brand).
- Seuls les hôtels présents dans les ventes entrent dans all_data.
- fill_weather / fill_proximity (optionnels) : comble via lat/lon
  (désactivés par défaut dans l'UI pour rester réactif).
- Les nulls sont **conservés** ici. L'imputation ML se fait dans model_data.

Anti-doublons : _merge_new n'ajoute que les colonnes encore absentes
(pas de suffixes _x / _y).

Appelé depuis le rebuild admin all_data et en amont de model_data.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.geo_proximity import ProximityFromGeo, as_coord as prox_as_coord
from archive.accor_1_0_6.pipelines.src.accor.geo_weather import WeatherFromGeo, as_coord as weather_as_coord
from archive.accor_1_0_6.pipelines.src.accor.schemas import DATA_DIR, get_schema

DATA_FILENAME = "all_data.xlsx"
DATA_SHEET = "all_data"
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
    """True si la température moyenne (métrique pivot) est absente."""
    if "meteo_temperature_c_mean" in frame.columns:
        return frame["meteo_temperature_c_mean"].isna()
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


def _impute_meteo_in_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Imputation intra-table : pour chaque hôtel, mois manquant
    ← même mois des années antérieures (puis postérieures).
    """
    if frame.empty or "hotel_code" not in frame.columns:
        return frame
    out = frame.copy()
    meteo_cols = [c for c in out.columns if c.startswith("meteo_")]
    if not meteo_cols:
        return out
    if "annee" not in out.columns or "mois" not in out.columns:
        return out

    for code, group in out.groupby(out["hotel_code"].astype(str), sort=False):
        idx_list = list(group.index)
        # index (annee, mois) → position
        by_ym: dict[tuple[int, int], Any] = {}
        for i in idx_list:
            y, m = out.at[i, "annee"], out.at[i, "mois"]
            if pd.isna(y) or pd.isna(m):
                continue
            by_ym[(int(y), int(m))] = i

        years = sorted({y for y, _ in by_ym.keys()})
        for (year, month), i in list(by_ym.items()):
            for col in meteo_cols:
                if pd.notna(out.at[i, col]):
                    continue
                # N-1, N-2, … puis N+1, N+2, …
                candidates = [y for y in years if y < year][::-1] + [
                    y for y in years if y > year
                ]
                for y2 in candidates:
                    j = by_ym.get((y2, month))
                    if j is None:
                        continue
                    val = out.at[j, col]
                    if pd.notna(val):
                        out.at[i, col] = val
                        break
    return out


def _fill_weather_gaps(
    result: pd.DataFrame,
    *,
    years: list[int],
    fetch: bool = True,
) -> pd.DataFrame:
    """
    Complète les lignes sans météo via WeatherFromGeo(lat, lon).

    - Fetch pour **tous** les hôtels ayant des coords (pas seulement un sous-ensemble)
      afin de couvrir les années absentes du fichier weather source.
    - Imputation N←N-1 intégrée dans WeatherFromGeo + passe finale sur le frame.
    """
    if result.empty:
        return result
    out = result.copy()

    # Colonnes météo cibles
    from archive.accor_1_0_6.pipelines.src.accor.geo_weather import meteo_column_names

    for c in meteo_column_names():
        if c not in out.columns:
            out[c] = pd.NA

    if not fetch:
        return _impute_meteo_in_frame(out)

    mask = _meteo_missing_mask(out)
    if not mask.any():
        return _impute_meteo_in_frame(out)

    # Tous les hôtels avec coords (même ceux partiellement remplis)
    need = out[["hotel_code", "hotel_lat", "hotel_lon"]].drop_duplicates(
        subset=["hotel_code"]
    )
    need = need[
        need["hotel_lat"].map(lambda v: weather_as_coord(v) is not None)
        & need["hotel_lon"].map(lambda v: weather_as_coord(v) is not None)
    ]
    if need.empty:
        return _impute_meteo_in_frame(out)

    engine = WeatherFromGeo(years=years)
    fetched = engine.for_hotels(
        need,
        lat_col="hotel_lat",
        lon_col="hotel_lon",
        id_cols=("hotel_code",),
        impute=True,
    )
    if fetched.empty:
        return _impute_meteo_in_frame(out)

    meteo_cols = [c for c in fetched.columns if c.startswith("meteo_")]
    for c in meteo_cols:
        if c not in out.columns:
            out[c] = pd.NA

    fetched = _normalize_keys(fetched, list(JOIN_KEYS_MONTHLY))
    # Évite MultiIndex ambigu
    fetched = fetched.drop_duplicates(subset=list(JOIN_KEYS_MONTHLY), keep="first")
    lookup = {
        (str(r.hotel_code).strip(), int(r.annee), int(r.mois)): r
        for r in fetched.itertuples(index=False)
    }

    # Remplir **toutes** les lignes manquantes (pas seulement le mask initial
    # : après fetch on re-scanne)
    for idx in out.index:
        if pd.notna(out.at[idx, "meteo_temperature_c_mean"]):
            continue
        code = str(out.at[idx, "hotel_code"]).strip()
        try:
            year = int(out.at[idx, "annee"])
            month = int(out.at[idx, "mois"])
        except (TypeError, ValueError):
            continue
        row = lookup.get((code, year, month))
        if row is None:
            continue
        for c in meteo_cols:
            val = getattr(row, c, None)
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                if pd.isna(out.at[idx, c]):
                    out.at[idx, c] = val

    # Dernière passe : imputer depuis d'autres années du même hôtel
    out = _impute_meteo_in_frame(out)
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


def _sales_hotel_codes(sales: pd.DataFrame) -> set[str]:
    """Codes hôtels présents dans hotel_sales_data (au moins une ligne)."""
    if sales is None or sales.empty or "hotel_code" not in sales.columns:
        return set()
    codes = sales["hotel_code"].astype(str).str.strip()
    return {
        c
        for c in codes
        if c and c.lower() not in {"nan", "none", "<na>", ""}
    }


class AllDataBuilder:
    """
    Construit all_data : base ventes + left joins.

    Utilisation:
        frame = AllDataBuilder(fill_weather=False).build()

    Ou via la facade build_joined_dataframe(...) pour l API existante.
    """

    KEY_ORDER = (
        "hotel_code",
        "hotel_name",
        "nom_hotel",
        "hotel_brand",
        "annee",
        "mois",
        "hotel_lat",
        "hotel_lon",
    )

    def __init__(
        self,
        *,
        fill_weather: bool = True,
        fill_proximity: bool = True,
    ) -> None:
        self.fill_weather = fill_weather
        self.fill_proximity = fill_proximity
        self.sales = pd.DataFrame()
        self.hotels = pd.DataFrame()
        self.holidays = pd.DataFrame()
        self.weather = pd.DataFrame()
        self.brand = pd.DataFrame()
        self.proximity = pd.DataFrame()
        self.sales_codes: set[str] = set()

    def load_sources(self) -> "AllDataBuilder":
        self.hotels = _read_source("hotel")
        self.sales = _read_source("sales")
        self.holidays = _read_source("holidays")
        self.weather = _read_source("weather")
        self.brand = _read_source("brand")
        self.proximity = _read_source("proximity")
        return self

    def prepare_sales_spine(self) -> pd.DataFrame | None:
        """Base = mois de vente uniques. None si rien a joindre."""
        sales = self.sales
        if sales is None or sales.empty or "hotel_code" not in sales.columns:
            return None
        sales = _normalize_keys(sales, list(JOIN_KEYS_MONTHLY))
        sales = sales.dropna(subset=["hotel_code", "annee", "mois"])
        sales["hotel_code"] = sales["hotel_code"].astype(str).str.strip()
        sales = sales.drop_duplicates(subset=list(JOIN_KEYS_MONTHLY), keep="last")
        self.sales = sales
        self.sales_codes = _sales_hotel_codes(sales)
        if not self.sales_codes:
            return None
        return sales.copy()

    def restrict_hotels_to_sales(self) -> None:
        """Hotels master = uniquement codes presents dans les ventes."""
        hotels = self.hotels
        sales = self.sales
        codes = self.sales_codes
        if not hotels.empty and "hotel_code" in hotels.columns:
            hotels = hotels.copy()
            hotels["hotel_code"] = hotels["hotel_code"].astype(str).str.strip()
            hotels = hotels[hotels["hotel_code"].isin(codes)].reset_index(drop=True)
        else:
            hotels = (
                sales.drop_duplicates(subset=["hotel_code"])[
                    [
                        c
                        for c in (
                            "hotel_code",
                            "hotel_name",
                            "nom_hotel",
                            "hotel_brand",
                        )
                        if c in sales.columns
                    ]
                ].copy()
            )
            if "hotel_name" not in hotels.columns and "nom_hotel" in hotels.columns:
                hotels["hotel_name"] = hotels["nom_hotel"]
        self.hotels = hotels

    def ensure_proximity(self) -> None:
        if not self.proximity.empty or self.hotels.empty or not self.fill_proximity:
            return
        try:
            from archive.accor_1_0_6.pipelines.src.accor.geo_proximity import ensure_hotel_proximity_data

            self.proximity = ensure_hotel_proximity_data(
                force_refresh=False, hotels=self.hotels, pause_s=1.0
            )
        except Exception:
            self.proximity = pd.DataFrame()

    def left_join_all(self, result: pd.DataFrame) -> pd.DataFrame:
        monthly = list(JOIN_KEYS_MONTHLY)
        if not self.holidays.empty:
            result = _merge_new(result, self.holidays, on=monthly, how="left")
        if not self.weather.empty:
            result = _merge_new(result, self.weather, on=monthly, how="left")
        if not self.proximity.empty and "hotel_code" in self.proximity.columns:
            result = _merge_new(result, self.proximity, on=["hotel_code"], how="left")
        if not self.hotels.empty:
            result = _merge_new(result, self.hotels, on=["hotel_code"], how="left")
            result = _fill_identity(result, self.hotels)
        if (
            not self.brand.empty
            and "Marque" in self.brand.columns
            and "hotel_brand" in result.columns
        ):
            brand_r = self.brand.rename(columns={"Marque": "hotel_brand"})
            result = _merge_new(result, brand_r, on=["hotel_brand"], how="left")
        return result

    def finalize(self, result: pd.DataFrame) -> pd.DataFrame:
        result = result[
            result["hotel_code"].astype(str).str.strip().isin(self.sales_codes)
        ].reset_index(drop=True)
        years = _collect_years(result) or _collect_years(self.sales)
        result = _fill_weather_gaps(
            result, years=years, fetch=self.fill_weather
        )
        result = _fill_proximity_gaps(
            result, self.hotels, fetch=self.fill_proximity
        )
        if not self.hotels.empty:
            result = _fill_identity(result, self.hotels)
        key_order = [c for c in self.KEY_ORDER if c in result.columns]
        other = [c for c in result.columns if c not in key_order]
        result = result[key_order + other]
        sort_cols = [c for c in ("hotel_code", "annee", "mois") if c in result.columns]
        if sort_cols:
            result = result.sort_values(sort_cols, kind="mergesort").reset_index(
                drop=True
            )
        else:
            result = result.reset_index(drop=True)
        return result.loc[:, ~result.columns.duplicated(keep="first")]

    def build(self) -> pd.DataFrame:
        self.load_sources()
        spine = self.prepare_sales_spine()
        if spine is None:
            return pd.DataFrame()
        self.restrict_hotels_to_sales()
        self.ensure_proximity()
        result = self.left_join_all(spine)
        return self.finalize(result)


def build_joined_dataframe(
    *,
    fill_weather: bool = True,
    fill_proximity: bool = True,
) -> pd.DataFrame:
    """
    Facade stable pour l API / UI.

    Base = ventes pilotes, left joins holidays / weather / hotel / proximity / brand.
    """
    return AllDataBuilder(
        fill_weather=fill_weather,
        fill_proximity=fill_proximity,
    ).build()


# Colonnes textuelles / listes : ne jamais les forcer en 0
_NON_NUMERIC_COLS = frozenset(
    {
        "hotel_code",
        "hotel_name",
        "nom_hotel",
        "hotel_brand",
        "hotel_city",
        "hotel_adresse_postale_1",
        "hotel_adresse_postale_2",
        "hotel_code_postal",
        "departement",
        "commune",
        "localisation",
        "Marque",
        "jours_feries",
        "jours_weekend",
        "jours_vacances_scolaires",
        "jours_vacances_hors_feries",
        "jours_holidays",
        "hotel_geo_source",
    }
)


def _is_null(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple)):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_text_cell(value: object) -> object:
    """Normalise une cellule texte (codes département, etc.)."""
    if isinstance(value, (list, tuple)):
        return value
    if _is_null(value):
        return ""
    if isinstance(value, float) and value == int(value):
        # 75.0 → "75" (code département lu comme float)
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value).replace("\u00a0", " ").strip()
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return text


def _looks_like_array_col(series: pd.Series) -> bool:
    sample = series.dropna().head(12)
    if sample.empty:
        return False
    for v in sample:
        if isinstance(v, (list, tuple)):
            return True
        if isinstance(v, str) and v.strip().startswith("["):
            return True
    return False


def fill_numeric_nulls(frame: pd.DataFrame) -> pd.DataFrame:
    """
    **Déprécié pour all_data** — ne plus combler les trous sources.

    Conservé pour compatibilité d'import. Délègue à
    :func:`impute_model.impute_for_model` (moyennes / 0 selon le type)
    pour le pipeline **model_data uniquement**.

    Les fichiers sources (hotel_data, brand, …) et ``all_data.xlsx``
    doivent **garder les NaN** : saisie ultérieure ou imputation au
    moment model_data.
    """
    from archive.accor_1_0_6.pipelines.src.accor.impute_model import impute_for_model

    if frame is None or frame.empty:
        return frame
    out, _ = impute_for_model(frame)
    return out


def data_xlsx_path() -> Path:
    return DATA_DIR / DATA_FILENAME


def save_joined_excel(frame: pd.DataFrame | None = None, **build_kwargs: Any) -> Path:
    """
    Écrit ``accord/data/all_data.xlsx`` (All Data).

    **Ne comble plus** les numériques manquants (pas de moyenne, pas de 0 forcé).
    Les trous restent vides ; l'imputation se fait uniquement dans
    ``model_data`` (voir ``impute_model.impute_for_model``).
    """
    if frame is None:
        frame = build_joined_dataframe(**build_kwargs)
    else:
        frame = frame.copy()

    # Textes : "" pour null (affichage) ; numériques : NaN conservé
    text_cols = []
    for col in frame.columns:
        if col in _NON_NUMERIC_COLS or _looks_like_array_col(frame[col]):
            text_cols.append(col)
            frame[col] = [
                (
                    ""
                    if _is_null(v)
                    else (
                        str(v)
                        if not isinstance(v, (list, tuple))
                        else v
                    )
                )
                for v in frame[col].tolist()
            ]
        # numériques : laisser NaN (openpyxl → cellule vide)

    path = data_xlsx_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=DATA_SHEET)
        # Forcer type string openpyxl sur colonnes texte
        try:
            ws = writer.sheets[DATA_SHEET]
            headers = {cell.value: cell.column for cell in ws[1]}
            for col in text_cols:
                idx = headers.get(col)
                if not idx:
                    continue
                for row in range(2, ws.max_row + 1):
                    cell = ws.cell(row=row, column=idx)
                    val = cell.value
                    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
                        cell.value = "\u00a0"
                    else:
                        cell.value = str(val)
                    cell.data_type = "s"
                    cell.number_format = "@"
            # Ne PAS forcer 0 sur les numériques vides
        except Exception:
            pass
    return path


def ensure_data_xlsx(*, force_rebuild: bool = False, **build_kwargs: Any) -> Path:
    """Garantit la présence de ``all_data.xlsx`` (jointure si absent ou forcé)."""
    path = data_xlsx_path()
    # Migration douce : ancien nom data.xlsx
    legacy = DATA_DIR / "data.xlsx"
    if not path.exists() and legacy.exists() and not force_rebuild:
        legacy.rename(path)
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
