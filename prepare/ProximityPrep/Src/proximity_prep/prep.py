"""ProximityPrep — commerces de proximité et distance plage."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.enrich_hotel import EnrichHotelService


class ProximityPrep:
    """Extrait POI et plage avec libellés lisibles."""

    def __init__(self, input_dir: Path, output_dir: Path) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        settings = get_settings()
        registry = HotelIdentityRegistry(settings.identity_registry_path)
        store = FeatureStoreRepository(settings.feature_store_dir)
        self._enrich = EnrichHotelService(store, registry, settings)

    def fill_input_from_rod(self, rod_output_dir: Path) -> Path:
        source = Path(rod_output_dir) / "hotel_lookup.parquet"
        frame = pd.read_parquet(source)
        self.input_dir.mkdir(parents=True, exist_ok=True)
        path = self.input_dir / "hotels.parquet"
        frame.to_parquet(path, index=False)
        return path

    def load_input(self) -> pd.DataFrame:
        path = self.input_dir / "hotels.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Entrée ProximityPrep absente : {path}")
        return pd.read_parquet(path)

    def run(self) -> pd.DataFrame:
        hotels = self.load_input()
        rows: list[dict] = []
        for _, hotel in hotels.iterrows():
            code = str(hotel.get("hotel_code", ""))
            name = str(hotel.get("hotel_name", code))
            city = str(hotel.get("hotel_city", ""))
            result = self._enrich.enrich(hotel_name=name, city=city, hotel_id=code)
            poi = result.features.poi or {}
            nearest = result.features.nearest or {}
            row = {
                "hotel_code": code,
                "hotel_name": name,
                "plage_distance_km": nearest.get("d_nearest_beach_km")
                or nearest.get("nearest_beach_km"),
                "commerce_fb_100m": poi.get("d_poi_fb_0_0_1km", 0),
                "commerce_fb_500m": poi.get("d_poi_fb_0_0_5km", 0),
                "commerce_non_fb_100m": poi.get("d_poi_not_fb_0_0_1km", 0),
                "commerce_non_fb_500m": poi.get("d_poi_not_fb_0_0_5km", 0),
            }
            for key, value in nearest.items():
                if key.startswith("d_nearest_") and key.endswith("_m"):
                    clean = key.replace("d_nearest_", "distance_").replace("_m", "_m")
                    row[clean] = value
            rows.append(row)
        frame = pd.DataFrame(rows)
        frame.to_parquet(self.output_dir / "proximity.parquet", index=False)
        frame.to_csv(self.output_dir / "proximity.csv", index=False)
        return frame