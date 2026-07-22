"""
WeatherFromGeo — météo mensuelle à partir de (lat, lon).

Indépendant du domaine hôtel : seules les coordonnées comptent.
Source : Meteostat (horaire → agrégation mean/min/max par mois).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

import pandas as pd

try:
    from meteostat import Hourly, Point

    HAS_METEOSTAT = True
except Exception:  # pragma: no cover
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


def as_coord(value: Any) -> float | None:
    """Latitude/longitude utilisable, sinon None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        coord = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(coord):
        return None
    return coord


class WeatherFromGeo:
    """
    Récupère les indicateurs météo mensuels pour un point géographique.

    Exemple
    -------
    >>> w = WeatherFromGeo(years=(2024, 2025))
    >>> df = w.for_point(48.85, 2.35)
    >>> # colonnes : hotel_lat, hotel_lon, annee, mois, meteo_*_mean/min/max
    """

    def __init__(self, years: Sequence[int] | None = None) -> None:
        if years:
            self.years = tuple(sorted({int(y) for y in years}))
        else:
            self.years = (datetime.utcnow().year,)

    def for_point(
        self,
        lat: float,
        lon: float,
        *,
        lat_col: str = "hotel_lat",
        lon_col: str = "hotel_lon",
    ) -> pd.DataFrame:
        """
        Grille année × mois (12 mois) pour le point ``(lat, lon)``.

        Les mois sans observation restent en NaN (pas de fill à 0).
        """
        lat_f, lon_f = as_coord(lat), as_coord(lon)
        if lat_f is None or lon_f is None:
            return self._empty_grid(lat_f, lon_f, lat_col=lat_col, lon_col=lon_col)
        try:
            by_ym = self._fetch_by_year_month(lat_f, lon_f)
        except Exception:
            by_ym = {}
        rows: list[dict[str, Any]] = []
        for year in self.years:
            for month in range(1, 13):
                row: dict[str, Any] = {
                    lat_col: lat_f,
                    lon_col: lon_f,
                    "annee": int(year),
                    "mois": month,
                }
                obs = by_ym.get((int(year), month))
                if obs:
                    row.update(obs)
                rows.append(row)
        return pd.DataFrame(rows)

    def for_hotels(
        self,
        hotels: pd.DataFrame,
        *,
        lat_col: str = "hotel_lat",
        lon_col: str = "hotel_lon",
        id_cols: Sequence[str] = ("hotel_code", "hotel_name"),
    ) -> pd.DataFrame:
        """Météo pour plusieurs hôtels (propager id_cols)."""
        if hotels is None or hotels.empty:
            return pd.DataFrame()
        parts: list[pd.DataFrame] = []
        for _, h in hotels.iterrows():
            part = self.for_point(
                h.get(lat_col), h.get(lon_col), lat_col=lat_col, lon_col=lon_col
            )
            for col in id_cols:
                if col in hotels.columns:
                    part[col] = h.get(col)
            parts.append(part)
        if not parts:
            return pd.DataFrame()
        return pd.concat(parts, ignore_index=True)

    def _fetch_by_year_month(
        self, lat: float, lon: float
    ) -> dict[tuple[int, int], dict[str, float]]:
        if not HAS_METEOSTAT:
            return {}
        start_y, end_y = min(self.years), max(self.years)
        now = datetime.utcnow()
        start = datetime(start_y, 1, 1)
        end = min(now, datetime(end_y, 12, 31, 23, 59, 59))
        if end <= start:
            return {}
        frame = Hourly(Point(float(lat), float(lon)), start, end).fetch()
        if frame is None or getattr(frame, "empty", True):
            return {}
        return self._aggregate_hourly(frame)

    @staticmethod
    def _aggregate_hourly(frame: pd.DataFrame) -> dict[tuple[int, int], dict[str, float]]:
        work = frame.reset_index()
        if "time" not in work.columns:
            return {}
        times = pd.to_datetime(work["time"], errors="coerce")
        work = work.loc[times.notna()].copy()
        if work.empty:
            return {}
        times = times.loc[times.notna()]
        work["_year"] = times.dt.year.astype(int).to_numpy()
        work["_month"] = times.dt.month.astype(int).to_numpy()
        by_ym: dict[tuple[int, int], dict[str, float]] = {}
        for (year, month), group in work.groupby(["_year", "_month"], sort=True):
            metrics: dict[str, float] = {}
            for col in METEO_RAW_COLS:
                if col not in group.columns:
                    continue
                series = pd.to_numeric(group[col], errors="coerce").dropna()
                if series.empty:
                    continue
                readable = READABLE_WEATHER.get(col, col)
                metrics[f"meteo_{readable}_mean"] = float(series.mean())
                metrics[f"meteo_{readable}_min"] = float(series.min())
                metrics[f"meteo_{readable}_max"] = float(series.max())
            if metrics:
                by_ym[(int(year), int(month))] = metrics
        return by_ym

    def _empty_grid(
        self,
        lat: float | None,
        lon: float | None,
        *,
        lat_col: str,
        lon_col: str,
    ) -> pd.DataFrame:
        rows = [
            {lat_col: lat, lon_col: lon, "annee": int(y), "mois": m}
            for y in self.years
            for m in range(1, 13)
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def meteo_columns() -> list[str]:
        """Noms de colonnes météo produites."""
        cols: list[str] = []
        for raw, readable in READABLE_WEATHER.items():
            for stat in ("mean", "min", "max"):
                cols.append(f"meteo_{readable}_{stat}")
        return cols
