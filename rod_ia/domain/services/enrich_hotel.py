"""Enrichissement géographique : géocodage, météo, POI (0.1–0.5 km)."""

from __future__ import annotations

import hashlib
import math
import unicodedata
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from rod_ia.config.settings import Settings, get_settings
from rod_ia.domain.models.enrichment import EnrichResult
from rod_ia.domain.models.simulation import EnrichedHotelFeatures
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.ml_column_naming import MLColumnNaming

try:
    from meteostat import Hourly, Point

    HAS_METEOSTAT = True
except Exception:
    HAS_METEOSTAT = False

FB_TYPES = [
    "convenience", "bakery", "supermarket", "alcohol", "confectionery",
    "beverages", "grocery", "ice_cream", "fast_food",
]
NOT_FB_TYPES = ["cosmetics", "gift", "tobacco", "kiosk", "pharmacy", "chemist"]

BEACH_TAGS = (
    ('natural', 'beach'),
    ('leisure', 'beach_resort'),
    ('leisure', 'swimming_area'),
)
BEACH_SEARCH_RADIUS_KM = 5.0
BEACH_MISSING_SENTINEL_M = 99_999.0


class EnrichHotelService:
    """Orchestre enrichissement POI/météo avec lecture cache ou calcul frais.

    Flux :
      1. Résoudre ``hotel_id`` via le registre d'identité
      2. Si cache valide dans le feature store → retour immédiat (``source=cache``)
      3. Sinon → géocode + météo + POI → persistance (``source=computed``)
    """

    def __init__(
        self,
        feature_store: FeatureStoreRepository,
        identity_registry: HotelIdentityRegistry,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.feature_store = feature_store
        self.identity_registry = identity_registry

    def resolve_hotel_id(
        self, hotel_name: str, city: str = "", source: str = "display"
    ) -> Optional[str]:
        hotel_id = self.identity_registry.resolve(source, hotel_name, city or None)
        if hotel_id:
            return hotel_id
        return self.identity_registry.resolve("any", hotel_name, city or None)

    def enrich(
        self,
        hotel_name: str,
        address: str = "",
        city: str = "",
        force_refresh: bool = False,
        hotel_id: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
    ) -> EnrichResult:
        warnings: list[str] = []
        resolved_id, warnings = self._resolve_hotel_id(hotel_name, city, hotel_id, warnings)
        fingerprint = self._enrichment_fingerprint(hotel_name, address, city, lat, lon)

        if not force_refresh:
            cached = self._load_from_cache(resolved_id, fingerprint)
            if cached is not None:
                return cached

        return self._compute_and_persist(
            resolved_id,
            hotel_name,
            address,
            city,
            fingerprint,
            warnings,
            lat=lat,
            lon=lon,
        )

    def _resolve_hotel_id(
        self,
        hotel_name: str,
        city: str,
        hotel_id: str | None,
        warnings: list[str],
    ) -> Tuple[str, list[str]]:
        resolved_id = hotel_id or self.resolve_hotel_id(hotel_name, city)
        if not resolved_id:
            warnings.append(
                f"Hôtel non trouvé dans le registre: '{hotel_name}'. "
                "Enrichissement avec identifiant provisoire."
            )
            resolved_id = self._fallback_slug(hotel_name, city)
        return resolved_id, warnings

    def _load_from_cache(self, hotel_id: str, fingerprint: str) -> EnrichResult | None:
        """Cas 1 : données déjà dans le feature store."""
        if not self.feature_store.has_valid_enrichment(hotel_id):
            return None
        if not self.feature_store.enrichment_fingerprint_matches(hotel_id, fingerprint):
            return None

        features = self.feature_store.load_enriched(hotel_id)
        if features is None or features.lat is None:
            return None

        meta = self.feature_store.load_meta(hotel_id) or {}
        return EnrichResult(
            hotel_id=hotel_id,
            features=features,
            source="cache",
            warnings=[],
            cached_at=meta.get("updated_at"),
        )

    def _compute_and_persist(
        self,
        hotel_id: str,
        hotel_name: str,
        address: str,
        city: str,
        fingerprint: str,
        warnings: list[str],
        lat: float | None = None,
        lon: float | None = None,
    ) -> EnrichResult:
        """Cas 2 : calcul frais puis persistance feature store.

        Si ``lat``/``lon`` sont fournis, le géocodage Nominatim est ignoré.
        """
        address_resolved = ""
        lat_f = self._as_coord(lat)
        lon_f = self._as_coord(lon)

        if lat_f is None or lon_f is None:
            geo = self._geocode_hotel(hotel_name, address, city)
            if not geo:
                empty = EnrichedHotelFeatures()
                self.feature_store.save_enriched(hotel_id, empty, fingerprint=fingerprint)
                warnings.append("Géocodage échoué.")
                return EnrichResult(
                    hotel_id=hotel_id,
                    features=empty,
                    source="failed",
                    warnings=warnings,
                )
            lat_f, lon_f = float(geo["lat"]), float(geo["lon"])
            address_resolved = str(geo.get("address_resolved", ""))
            if self.identity_registry.get(hotel_id):
                warnings.extend(
                    self.identity_registry.update_nominatim_coords(hotel_id, lat_f, lon_f)
                )
                self.identity_registry.save()

        weather = self._fetch_weather_12_months(lat_f, lon_f)
        try:
            pois = self._fetch_poi(lat_f, lon_f)
            poi_features, nearest = self._compute_poi_features(pois)
        except Exception as exc:
            poi_features, nearest = {}, {}
            warnings.append(f"POI indisponibles: {exc}")

        try:
            beach_m = self._fetch_nearest_beach_m(lat_f, lon_f)
            nearest["nearest_beach_m"] = beach_m
            nearest["nearest_beach_km"] = beach_m / 1000.0
        except Exception as exc:
            nearest["nearest_beach_m"] = BEACH_MISSING_SENTINEL_M
            nearest["nearest_beach_km"] = BEACH_MISSING_SENTINEL_M / 1000.0
            warnings.append(f"Plages indisponibles: {exc}")

        features = EnrichedHotelFeatures(
            lat=lat_f,
            lon=lon_f,
            address_resolved=address_resolved,
            poi=self._prefix_descriptive(poi_features),
            weather_monthly=self._prefix_descriptive(weather),
            nearest=self._prefix_descriptive(nearest),
        )
        self.feature_store.save_enriched(hotel_id, features, fingerprint=fingerprint)
        meta = self.feature_store.load_meta(hotel_id) or {}

        return EnrichResult(
            hotel_id=hotel_id,
            features=features,
            source="computed",
            warnings=warnings,
            cached_at=meta.get("updated_at"),
        )

    @staticmethod
    def _enrichment_fingerprint(
        hotel_name: str,
        address: str,
        city: str,
        lat: float | None = None,
        lon: float | None = None,
    ) -> str:
        coords = ""
        if lat is not None and lon is not None:
            try:
                coords = f"|{float(lat):.6f}|{float(lon):.6f}"
            except (TypeError, ValueError):
                coords = ""
        raw = (
            f"{hotel_name.strip().lower()}|{address.strip().lower()}"
            f"|{city.strip().lower()}{coords}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _prefix_descriptive(features: Dict[str, float]) -> Dict[str, float]:
        return {
            MLColumnNaming.descriptive(key): float(value)
            for key, value in features.items()
            if value is not None
        }

    def _geocode_hotel(
        self, hotel_name: str, address: str, city: str
    ) -> Optional[Dict]:
        return geocode_hotel(hotel_name, address, city, settings=self.settings)

    def _fetch_weather_12_months(self, lat: float, lon: float) -> Dict[str, float]:
        """Agrège la météo horaire Meteostat (stations proches de lat/lon)."""
        if not HAS_METEOSTAT:
            return {}
        end = datetime.utcnow().replace(day=1)
        start = (end - timedelta(days=370)).replace(day=1)
        frame = Hourly(Point(lat, lon), start, end).fetch()
        if frame.empty:
            return {}
        frame = frame.reset_index()
        frame["month"] = pd.to_datetime(frame["time"]).dt.month
        features: dict[str, float] = {}
        for month, group in frame.groupby("month"):
            prefix = f"m{int(month):02d}"
            for col in ["temp", "dwpt", "rhum", "prcp", "snow", "wspd", "pres", "tsun"]:
                if col not in group.columns:
                    continue
                series = pd.to_numeric(group[col], errors="coerce")
                if series.dropna().empty:
                    continue
                features[f"{prefix}_{col}_mean"] = float(series.mean())
                features[f"{prefix}_{col}_min"] = float(series.min())
                features[f"{prefix}_{col}_max"] = float(series.max())
        return features

    def _fetch_poi(self, lat: float, lon: float) -> List[Dict]:
        radii = self.settings.default_poi_radii_km
        max_radius_m = int(max(radii) * 1000)
        types_regex = "|".join(FB_TYPES + NOT_FB_TYPES)
        query = f"""
[out:json][timeout:25];
(
  node["shop"~"{types_regex}"](around:{max_radius_m},{lat},{lon});
  way["shop"~"{types_regex}"](around:{max_radius_m},{lat},{lon});
  relation["shop"~"{types_regex}"](around:{max_radius_m},{lat},{lon});
);
out center tags;
"""
        response = requests.post(
            self.settings.overpass_url,
            data={"data": query},
            headers={"User-Agent": self.settings.user_agent},
            timeout=40,
        )
        response.raise_for_status()
        pois: list[dict] = []
        for element in response.json().get("elements", []):
            p_lat = element.get("lat") or element.get("center", {}).get("lat")
            p_lon = element.get("lon") or element.get("center", {}).get("lon")
            if p_lat is None or p_lon is None:
                continue
            shop = element.get("tags", {}).get("shop", "")
            distance = self._haversine_m(lat, lon, float(p_lat), float(p_lon))
            pois.append(
                {
                    "lat": float(p_lat),
                    "lon": float(p_lon),
                    "shop": shop,
                    "distance_m": distance,
                }
            )
        return pois

    def _fetch_nearest_beach_m(self, lat: float, lon: float) -> float:
        """Distance minimale à une plage (Overpass) — utile mix SOS / textile plage."""
        radius_m = int(BEACH_SEARCH_RADIUS_KM * 1000)
        tag_filters = "\n".join(
            f'  node["{key}"="{value}"](around:{radius_m},{lat},{lon});\n'
            f'  way["{key}"="{value}"](around:{radius_m},{lat},{lon});\n'
            f'  relation["{key}"="{value}"](around:{radius_m},{lat},{lon});'
            for key, value in BEACH_TAGS
        )
        query = f"""
[out:json][timeout:25];
(
{tag_filters}
);
out center tags;
"""
        response = requests.post(
            self.settings.overpass_url,
            data={"data": query},
            headers={"User-Agent": self.settings.user_agent},
            timeout=40,
        )
        response.raise_for_status()
        distances: list[float] = []
        for element in response.json().get("elements", []):
            p_lat = element.get("lat") or element.get("center", {}).get("lat")
            p_lon = element.get("lon") or element.get("center", {}).get("lon")
            if p_lat is None or p_lon is None:
                continue
            distances.append(
                self._haversine_m(lat, lon, float(p_lat), float(p_lon))
            )
        if not distances:
            return BEACH_MISSING_SENTINEL_M
        return float(min(distances))

    def _compute_poi_features(
        self, pois: List[Dict]
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        radii = self.settings.default_poi_radii_km
        features: dict[str, float] = {}
        nearest: dict[str, float] = {}
        for radius in radii:
            key = str(radius).replace(".", "_")
            max_m = radius * 1000
            fb_count = len(
                [p for p in pois if p["distance_m"] <= max_m and p.get("shop") in FB_TYPES]
            )
            nf_count = len(
                [
                    p
                    for p in pois
                    if p["distance_m"] <= max_m and p.get("shop") in NOT_FB_TYPES
                ]
            )
            features[f"poi_fb_0_{key}km"] = float(fb_count)
            features[f"poi_not_fb_0_{key}km"] = float(nf_count)
        for shop in sorted(set(FB_TYPES + NOT_FB_TYPES)):
            distances = [p["distance_m"] for p in pois if p.get("shop") == shop]
            if distances:
                nearest[f"nearest_{shop}_m"] = float(min(distances))
        return features, nearest

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(
            dlambda / 2
        ) ** 2
        return 2 * radius * math.asin(math.sqrt(a))

    @staticmethod
    def _fallback_slug(hotel_name: str, city: str) -> str:
        raw = f"{hotel_name}_{city}".lower().strip()
        raw = "".join(
            c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c)
        )
        slug = "".join(c if c.isalnum() else "_" for c in raw).strip("_")
        return slug[:80] or "unknown_hotel"

    @staticmethod
    def _as_coord(value: float | None) -> float | None:
        if value is None:
            return None
        try:
            coord = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(coord):
            return None
        return coord


def geocode_hotel(
    hotel_name: str,
    address: str = "",
    city: str = "",
    *,
    settings: Settings | None = None,
) -> Optional[Dict[str, float | str]]:
    """Géocode un hôtel via Nominatim (nom + adresse + ville)."""
    settings = settings or get_settings()
    query = ", ".join(
        part
        for part in [hotel_name, address, city, settings.default_country]
        if part
    )
    if not query:
        return None
    response = requests.get(
        settings.nominatim_url,
        params={"q": query, "format": "json", "limit": 1, "addressdetails": 1},
        headers={"User-Agent": settings.user_agent},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if not data:
        return None
    item = data[0]
    return {
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "address_resolved": item.get("display_name", ""),
    }