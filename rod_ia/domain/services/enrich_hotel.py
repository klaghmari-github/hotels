"""Enrichissement géographique : géocodage, météo, POI (0.1–0.5 km)."""

from __future__ import annotations

import math
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from rod_ia.config.settings import Settings, get_settings
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


class EnrichHotelService:
    """Géocode, enrichit et persiste les features dans le feature store."""

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
    ) -> Tuple[str, EnrichedHotelFeatures, list[str]]:
        warnings: list[str] = []
        resolved_id = hotel_id or self.resolve_hotel_id(hotel_name, city)
        if not resolved_id:
            warnings.append(
                f"Hôtel non trouvé dans le registre: '{hotel_name}'. "
                "Enrichissement sans hotel_id canonique."
            )
            resolved_id = self._fallback_slug(hotel_name, city)

        if not force_refresh:
            cached = self.feature_store.load_enriched(resolved_id)
            if cached and cached.lat is not None:
                return resolved_id, cached, warnings

        geo = self._geocode_hotel(hotel_name, address, city)
        if not geo:
            empty = EnrichedHotelFeatures()
            self.feature_store.save_enriched(resolved_id, empty)
            warnings.append("Géocodage échoué.")
            return resolved_id, empty, warnings

        lat, lon = geo["lat"], geo["lon"]
        warnings.extend(
            self.identity_registry.update_nominatim_coords(resolved_id, lat, lon)
        )

        weather = self._fetch_weather_12_months(lat, lon)
        try:
            pois = self._fetch_poi(lat, lon)
            poi_features, nearest = self._compute_poi_features(pois)
        except Exception as exc:
            poi_features, nearest = {}, {}
            warnings.append(f"POI indisponibles: {exc}")

        features = EnrichedHotelFeatures(
            lat=lat,
            lon=lon,
            address_resolved=geo.get("address_resolved", ""),
            poi=self._prefix_descriptive(poi_features),
            weather_monthly=self._prefix_descriptive(weather),
            nearest=self._prefix_descriptive(nearest),
        )
        self.feature_store.save_enriched(resolved_id, features)
        return resolved_id, features, warnings

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
        query = ", ".join(
            part
            for part in [hotel_name, address, city, self.settings.default_country]
            if part
        )
        response = requests.get(
            self.settings.nominatim_url,
            params={"q": query, "format": "json", "limit": 1, "addressdetails": 1},
            headers={"User-Agent": self.settings.user_agent},
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

    def _fetch_weather_12_months(self, lat: float, lon: float) -> Dict[str, float]:
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
                [
                    p
                    for p in pois
                    if p["distance_m"] <= max_m and p.get("shop") in FB_TYPES
                ]
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