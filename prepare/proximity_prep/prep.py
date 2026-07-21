"""ProximityPrep — commerces de proximité et distance plage.

Orchestration pipeline : charge les hôtels (``hotel_code`` Accor + coordonnées
déjà résolues par RodPrep), délègue POI/plage à ``EnrichHotelService``,
sérialise une table à grain ``hotel_code``.

Même contrat d'entrée que MeteoPrep :
  - ``hotel_code`` = code Accor (``code_h`` de RodPrep), **jamais** un nom
  - ``hotel_lat`` / ``hotel_lon`` fournis par RodPrep
  - géocodage par nom uniquement en fallback si coords absentes
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from rod_ia.config.settings import Settings, get_settings
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.enrich_hotel import EnrichHotelService

# Champs d'identité hôtel (RodPrep) utilisés par ProximityPrep — miroir MeteoPrep.
HOTEL_IDENTITY_COLS = [
    "hotel_code",
    "hotel_name",
    "hotel_brand",
    "hotel_city",
    "hotel_lat",
    "hotel_lon",
]


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


class ProximityPrep:
    """Pipeline : hôtels géolocalisés (RodPrep) → table proximité.

    La proximité est calculée au point ``(hotel_lat, hotel_lon)``. Aucun
    géocodage d'adresse si les coordonnées sont présentes (responsabilité
    RodPrep). Si lat/lon manquent, fallback Nominatim via le nom + ville.
    """

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        *,
        settings: Settings | None = None,
        enrich: EnrichHotelService | None = None,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._settings = settings or get_settings()
        if enrich is not None:
            self._enrich = enrich
        else:
            registry = HotelIdentityRegistry(self._settings.identity_registry_path)
            store = FeatureStoreRepository(self._settings.feature_store_dir)
            self._enrich = EnrichHotelService(store, registry, self._settings)

    def fill_input_from_rod(self, rod_output_dir: Path) -> Path:
        """Copie les champs d'identité depuis la sortie RodPrep.

        - ``hotel_code`` = code Accor (pas un slug, pas un nom)
        - ``hotel_lat`` / ``hotel_lon`` déjà résolus par RodPrep
        - lignes sans ``hotel_code`` exclues (impossible à joindre ensuite)
        """
        source = Path(rod_output_dir) / "hotel_lookup.parquet"
        if not source.exists():
            raise FileNotFoundError(f"Sortie RodPrep introuvable : {source}")
        frame = pd.read_parquet(source)
        cols = [c for c in HOTEL_IDENTITY_COLS if c in frame.columns]
        out = frame[cols].copy()
        if "hotel_code" not in out.columns:
            raise ValueError(
                "hotel_lookup sans hotel_code — relancer RodPrep (code Accor code_h)."
            )
        out = out.dropna(subset=["hotel_code"]).drop_duplicates(subset=["hotel_code"])
        out["hotel_code"] = out["hotel_code"].astype(str).str.strip()
        out = out[out["hotel_code"].ne("") & out["hotel_code"].str.lower().ne("none")]
        out = out[out["hotel_code"].str.lower().ne("nan")]
        self.input_dir.mkdir(parents=True, exist_ok=True)
        path = self.input_dir / "hotels.parquet"
        out.to_parquet(path, index=False)
        out.to_csv(self.input_dir / "hotels.csv", index=False)
        return path

    def load_input(self) -> pd.DataFrame:
        path = self.input_dir / "hotels.parquet"
        if path.exists():
            return pd.read_parquet(path)
        csv_path = self.input_dir / "hotels.csv"
        if csv_path.exists():
            return pd.read_csv(csv_path)
        raise FileNotFoundError(f"Entrée ProximityPrep absente dans {self.input_dir}")

    def run(self, *, force_refresh: bool = False) -> pd.DataFrame:
        hotels = self.load_input()
        rows: list[dict[str, Any]] = []
        for _, hotel in hotels.iterrows():
            try:
                rows.append(self._row_for_hotel(hotel, force_refresh=force_refresh))
            except Exception as exc:
                rows.append(self._empty_row(hotel, warnings=[str(exc)]))
        frame = pd.DataFrame(rows)
        if frame.empty:
            frame = pd.DataFrame(
                columns=[
                    "hotel_code",
                    "hotel_name",
                    "hotel_lat",
                    "hotel_lon",
                    "geo_source",
                    "plage_distance_km",
                    "commerce_fb_100m",
                    "commerce_fb_500m",
                    "commerce_non_fb_100m",
                    "commerce_non_fb_500m",
                ]
            )
        frame.to_parquet(self.output_dir / "proximity.parquet", index=False)
        frame.to_csv(self.output_dir / "proximity.csv", index=False)
        return frame

    def _row_for_hotel(
        self, hotel: pd.Series | dict[str, Any], *, force_refresh: bool = False
    ) -> dict[str, Any]:
        code = self._normalize_code(hotel.get("hotel_code"))
        name = str(hotel.get("hotel_name") or code or "").strip()
        city = str(hotel.get("hotel_city") or "").strip()
        lat = as_coord(hotel.get("hotel_lat"))
        lon = as_coord(hotel.get("hotel_lon"))

        if not code:
            return self._empty_row(
                hotel,
                warnings=["hotel_code Accor absent — ligne ignorée pour jointure."],
            )

        # hotel_id feature-store = code Accor (pas un slug, pas un nom).
        # lat/lon fournis → pas de re-géocodage (coords RodPrep prioritaires).
        result = self._enrich.enrich(
            hotel_name=name,
            city=city,
            hotel_id=code,
            lat=lat,
            lon=lon,
            force_refresh=force_refresh,
        )
        features = result.features
        poi = features.poi or {}
        nearest = features.nearest or {}

        used_lat = as_coord(features.lat) if features.lat is not None else lat
        used_lon = as_coord(features.lon) if features.lon is not None else lon
        if lat is not None and lon is not None:
            geo_source = "rod_coords"
        elif used_lat is not None and used_lon is not None:
            geo_source = "name_geocode"
        else:
            geo_source = "failed"

        row: dict[str, Any] = {
            "hotel_code": code,
            "hotel_name": name,
            "hotel_lat": used_lat,
            "hotel_lon": used_lon,
            "geo_source": geo_source,
            "plage_distance_km": nearest.get("d_nearest_beach_km")
            or nearest.get("nearest_beach_km"),
            "commerce_fb_100m": poi.get("d_poi_fb_0_0_1km", 0) or 0,
            "commerce_fb_500m": poi.get("d_poi_fb_0_0_5km", 0) or 0,
            "commerce_non_fb_100m": poi.get("d_poi_not_fb_0_0_1km", 0) or 0,
            "commerce_non_fb_500m": poi.get("d_poi_not_fb_0_0_5km", 0) or 0,
        }
        for key, value in nearest.items():
            if key.startswith("d_nearest_") and key.endswith("_m"):
                clean = key.replace("d_nearest_", "distance_", 1)
                row[clean] = value
            elif key.startswith("nearest_") and key.endswith("_m") and not key.endswith("_km"):
                # clés non préfixées d_ (ex. nearest_beach_m avant prefix)
                clean = key.replace("nearest_", "distance_", 1)
                row.setdefault(clean, value)

        if result.warnings:
            row["warnings"] = "; ".join(result.warnings)
        return row

    def _empty_row(
        self,
        hotel: pd.Series | dict[str, Any],
        *,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        code = self._normalize_code(hotel.get("hotel_code")) or ""
        name = str(hotel.get("hotel_name") or code or "").strip()
        row: dict[str, Any] = {
            "hotel_code": code,
            "hotel_name": name,
            "hotel_lat": as_coord(hotel.get("hotel_lat")),
            "hotel_lon": as_coord(hotel.get("hotel_lon")),
            "geo_source": "failed",
            "plage_distance_km": None,
            "commerce_fb_100m": 0,
            "commerce_fb_500m": 0,
            "commerce_non_fb_100m": 0,
            "commerce_non_fb_500m": 0,
        }
        if warnings:
            row["warnings"] = "; ".join(warnings)
        return row

    @staticmethod
    def _normalize_code(value: Any) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "nan", "null"}:
            return None
        return text
