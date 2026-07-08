"""MeteoPrep — météo mensuelle par hôtel avec libellés lisibles."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.enrich_hotel import EnrichHotelService
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository

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


class MeteoPrep:
    """Récupère et renomme la météo ; impute les mois manquants."""

    TARGET_YEARS = (2024, 2025)

    def __init__(self, input_dir: Path, output_dir: Path) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        settings = get_settings()
        registry = HotelIdentityRegistry(settings.identity_registry_path)
        store = FeatureStoreRepository(settings.feature_store_dir)
        self._enrich = EnrichHotelService(store, registry, settings)

    def load_input(self) -> pd.DataFrame:
        path = self.input_dir / "hotels.csv"
        if path.exists():
            return pd.read_csv(path)
        parquet = self.input_dir / "hotels.parquet"
        if parquet.exists():
            return pd.read_parquet(parquet)
        raise FileNotFoundError(f"Entrée MeteoPrep absente dans {self.input_dir}")

    def fill_input_from_rod(self, rod_output_dir: Path) -> Path:
        source = Path(rod_output_dir) / "hotel_lookup.parquet"
        if not source.exists():
            raise FileNotFoundError("Sortie RodPrep introuvable")
        frame = pd.read_parquet(source)
        out = frame[
            [
                c
                for c in [
                    "hotel_code",
                    "hotel_name",
                    "hotel_brand",
                    "hotel_city",
                    "hotel_lat",
                    "hotel_lon",
                ]
                if c in frame.columns
            ]
        ].copy()
        if "hotel_city" in out.columns:
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
            code = str(hotel.get("hotel_code", ""))
            name = str(hotel.get("hotel_name", code))
            city = str(hotel.get("hotel_city", ""))
            result = self._enrich.enrich(
                hotel_name=name,
                city=city,
                hotel_id=code,
                force_refresh=False,
            )
            monthly = self._readable_monthly(result.features.weather_monthly)
            for year in self.TARGET_YEARS:
                for month in range(1, 13):
                    row = {
                        "hotel_code": code,
                        "hotel_name": name,
                        "annee": year,
                        "mois": month,
                    }
                    row.update(self._month_vector(monthly, month))
                    rows.append(row)

        frame = pd.DataFrame(rows)
        frame = self._impute_missing(frame)
        frame.to_parquet(self.output_dir / "meteo_monthly.parquet", index=False)
        frame.to_csv(self.output_dir / "meteo_monthly.csv", index=False)
        return frame

    def _readable_monthly(self, weather: dict) -> dict[int, dict[str, float]]:
        by_month: dict[int, dict[str, float]] = {m: {} for m in range(1, 13)}
        for key, value in (weather or {}).items():
            if not key.startswith("d_m"):
                continue
            parts = key.split("_")
            if len(parts) < 4:
                continue
            try:
                month = int(parts[1].replace("m", ""))
            except ValueError:
                continue
            metric = parts[2]
            stat = parts[3]
            readable = READABLE_WEATHER.get(metric, metric)
            col = f"meteo_{readable}_{stat}"
            by_month.setdefault(month, {})[col] = float(value)
        return by_month

    @staticmethod
    def _month_vector(monthly: dict[int, dict[str, float]], month: int) -> dict[str, float]:
        return dict(monthly.get(month, {}))

    def _impute_missing(self, frame: pd.DataFrame) -> pd.DataFrame:
        numeric_cols = [c for c in frame.columns if c.startswith("meteo_")]
        if not numeric_cols:
            return frame

        def fill_group(group: pd.DataFrame) -> pd.DataFrame:
            group = group.sort_values("mois").copy()
            for col in numeric_cols:
                series = group[col]
                if series.notna().any():
                    group[col] = series.ffill().bfill()
                if group[col].isna().any() and series.notna().any():
                    group[col] = group[col].fillna(series.mean())
                if group[col].isna().any():
                    group[col] = group[col].fillna(0.0)
            return group

        return frame.groupby(["hotel_code", "annee"], group_keys=False).apply(fill_group)