"""Agrégation météo mensuelle indépendante du cas d'usage hôtel.

Entrée : coordonnées géographiques + liste d'années.
Sortie : indicateurs météo par (année, mois) + colonnes de coordonnées
telles que fournies en entrée (pas de renommage).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

try:
    from meteostat import Hourly, Point

    HAS_METEOSTAT = True
except Exception:  # pragma: no cover - dépendance optionnelle
    HAS_METEOSTAT = False

READABLE_WEATHER = {
    "temp": "temperature_c",
    "dwpt": "point_rosee_c",
    "rhum": "humidite_pct",
    "prcp": "precipitations_mm",
    "snow": "neige_mm",
    "wspd": "vent_kmh",
    "pres": "pression_hpa",
    "tsun": "ensoleillement_min",
}

METEO_RAW_COLS = ("temp", "dwpt", "rhum", "prcp", "snow", "wspd", "pres", "tsun")

# Colonnes temporelles toujours présentes en sortie (les noms lat/lon
# suivent lat_col / lon_col fournis par l'appelant).
OUTPUT_TIME_COLS = ("annee", "mois")


def default_target_years(now: datetime | None = None) -> tuple[int, ...]:
    """Année en cours si non fournie."""
    year = (now or datetime.utcnow()).year
    return (year,)


def resolve_years(years: Sequence[int] | None) -> tuple[int, ...]:
    """Normalise une liste d'années (uniques, triées). Vide → année en cours."""
    if years is None:
        return default_target_years()
    cleaned: list[int] = []
    for value in years:
        try:
            year = int(value)
        except (TypeError, ValueError):
            continue
        if year not in cleaned:
            cleaned.append(year)
    if not cleaned:
        return default_target_years()
    return tuple(sorted(cleaned))


