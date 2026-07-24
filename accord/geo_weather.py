"""
WeatherFromGeo — météo mensuelle à partir de (lat, lon).

Utilisé optionnellement lors du rebuild All Data
(``join_data.build_joined_dataframe(fill_weather=True)``) pour combler
les trous de ``hotel_weather_data``.

Compatible **Meteostat 2.x** (``stations.nearby`` + monthly/daily/hourly).

Stratégie
---------
1. Station météo la plus proche (``stations.nearby(Point)``).
2. Série **monthly** (historique long, rapide).
3. Fallback daily / hourly si couverture insuffisante.
4. **Imputation** mois manquant ← même mois N-1, N-2, … (jamais fill 0
   ici — le fill 0 global se fait ailleurs pour les mesures sales).

Si Meteostat n'est pas installé, ``HAS_METEOSTAT`` est False et les appels
retournent des frames vides sans lever d'exception bloquante.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

import pandas as pd

HAS_METEOSTAT = False
_Point = None
_stations = None
_monthly = None
_daily = None
_hourly = None

try:
    from meteostat import Point as _Point
    from meteostat import daily as _daily
    from meteostat import hourly as _hourly
    from meteostat import monthly as _monthly
    from meteostat import stations as _stations

    HAS_METEOSTAT = True
except Exception:  # pragma: no cover
    # Ancien API 1.x (Daily/Hourly/Monthly classes)
    try:
        from meteostat import Daily as _Daily  # type: ignore
        from meteostat import Hourly as _Hourly  # type: ignore
        from meteostat import Monthly as _Monthly  # type: ignore
        from meteostat import Point as _Point  # type: ignore

        HAS_METEOSTAT = True
        _USE_V1 = True
    except Exception:
        _USE_V1 = False
else:
    _USE_V1 = False

TARGET_METRICS = (
    "temperature_c",
    "point_rosee_c",
    "humidite_pct",
    "precipitations_mm",
    "neige_mm",
    "vent_kmh",
    "pression_hpa",
    "ensoleillement_min",
)


def as_coord(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        coord = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(coord):
        return None
    return coord


def meteo_column_names() -> list[str]:
    cols: list[str] = []
    for m in TARGET_METRICS:
        for stat in ("mean", "min", "max"):
            cols.append(f"meteo_{m}_{stat}")
    return cols


class WeatherFromGeo:
    """
    Récupère les indicateurs météo mensuels pour un point géographique.

    >>> w = WeatherFromGeo(years=(2023, 2024, 2025))
    >>> df = w.for_point(43.69, 7.24, impute=True)
    """

    def __init__(self, years: Sequence[int] | None = None) -> None:
        if years:
            self.years = tuple(sorted({int(y) for y in years}))
        else:
            self.years = (datetime.utcnow().year,)
        self._fetch_cache: dict[
            tuple[float, float], dict[tuple[int, int], dict[str, float]]
        ] = {}
        self._station_cache: dict[tuple[float, float], str | None] = {}

    def for_point(
        self,
        lat: float,
        lon: float,
        *,
        lat_col: str = "hotel_lat",
        lon_col: str = "hotel_lon",
        impute: bool = True,
    ) -> pd.DataFrame:
        """Grille année × mois pour ``(lat, lon)``."""
        lat_f, lon_f = as_coord(lat), as_coord(lon)
        if lat_f is None or lon_f is None:
            return self._empty_grid(lat_f, lon_f, lat_col=lat_col, lon_col=lon_col)

        by_ym = self._fetch_by_year_month(lat_f, lon_f)
        if impute:
            by_ym = self._impute_by_ym(by_ym, self.years)

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
        impute: bool = True,
    ) -> pd.DataFrame:
        if hotels is None or hotels.empty:
            return pd.DataFrame()
        parts: list[pd.DataFrame] = []
        for _, h in hotels.iterrows():
            part = self.for_point(
                h.get(lat_col),
                h.get(lon_col),
                lat_col=lat_col,
                lon_col=lon_col,
                impute=impute,
            )
            for col in id_cols:
                if col in hotels.columns:
                    part[col] = h.get(col)
            parts.append(part)
        if not parts:
            return pd.DataFrame()
        return pd.concat(parts, ignore_index=True)

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _nearest_station_id(self, lat: float, lon: float) -> str | None:
        key = (round(lat, 3), round(lon, 3))
        if key in self._station_cache:
            return self._station_cache[key]
        if not HAS_METEOSTAT or _stations is None:
            self._station_cache[key] = None
            return None
        try:
            nearby = _stations.nearby(_Point(lat, lon))
            if nearby is None or getattr(nearby, "empty", True):
                self._station_cache[key] = None
                return None
            sid = str(nearby.index[0])
            self._station_cache[key] = sid
            return sid
        except Exception:
            self._station_cache[key] = None
            return None

    def _fetch_by_year_month(
        self, lat: float, lon: float
    ) -> dict[tuple[int, int], dict[str, float]]:
        key = (round(lat, 4), round(lon, 4))
        if key in self._fetch_cache:
            return dict(self._fetch_cache[key])

        if not HAS_METEOSTAT:
            self._fetch_cache[key] = {}
            return {}

        start_y = min(self.years) - 2  # marge imputation
        end_y = max(self.years)
        now = datetime.utcnow()
        start = datetime(start_y, 1, 1)
        end = min(now, datetime(end_y, 12, 31, 23, 59, 59))
        if end <= start:
            self._fetch_cache[key] = {}
            return {}

        by_ym: dict[tuple[int, int], dict[str, float]] = {}

        if _USE_V1:
            by_ym = self._fetch_v1(lat, lon, start, end)
        else:
            station_id = self._nearest_station_id(lat, lon)
            if station_id:
                by_ym = self._fetch_v2_station(station_id, start, end)
            # Point direct (providers géo) en complément
            if self._coverage_ratio(by_ym) < 0.9:
                extra = self._fetch_v2_point(lat, lon, start, end)
                by_ym = self._merge_ym(by_ym, extra)

        self._fetch_cache[key] = by_ym
        return dict(by_ym)

    def _fetch_v2_station(
        self, station_id: str, start: datetime, end: datetime
    ) -> dict[tuple[int, int], dict[str, float]]:
        by_ym: dict[tuple[int, int], dict[str, float]] = {}
        # Monthly
        try:
            ts = _monthly(station_id, start=start, end=end)
            frame = ts.fetch() if ts is not None and hasattr(ts, "fetch") else None
            if frame is not None and not getattr(frame, "empty", True):
                by_ym = self._frame_to_ym(frame)
        except Exception:
            pass
        # Daily fallback
        if self._coverage_ratio(by_ym) < 0.85:
            try:
                ts = _daily(station_id, start=start, end=end)
                frame = ts.fetch() if ts is not None and hasattr(ts, "fetch") else None
                if frame is not None and not getattr(frame, "empty", True):
                    by_ym = self._merge_ym(by_ym, self._frame_to_ym(frame, aggregate=True))
            except Exception:
                pass
        return by_ym

    def _fetch_v2_point(
        self, lat: float, lon: float, start: datetime, end: datetime
    ) -> dict[tuple[int, int], dict[str, float]]:
        by_ym: dict[tuple[int, int], dict[str, float]] = {}
        try:
            pt = _Point(lat, lon)
            ts = _monthly(pt, start=start, end=end)
            frame = ts.fetch() if ts is not None and hasattr(ts, "fetch") else None
            if frame is not None and not getattr(frame, "empty", True):
                by_ym = self._frame_to_ym(frame)
        except Exception:
            pass
        return by_ym

    def _fetch_v1(
        self, lat: float, lon: float, start: datetime, end: datetime
    ) -> dict[tuple[int, int], dict[str, float]]:
        """API meteostat 1.x (classes Monthly/Daily/Hourly)."""
        by_ym: dict[tuple[int, int], dict[str, float]] = {}
        try:
            frame = _Monthly(_Point(lat, lon), start, end).fetch()  # type: ignore[misc]
            if frame is not None and not getattr(frame, "empty", True):
                by_ym = self._frame_to_ym(frame)
        except Exception:
            pass
        if self._coverage_ratio(by_ym) < 0.85:
            try:
                frame = _Daily(_Point(lat, lon), start, end).fetch()  # type: ignore[misc]
                if frame is not None and not getattr(frame, "empty", True):
                    by_ym = self._merge_ym(
                        by_ym, self._frame_to_ym(frame, aggregate=True)
                    )
            except Exception:
                pass
        return by_ym

    # ------------------------------------------------------------------
    # Conversion DataFrame → (année, mois) → métriques
    # ------------------------------------------------------------------

    def _frame_to_ym(
        self, frame: pd.DataFrame, *, aggregate: bool = False
    ) -> dict[tuple[int, int], dict[str, float]]:
        work = frame.reset_index()
        # Colonne temps
        time_col = None
        for c in ("time", "date", "month", "index"):
            if c in work.columns:
                time_col = c
                break
        if time_col is None:
            # multiindex station/time déjà flatten
            for c in work.columns:
                if "time" in str(c).lower():
                    time_col = c
                    break
        if time_col is None:
            return {}

        times = pd.to_datetime(work[time_col], errors="coerce")
        work = work.loc[times.notna()].copy()
        if work.empty:
            return {}
        times = times.loc[times.notna()]
        work["_year"] = times.dt.year.astype(int).to_numpy()
        work["_month"] = times.dt.month.astype(int).to_numpy()

        by_ym: dict[tuple[int, int], dict[str, float]] = {}
        if not aggregate and work.groupby(["_year", "_month"]).size().max() == 1:
            # Une ligne par mois (Monthly)
            for _, r in work.iterrows():
                metrics = self._series_to_metrics(r)
                if metrics:
                    by_ym[(int(r["_year"]), int(r["_month"]))] = metrics
        else:
            for (year, month), group in work.groupby(["_year", "_month"], sort=True):
                metrics = self._group_to_metrics(group)
                if metrics:
                    by_ym[(int(year), int(month))] = metrics
        return by_ym

    def _series_to_metrics(self, row: pd.Series) -> dict[str, float]:
        metrics: dict[str, float] = {}
        # Température
        tavg = self._num(row, "temp") or self._num(row, "tavg")
        tmin = self._num(row, "tmin")
        tmax = self._num(row, "tmax")
        if tavg is not None:
            metrics["meteo_temperature_c_mean"] = tavg
            metrics["meteo_temperature_c_min"] = tmin if tmin is not None else tavg
            metrics["meteo_temperature_c_max"] = tmax if tmax is not None else tavg
        elif tmin is not None or tmax is not None:
            vals = [v for v in (tmin, tmax) if v is not None]
            metrics["meteo_temperature_c_mean"] = sum(vals) / len(vals)
            metrics["meteo_temperature_c_min"] = min(vals)
            metrics["meteo_temperature_c_max"] = max(vals)

        for raw, readable in (
            ("prcp", "precipitations_mm"),
            ("snow", "neige_mm"),
            ("wspd", "vent_kmh"),
            ("pres", "pression_hpa"),
            ("tsun", "ensoleillement_min"),
            ("rhum", "humidite_pct"),
            ("dwpt", "point_rosee_c"),
        ):
            val = self._num(row, raw)
            if val is None:
                continue
            metrics[f"meteo_{readable}_mean"] = val
            metrics[f"meteo_{readable}_min"] = val
            metrics[f"meteo_{readable}_max"] = val
        return metrics

    def _group_to_metrics(self, group: pd.DataFrame) -> dict[str, float]:
        metrics: dict[str, float] = {}
        for raw, readable in (
            ("temp", "temperature_c"),
            ("tavg", "temperature_c"),
            ("dwpt", "point_rosee_c"),
            ("rhum", "humidite_pct"),
            ("prcp", "precipitations_mm"),
            ("snow", "neige_mm"),
            ("wspd", "vent_kmh"),
            ("pres", "pression_hpa"),
            ("tsun", "ensoleillement_min"),
        ):
            if raw not in group.columns:
                continue
            series = pd.to_numeric(group[raw], errors="coerce").dropna()
            if series.empty:
                continue
            key = f"meteo_{readable}_mean"
            if key in metrics and raw == "tavg":
                continue
            metrics[f"meteo_{readable}_mean"] = float(series.mean())
            metrics[f"meteo_{readable}_min"] = float(series.min())
            metrics[f"meteo_{readable}_max"] = float(series.max())
        if "tmin" in group.columns:
            tmin_s = pd.to_numeric(group["tmin"], errors="coerce").dropna()
            if not tmin_s.empty:
                metrics["meteo_temperature_c_min"] = float(tmin_s.min())
        if "tmax" in group.columns:
            tmax_s = pd.to_numeric(group["tmax"], errors="coerce").dropna()
            if not tmax_s.empty:
                metrics["meteo_temperature_c_max"] = float(tmax_s.max())
        return metrics

    @staticmethod
    def _num(row: pd.Series, col: str) -> float | None:
        if col not in row.index:
            return None
        try:
            val = float(row[col])
        except (TypeError, ValueError):
            return None
        if pd.isna(val):
            return None
        return val

    # ------------------------------------------------------------------
    # Imputation
    # ------------------------------------------------------------------

    def _impute_by_ym(
        self,
        by_ym: dict[tuple[int, int], dict[str, float]],
        target_years: Sequence[int],
    ) -> dict[tuple[int, int], dict[str, float]]:
        out = {k: dict(v) for k, v in by_ym.items()}
        target_cols = meteo_column_names()
        years_sorted = sorted({int(y) for y in target_years})
        all_years = sorted(set(years_sorted) | {y for y, _ in out.keys()})
        min_y = min(all_years) if all_years else min(years_sorted)

        for year in years_sorted:
            for month in range(1, 13):
                key = (year, month)
                current = dict(out.get(key, {}))
                for col in target_cols:
                    if col in current and current[col] is not None and not pd.isna(
                        current[col]
                    ):
                        continue
                    for prev in range(year - 1, min_y - 3, -1):
                        prev_m = out.get((prev, month)) or by_ym.get((prev, month))
                        if not prev_m:
                            continue
                        val = prev_m.get(col)
                        if val is not None and not pd.isna(val):
                            current[col] = float(val)
                            break
                if current:
                    out[key] = current
        return out

    @staticmethod
    def _merge_ym(
        base: dict[tuple[int, int], dict[str, float]],
        extra: dict[tuple[int, int], dict[str, float]],
    ) -> dict[tuple[int, int], dict[str, float]]:
        out = {k: dict(v) for k, v in base.items()}
        for key, metrics in extra.items():
            if key not in out:
                out[key] = dict(metrics)
            else:
                for col, val in metrics.items():
                    if col not in out[key] or out[key][col] is None or pd.isna(
                        out[key][col]
                    ):
                        out[key][col] = val
        return out

    def _coverage_ratio(self, by_ym: dict[tuple[int, int], dict[str, float]]) -> float:
        if not self.years:
            return 0.0
        total = len(self.years) * 12
        ok = 0
        for y in self.years:
            for m in range(1, 13):
                metrics = by_ym.get((int(y), m)) or {}
                if metrics.get("meteo_temperature_c_mean") is not None:
                    ok += 1
        return ok / total if total else 0.0

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
        return meteo_column_names()
