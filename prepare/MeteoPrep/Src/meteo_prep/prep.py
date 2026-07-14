"""MeteoPrep — météo mensuelle par hôtel à partir de hotel_lat / hotel_lon."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.enrich_hotel import EnrichHotelService, geocode_hotel

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

# Champs d'identification hôtel (RodPrep) utilisés par MeteoPrep.
HOTEL_IDENTITY_COLS = [
    "hotel_code",
    "hotel_name",
    "hotel_brand",
    "hotel_city",
    "hotel_lat",
    "hotel_lon",
]


def default_target_years(now: datetime | None = None) -> tuple[int, ...]:
    """Année en cours si non fournie (helper public)."""
    year = (now or datetime.utcnow()).year
    return (year,)


class MeteoPrep:
    """Récupère la météo aux coordonnées hôtel, renomme et impute les mois manquants.

    La météo est demandée pour le point ``(hotel_lat, hotel_lon)`` (stations
    Meteostat les plus proches). Les autres champs d'identité servent uniquement
    à identifier l'hôtel dans les sorties.

    Années cibles :
      - si ``target_years`` est fourni → ces années ;
      - sinon → année en cours uniquement.

    Imputation (sans jamais forcer à 0) :
      mois manquant de l'année Y ← même mois de l'année Y-1 (puis Y-2, …).
    """

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        target_years: Sequence[int] | None = None,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.target_years = self._resolve_target_years(target_years)
        settings = get_settings()
        registry = HotelIdentityRegistry(settings.identity_registry_path)
        store = FeatureStoreRepository(settings.feature_store_dir)
        self._enrich = EnrichHotelService(store, registry, settings)

    @staticmethod
    def _resolve_target_years(years: Sequence[int] | None) -> tuple[int, ...]:
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

    # Compat notebooks / code existant qui lisent MeteoPrep.TARGET_YEARS
    @property
    def TARGET_YEARS(self) -> tuple[int, ...]:  # noqa: N802
        return self.target_years

    def load_input(self) -> pd.DataFrame:
        path = self.input_dir / "hotels.csv"
        if path.exists():
            return pd.read_csv(path)
        parquet = self.input_dir / "hotels.parquet"
        if parquet.exists():
            return pd.read_parquet(parquet)
        raise FileNotFoundError(f"Entrée MeteoPrep absente dans {self.input_dir}")

    def fill_input_from_rod(self, rod_output_dir: Path) -> Path:
        """Copie les champs d'identité hôtel depuis la sortie RodPrep."""
        source = Path(rod_output_dir) / "hotel_lookup.parquet"
        if not source.exists():
            raise FileNotFoundError("Sortie RodPrep introuvable")
        frame = pd.read_parquet(source)
        cols = [c for c in HOTEL_IDENTITY_COLS if c in frame.columns]
        out = frame[cols].copy()
        if "hotel_code" in out.columns:
            out = out.dropna(subset=["hotel_code"]).drop_duplicates(subset=["hotel_code"])
            out["hotel_code"] = out["hotel_code"].astype(str)
        # Adresse optionnelle uniquement pour le fallback sans lat/lon.
        if "hotel_adresse" not in out.columns and "hotel_city" in out.columns:
            out["hotel_adresse"] = out["hotel_city"]
        self.input_dir.mkdir(parents=True, exist_ok=True)
        path = self.input_dir / "hotels.parquet"
        out.to_parquet(path, index=False)
        out.to_csv(self.input_dir / "hotels.csv", index=False)
        return path

    def run(self) -> pd.DataFrame:
        hotels = self.load_input()
        rows: list[dict] = []
        for _, hotel in hotels.iterrows():
            try:
                rows.extend(self._rows_for_hotel(hotel))
            except Exception as exc:  # ne pas faire planter tout le run
                code = str(hotel.get("hotel_code") or "")
                name = str(hotel.get("hotel_name") or code)
                rows.extend(self._empty_year_rows(code, name, warnings=[str(exc)]))

        frame = pd.DataFrame(rows)
        if frame.empty:
            frame = pd.DataFrame(columns=["hotel_code", "hotel_name", "annee", "mois"])
        else:
            frame = self._impute_missing(frame)
            # Ne garder que les années cibles en sortie (l'année N-1 a pu servir d'imputation)
            frame = frame[frame["annee"].isin(self.target_years)].copy()
            frame = frame.sort_values(
                ["hotel_code", "annee", "mois"], kind="mergesort"
            ).reset_index(drop=True)

        frame.to_parquet(self.output_dir / "meteo_monthly.parquet", index=False)
        frame.to_csv(self.output_dir / "meteo_monthly.csv", index=False)
        return frame

    def weather_for_hotel(self, hotel: pd.Series | dict[str, Any]) -> dict[str, Any]:
        """Récupère la météo brute au point hôtel (lat/lon), sans POI ni plage.

        Priorité :
        1. ``hotel_lat`` / ``hotel_lon`` fournis par RodPrep
        2. géocodage de secours (nom / adresse / ville) si coordonnées absentes

        Retourne un dict indexé par ``(annee, mois)`` → métriques ``meteo_*``.
        """
        code = str(hotel.get("hotel_code") or "")
        name = str(hotel.get("hotel_name") or code)
        city = str(hotel.get("hotel_city") or "")
        address = str(hotel.get("hotel_adresse") or city or "")
        lat = self._as_coord(hotel.get("hotel_lat"))
        lon = self._as_coord(hotel.get("hotel_lon"))
        warnings: list[str] = []
        source = "hotel_coords"

        if lat is None or lon is None:
            try:
                geo = geocode_hotel(name, address, city, settings=get_settings())
            except Exception as exc:
                geo = None
                warnings.append(f"Géocodage en erreur: {exc}")
            if not geo:
                warnings.append("Coordonnées absentes et géocodage échoué.")
                return {
                    "hotel_code": code,
                    "hotel_name": name,
                    "hotel_lat": None,
                    "hotel_lon": None,
                    "source": "failed",
                    "warnings": warnings,
                    "weather_by_year_month": {},
                    "nb_cles_meteo": 0,
                }
            try:
                lat = float(geo["lat"])
                lon = float(geo["lon"])
            except (TypeError, ValueError, KeyError):
                warnings.append("Géocodage sans lat/lon exploitables.")
                return {
                    "hotel_code": code,
                    "hotel_name": name,
                    "hotel_lat": None,
                    "hotel_lon": None,
                    "source": "failed",
                    "warnings": warnings,
                    "weather_by_year_month": {},
                    "nb_cles_meteo": 0,
                }
            source = "geocoded"
            warnings.append("lat/lon absents : géocodage de secours utilisé.")

        start_year, end_year = self._fetch_year_window()
        try:
            by_ym = self._fetch_weather_by_year_month(lat, lon, start_year, end_year)
        except Exception as exc:
            by_ym = {}
            warnings.append(f"Récupération météo en erreur: {exc}")

        n_keys = sum(len(v) for v in by_ym.values())
        return {
            "hotel_code": code,
            "hotel_name": name,
            "hotel_lat": lat,
            "hotel_lon": lon,
            "source": source,
            "warnings": warnings,
            "weather_by_year_month": by_ym,
            "nb_cles_meteo": n_keys,
        }

    def _fetch_year_window(self) -> tuple[int, int]:
        """Fenêtre de téléchargement : années cibles + année précédente (imputation)."""
        now_year = datetime.utcnow().year
        if self.target_years:
            start = min(self.target_years) - 1
            end = max(max(self.target_years), now_year)
        else:
            start = now_year - 1
            end = now_year
        return start, end

    def _fetch_weather_by_year_month(
        self,
        lat: float,
        lon: float,
        start_year: int,
        end_year: int,
    ) -> dict[tuple[int, int], dict[str, float]]:
        """Agrège Meteostat horaire en ``(année, mois) → métriques lisibles``.

        Si l'API ne fournit pas d'année exploitable, les observations sont
        rattachées à l'année en cours.
        """
        if not HAS_METEOSTAT:
            return {}

        now = datetime.utcnow()
        start = datetime(int(start_year), 1, 1)
        end = min(now, datetime(int(end_year), 12, 31, 23, 59, 59))
        if end <= start:
            end = now

        frame = Hourly(Point(float(lat), float(lon)), start, end).fetch()
        if frame is None or getattr(frame, "empty", True):
            return {}

        frame = frame.reset_index()
        if "time" not in frame.columns:
            return {}

        times = pd.to_datetime(frame["time"], errors="coerce")
        frame = frame.loc[times.notna()].copy()
        if frame.empty:
            return {}
        times = times.loc[times.notna()]
        # Année absente / NaT → année en cours
        years = times.dt.year.fillna(now.year).astype(int)
        months = times.dt.month.fillna(1).astype(int)
        frame["_year"] = years.to_numpy()
        frame["_month"] = months.to_numpy()

        by_ym: dict[tuple[int, int], dict[str, float]] = {}
        for (year, month), group in frame.groupby(["_year", "_month"], sort=True):
            year_i = int(year)
            month_i = int(month)
            if month_i < 1 or month_i > 12:
                continue
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
            if metrics:
                by_ym[(year_i, month_i)] = metrics
        return by_ym

    def _rows_for_hotel(self, hotel: pd.Series) -> list[dict]:
        info = self.weather_for_hotel(hotel)
        by_ym: dict[tuple[int, int], dict[str, float]] = (
            info.get("weather_by_year_month") or {}
        )
        code = info["hotel_code"]
        name = info["hotel_name"]

        # Années présentes dans les données + cibles + année préc. pour imputer
        years = set(self.target_years)
        years.update(y for (y, _m) in by_ym.keys())
        if self.target_years:
            years.add(min(self.target_years) - 1)
        years = {int(y) for y in years if y is not None}

        rows: list[dict] = []
        for year in sorted(years):
            for month in range(1, 13):
                row: dict[str, Any] = {
                    "hotel_code": code,
                    "hotel_name": name,
                    "annee": year,
                    "mois": month,
                }
                row.update(by_ym.get((year, month), {}))
                rows.append(row)
        return rows

    def _empty_year_rows(
        self,
        code: str,
        name: str,
        warnings: Iterable[str] | None = None,
    ) -> list[dict]:
        _ = warnings  # réservé logs / debug
        rows: list[dict] = []
        for year in self.target_years:
            for month in range(1, 13):
                rows.append(
                    {
                        "hotel_code": code,
                        "hotel_name": name,
                        "annee": int(year),
                        "mois": month,
                    }
                )
        return rows

    def _readable_monthly(self, weather: dict) -> dict[int, dict[str, float]]:
        """Compat : transforme clés ``[d_]m{MM}_{metric}_{stat}`` (sans année).

        Utilisé par le notebook d'exploration sur un profil mensuel aplati.
        Sans info d'année, les valeurs sont traitées comme année en cours.
        """
        by_month: dict[int, dict[str, float]] = {m: {} for m in range(1, 13)}
        if not weather:
            return by_month

        # Nouveau format : dict (year, month) → metrics
        sample_key = next(iter(weather), None)
        if isinstance(sample_key, tuple) and len(sample_key) == 2:
            current_year = datetime.utcnow().year
            # Préférer l'année en cours, sinon la plus récente disponible
            years = sorted({int(y) for y, _m in weather.keys()})
            preferred = current_year if current_year in years else (years[-1] if years else current_year)
            for (year, month), metrics in weather.items():
                if int(year) != preferred:
                    continue
                try:
                    month_i = int(month)
                except (TypeError, ValueError):
                    continue
                if 1 <= month_i <= 12 and isinstance(metrics, dict):
                    by_month[month_i] = {
                        k: float(v)
                        for k, v in metrics.items()
                        if k.startswith("meteo_")
                    }
            return by_month

        for key, value in weather.items():
            k = str(key)
            k = k[2:] if k.startswith("d_") else k
            if not k.startswith("m"):
                continue
            parts = k.split("_")
            if len(parts) < 3:
                continue
            try:
                month = int(parts[0].replace("m", ""))
            except ValueError:
                continue
            if month < 1 or month > 12:
                continue
            metric = parts[1]
            stat = parts[2]
            readable = READABLE_WEATHER.get(metric, metric)
            col = f"meteo_{readable}_{stat}"
            try:
                by_month.setdefault(month, {})[col] = float(value)
            except (TypeError, ValueError):
                continue
        return by_month

    @staticmethod
    def _month_vector(monthly: dict[int, dict[str, float]], month: int) -> dict[str, float]:
        return dict(monthly.get(month, {}))

    @staticmethod
    def _as_coord(value: Any) -> float | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        try:
            coord = float(value)
        except (TypeError, ValueError):
            return None
        if pd.isna(coord):
            return None
        return coord

    def _impute_missing(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Impute les mois manquants par le même mois de l'année précédente.

        Règles :
        1. Pour chaque ``(hotel_code, annee, mois)`` et chaque colonne ``meteo_*``,
           si NaN → valeur du même mois de l'année N-1 (puis N-2, …).
        2. Jamais de ``fillna(0)``.
        3. Si aucune année antérieure n'a la valeur, le NaN est conservé.
        """
        if frame.empty:
            return frame

        numeric_cols = [c for c in frame.columns if c.startswith("meteo_")]
        if not numeric_cols:
            return frame

        out = frame.copy()
        # S'assurer des types numériques pour les colonnes météo
        for col in numeric_cols:
            out[col] = pd.to_numeric(out[col], errors="coerce")

        if "hotel_code" not in out.columns or "annee" not in out.columns or "mois" not in out.columns:
            return out

        out["annee"] = pd.to_numeric(out["annee"], errors="coerce")
        out["mois"] = pd.to_numeric(out["mois"], errors="coerce")
        out = out.dropna(subset=["annee", "mois"]).copy()
        out["annee"] = out["annee"].astype(int)
        out["mois"] = out["mois"].astype(int)

        parts: list[pd.DataFrame] = []
        for hotel_code, hotel_df in out.groupby("hotel_code", sort=False):
            parts.append(self._impute_hotel(hotel_df, numeric_cols))
        if not parts:
            return out
        return pd.concat(parts, ignore_index=True)

    @staticmethod
    def _impute_hotel(hotel_df: pd.DataFrame, numeric_cols: list[str]) -> pd.DataFrame:
        """Impute un hôtel : mois manquants ← même mois année précédente."""
        df = hotel_df.sort_values(["annee", "mois"], kind="mergesort").copy()
        years = sorted(df["annee"].dropna().unique().tolist())
        if not years:
            return df

        # Index (annee, mois) → positions pour lookup rapide
        for col in numeric_cols:
            if col not in df.columns:
                continue
            # Carte (year, month) → valeur connue
            known: dict[tuple[int, int], float] = {}
            for _, row in df.iterrows():
                val = row[col]
                if pd.notna(val):
                    known[(int(row["annee"]), int(row["mois"]))] = float(val)

            filled_values: list[float | None] = []
            for _, row in df.iterrows():
                year = int(row["annee"])
                month = int(row["mois"])
                val = row[col]
                if pd.notna(val):
                    filled_values.append(float(val))
                    known[(year, month)] = float(val)
                    continue

                # Remonter les années précédentes pour le même mois
                imputed: float | None = None
                prev = year - 1
                min_year = min(years) - 5  # borne de sécurité
                while prev >= min_year:
                    candidate = known.get((prev, month))
                    if candidate is not None and pd.notna(candidate):
                        imputed = float(candidate)
                        break
                    prev -= 1

                filled_values.append(imputed)
                if imputed is not None:
                    known[(year, month)] = imputed

            df[col] = filled_values

        return df