def as_coord(value: Any) -> float | None:
    """Convertit une valeur en latitude/longitude, ou None si invalide."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        coord = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(coord):
        return None
    return coord


class MonthlyWeather:
    """Calcule les indicateurs météo mensuels pour des points géographiques.

    Indépendant du domaine hôtel : ne gère ni adresse, ni géocodage, ni I/O.
    La génération des coordonnées à partir d'une adresse est hors périmètre.

    Paramètres
    ----------
    years :
        Années pour lesquelles calculer les indicateurs.
        Si ``None`` ou vide → année en cours uniquement.
    """

    def __init__(self, years: Sequence[int] | None = None) -> None:
        self.years = resolve_years(years)

    @property
    def year_window(self) -> tuple[int, int]:
        """Borne inclusive (min, max) des années demandées."""
        return min(self.years), max(self.years)

    def for_point(
        self,
        lat: float,
        lon: float,
        *,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> pd.DataFrame:
        """Indicateurs pour un point ``(lat, lon)`` sur toutes les années.

        Retourne un DataFrame indexé conceptuellement par
        ``(annee, mois)`` avec colonnes de coordonnées (noms ``lat_col`` /
        ``lon_col``), ``annee``, ``mois`` et les métriques ``meteo_*``
        (mean / min / max).

        La grille année × mois (12 mois par année demandée) est toujours
        produite ; les cellules sans observation restent NaN.
        Les noms de colonnes de coordonnées ne sont pas renommés.
        """
        lat_f = as_coord(lat)
        lon_f = as_coord(lon)
        if lat_f is None or lon_f is None:
            return self._empty_grid(
                lat=lat_f, lon=lon_f, lat_col=lat_col, lon_col=lon_col
            )

        try:
            by_ym = self.fetch_by_year_month(lat_f, lon_f)
        except Exception:
            by_ym = {}
        return self._grid_from_observations(
            lat_f, lon_f, by_ym, lat_col=lat_col, lon_col=lon_col
        )

    @classmethod
    def compute_meteo_final(
        cls,
        geo: pd.DataFrame | Sequence[Mapping[str, Any]],
        years: Sequence[int] | None = None,
        *,
        lat_col: str = "lat",
        lon_col: str = "lon",
        id_cols: Sequence[str] | None = None,
        impute: bool = True,
    ) -> pd.DataFrame:
        """Construit la dataframe météo finale à partir de la géo et des années.

        Pipeline tout-en-un (indépendant du domaine hôtel) :

        1. récupération Meteostat sur les années cibles (+ année N-1 si imputation) ;
        2. grille ``annee × mois`` par point géographique ;
        3. imputation des mois manquants par le même mois de l'année précédente ;
        4. filtre sur les années cibles demandées.

        Parameters
        ----------
        geo :
            Données de géolocalisation (DataFrame ou mappings) avec lat/lon.
        years :
            Liste d'années cibles. ``None`` / vide → année en cours.
        lat_col, lon_col :
            Noms des colonnes de coordonnées dans ``geo`` ; réutilisés à
            l'identique en sortie (aucun renommage).
        id_cols :
            Identifiants optionnels à propager (ex. ``hotel_code``).
        impute :
            Si ``True`` (défaut), complète les NaN via N-1 et charge l'année
            précédente en plus des années cibles.

        Returns
        -------
        pd.DataFrame
            Une ligne par (point, année, mois) avec les colonnes de
            coordonnées sous les noms ``lat_col`` / ``lon_col`` (aucun
            renommage), ``annee``, ``mois``, éventuels ``id_cols``,
            et métriques ``meteo_*``.
        """
        target_years = resolve_years(years)
        if impute:
            fetch_years = tuple(sorted(set(target_years) | {min(target_years) - 1}))
        else:
            fetch_years = target_years

        engine = cls(years=fetch_years)
        raw = engine.for_points(
            geo,
            lat_col=lat_col,
            lon_col=lon_col,
            id_cols=id_cols,
        )
        if raw.empty:
            return raw

        if impute:
            present_ids = [c for c in (id_cols or ()) if c in raw.columns]
            group_cols: Sequence[str] = (
                present_ids if present_ids else (lat_col, lon_col)
            )
            raw = impute_previous_year_month(
                raw,
                group_cols=group_cols,
                year_col="annee",
                month_col="mois",
            )

        out = raw[raw["annee"].isin(target_years)].copy()
        sort_keys = [
            c
            for c in list(id_cols or ()) + [lat_col, lon_col, "annee", "mois"]
            if c in out.columns
        ]
        if sort_keys:
            out = out.sort_values(sort_keys, kind="mergesort").reset_index(drop=True)
        else:
            out = out.reset_index(drop=True)
        return out

    def for_points(
        self,
        locations: pd.DataFrame | Sequence[Mapping[str, Any]],
        *,
        lat_col: str = "lat",
        lon_col: str = "lon",
        id_cols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Indicateurs pour plusieurs points.

        Parameters
        ----------
        locations :
            DataFrame ou séquence de mappings avec au minimum lat/lon.
        lat_col, lon_col :
            Noms des colonnes de coordonnées en entrée et en sortie
            (défaut ``lat`` / ``lon``). Pas de renommage.
        id_cols :
            Colonnes d'identifiants optionnelles à propager en sortie
            (ex. un id de point). Aucune sémantique métier imposée.

        Returns
        -------
        pd.DataFrame
            Une ligne par (point, année, mois) avec les indicateurs météo.
        """
        frame = self._as_locations_frame(locations, lat_col=lat_col, lon_col=lon_col)
        keep_ids = [c for c in (id_cols or ()) if c in frame.columns]

        parts: list[pd.DataFrame] = []
        for _, row in frame.iterrows():
            point_df = self.for_point(
                row[lat_col],
                row[lon_col],
                lat_col=lat_col,
                lon_col=lon_col,
            )
            for col in keep_ids:
                point_df[col] = row[col]
            # Ordre : ids puis grille météo
            ordered = list(keep_ids) + [c for c in point_df.columns if c not in keep_ids]
            parts.append(point_df[ordered])

        if not parts:
            base_cols = list(keep_ids) + [lat_col, lon_col, *OUTPUT_TIME_COLS]
            return pd.DataFrame(columns=base_cols)

        return pd.concat(parts, ignore_index=True)

    def fetch_by_year_month(
        self,
        lat: float,
        lon: float,
        *,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> dict[tuple[int, int], dict[str, float]]:
        """Télécharge et agrège Meteostat en ``(année, mois) → métriques``.

        Méthode de bas niveau : pas de grille forcée, seulement les mois
        réellement observés. Les noms de colonnes sont déjà lisibles
        (``meteo_temperature_c_mean``, …).
        """
        if not HAS_METEOSTAT:
            return {}

        window_start, window_end = self.year_window
        start_y = int(start_year if start_year is not None else window_start)
        end_y = int(end_year if end_year is not None else window_end)

        now = datetime.utcnow()
        start = datetime(start_y, 1, 1)
        end = min(now, datetime(end_y, 12, 31, 23, 59, 59))
        if end <= start:
            return {}

        frame = Hourly(Point(float(lat), float(lon)), start, end).fetch()
        if frame is None or getattr(frame, "empty", True):
            return {}

        return self.aggregate_hourly(frame)

    @staticmethod
    def aggregate_hourly(
        frame: pd.DataFrame,
        *,
        time_col: str = "time",
        fallback_year: int | None = None,
    ) -> dict[tuple[int, int], dict[str, float]]:
        """Agrège un DataFrame horaire Meteostat en indicateurs mensuels.

        Parameters
        ----------
        frame :
            Sortie brute Meteostat (index temporel ou colonne ``time``).
        time_col :
            Nom de la colonne datetime après ``reset_index``.
        fallback_year :
            Année de rattachement si la date est manquante
            (défaut = année UTC courante).
        """
        work = frame.reset_index() if time_col not in getattr(frame, "columns", []) else frame.copy()
        if time_col not in work.columns:
            return {}

        times = pd.to_datetime(work[time_col], errors="coerce")
        work = work.loc[times.notna()].copy()
        if work.empty:
            return {}
        times = times.loc[times.notna()]

        year_fallback = fallback_year if fallback_year is not None else datetime.utcnow().year
        work["_year"] = times.dt.year.fillna(year_fallback).astype(int).to_numpy()
        work["_month"] = times.dt.month.fillna(1).astype(int).to_numpy()

        by_ym: dict[tuple[int, int], dict[str, float]] = {}
        for (year, month), group in work.groupby(["_year", "_month"], sort=True):
            year_i = int(year)
            month_i = int(month)
            if month_i < 1 or month_i > 12:
                continue
            metrics = MonthlyWeather._metrics_for_group(group)
            if metrics:
                by_ym[(year_i, month_i)] = metrics
        return by_ym

    @staticmethod
    def _metrics_for_group(group: pd.DataFrame) -> dict[str, float]:
        metrics: dict[str, float] = {}
        for col in METEO_RAW_COLS:
            if col not in group.columns:
                continue
            series = pd.to_numeric(group[col], errors="coerce")
            valid = series.dropna()
            if valid.empty:
                continue
            readable = READABLE_WEATHER.get(col, col)
            metrics[f"meteo_{readable}_mean"] = float(valid.mean())
            metrics[f"meteo_{readable}_min"] = float(valid.min())
            metrics[f"meteo_{readable}_max"] = float(valid.max())
        return metrics

    def _grid_from_observations(
        self,
        lat: float,
        lon: float,
        by_ym: Mapping[tuple[int, int], Mapping[str, float]],
        *,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for year in self.years:
            for month in range(1, 13):
                row: dict[str, Any] = {
                    lat_col: lat,
                    lon_col: lon,
                    "annee": int(year),
                    "mois": month,
                }
                obs = by_ym.get((int(year), month))
                if obs:
                    row.update(obs)
                rows.append(row)
        return pd.DataFrame(rows)

    def _empty_grid(
        self,
        *,
        lat: float | None = None,
        lon: float | None = None,
        lat_col: str = "lat",
        lon_col: str = "lon",
    ) -> pd.DataFrame:
        rows = [
            {lat_col: lat, lon_col: lon, "annee": int(year), "mois": month}
            for year in self.years
            for month in range(1, 13)
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def _as_locations_frame(
        locations: pd.DataFrame | Sequence[Mapping[str, Any]],
        *,
        lat_col: str,
        lon_col: str,
    ) -> pd.DataFrame:
        if isinstance(locations, pd.DataFrame):
            frame = locations.copy()
        else:
            frame = pd.DataFrame(list(locations))
        if frame.empty:
            return frame
        if lat_col not in frame.columns or lon_col not in frame.columns:
            raise ValueError(
                f"Colonnes de coordonnées absentes : attendu '{lat_col}' et '{lon_col}', "
                f"reçu {list(frame.columns)}"
            )
        return frame


def impute_previous_year_month(
    frame: pd.DataFrame,
    *,
    group_cols: Sequence[str] = ("lat", "lon"),
    year_col: str = "annee",
    month_col: str = "mois",
    value_prefix: str = "meteo_",
) -> pd.DataFrame:
    """Impute les mois manquants par le même mois de l'année précédente.

    Règles :
    1. Pour chaque groupe (ex. point geo), chaque ``(année, mois)`` et chaque
       colonne ``meteo_*`` : si NaN → valeur du même mois en N-1 (puis N-2, …).
    2. Jamais de fill à ``0.0``.
    3. Si aucune année antérieure n'a la valeur, le NaN est conservé.

    Indépendant du domaine hôtel : le regroupement se fait sur ``group_cols``
    (par défaut les coordonnées).
    """
    if frame.empty:
        return frame

    numeric_cols = [c for c in frame.columns if c.startswith(value_prefix)]
    if not numeric_cols:
        return frame

    out = frame.copy()
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    missing_keys = [c for c in (year_col, month_col) if c not in out.columns]
    if missing_keys:
        return out

    out[year_col] = pd.to_numeric(out[year_col], errors="coerce")
    out[month_col] = pd.to_numeric(out[month_col], errors="coerce")
    out = out.dropna(subset=[year_col, month_col]).copy()
    out[year_col] = out[year_col].astype(int)
    out[month_col] = out[month_col].astype(int)

    present_groups = [c for c in group_cols if c in out.columns]
    if not present_groups:
        return _impute_single_group(out, numeric_cols, year_col, month_col)

    parts: list[pd.DataFrame] = []
    for _, group_df in out.groupby(list(present_groups), sort=False, dropna=False):
        parts.append(_impute_single_group(group_df, numeric_cols, year_col, month_col))
    if not parts:
        return out
    return pd.concat(parts, ignore_index=True)


def _impute_single_group(
    group_df: pd.DataFrame,
    numeric_cols: list[str],
    year_col: str,
    month_col: str,
) -> pd.DataFrame:
    df = group_df.sort_values([year_col, month_col], kind="mergesort").copy()
    years = sorted(df[year_col].dropna().unique().tolist())
    if not years:
        return df

    for col in numeric_cols:
        if col not in df.columns:
            continue
        known: dict[tuple[int, int], float] = {}
        for _, row in df.iterrows():
            val = row[col]
            if pd.notna(val):
                known[(int(row[year_col]), int(row[month_col]))] = float(val)

        filled: list[float | None] = []
        min_year = min(years) - 5
        for _, row in df.iterrows():
            year = int(row[year_col])
            month = int(row[month_col])
            val = row[col]
            if pd.notna(val):
                filled.append(float(val))
                known[(year, month)] = float(val)
                continue

            imputed: float | None = None
            prev = year - 1
            while prev >= min_year:
                candidate = known.get((prev, month))
                if candidate is not None and pd.notna(candidate):
                    imputed = float(candidate)
                    break
                prev -= 1

            filled.append(imputed)
            if imputed is not None:
                known[(year, month)] = imputed

        df[col] = filled

    return df
