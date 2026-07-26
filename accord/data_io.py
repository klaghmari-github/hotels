"""
Lecture / ecriture Excel et normalisations partagees.

Utilise par geo_*, join_data, store, catalog, parallel_*.
Fonctions pures : pas d etat global hors DATA_DIR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

# Codes pays reconnus comme France
FRANCE_COUNTRY_CODES = frozenset({"FR", "FRA", "FRANCE"})


def read_excel(
    path: Path | str,
    *,
    sheet: str | int = 0,
    dtype: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Lit un Excel de facon tolerante (feuille demandee puis index 0).

    Retourne un DataFrame vide si le fichier est absent ou illisible.
    """
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet, dtype=dtype)
    except ValueError:
        try:
            return pd.read_excel(path, sheet_name=0, dtype=dtype)
        except Exception:
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def data_path(*parts: str) -> Path:
    """Chemin sous accord/data/."""
    return DATA_DIR.joinpath(*parts)


def normalize_hotel_code_series(series: pd.Series) -> pd.Series:
    """Strip + vide / nan / none → NA string-safe."""
    out = series.astype(str).str.strip()
    bad = out.str.lower().isin({"", "nan", "none", "<na>", "nat"})
    return out.mask(bad, pd.NA)


def normalize_hotel_code_value(value: Any) -> str:
    """Code hotel normalise (string vide si invalide)."""
    s = str(value or "").strip()
    if not s or s.lower() in {"nan", "none", "<na>", "nat"}:
        return ""
    return s


def is_france_country(series: pd.Series) -> pd.Series:
    """Masque booleen pour lignes France."""
    country = series.astype(str).str.upper().str.strip()
    return country.isin(FRANCE_COUNTRY_CODES)


def filter_france_hotels(
    frame: pd.DataFrame,
    *,
    require_coords: bool = False,
    country_col: str = "hotel_country",
    code_col: str = "hotel_code",
    lat_col: str = "hotel_lat",
    lon_col: str = "hotel_lon",
) -> pd.DataFrame:
    """
    Filtre le parc sur la France, deduplique par code hotel.

    require_coords=True : drop les lignes sans lat/lon valides (meteo, proximite).
    """
    if frame is None or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    if country_col in df.columns:
        df = df[is_france_country(df[country_col])].copy()
    if code_col not in df.columns:
        return df.reset_index(drop=True)
    df[code_col] = normalize_hotel_code_series(df[code_col])
    df = df[df[code_col].notna()].copy()
    if require_coords and lat_col in df.columns and lon_col in df.columns:
        lat = pd.to_numeric(df[lat_col], errors="coerce")
        lon = pd.to_numeric(df[lon_col], errors="coerce")
        df = df[lat.notna() & lon.notna()].copy()
        df[lat_col] = lat.loc[df.index]
        df[lon_col] = lon.loc[df.index]
    df = df.drop_duplicates(subset=[code_col], keep="first")
    return df.reset_index(drop=True)


def cell_to_python(val: Any) -> Any:
    """Convertit une cellule pandas (incl. numpy scalar) en type Python JSON-safe."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:
            return val
    return val


def row_to_dict(row: pd.Series, columns: list[str] | None = None) -> dict[str, Any]:
    """Serie pandas → dict avec valeurs normalisees."""
    cols = columns if columns is not None else list(row.index)
    return {str(c): cell_to_python(row.get(c)) for c in cols}
