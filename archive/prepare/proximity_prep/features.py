"""Indicateurs de proximité géographiques (indépendants du domaine hôtel).

Rôle métier ProximityPrep
-------------------------
1. **Commerces** : nombre de commerces **par catégorie OSM** (`shop=*`)
   pour chaque rayon de **100 m à 500 m** par pas de 100 m.
2. **Plage** : présence (oui/non = 1/0) d'au moins une plage dans
   chaque rayon de **1 km à 5 km** par pas de 1 km.

Entrée : un point ``(lat, lon)``.
Sortie : dictionnaire de features numériques.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable, Sequence

import requests

from rod_ia.config.settings import Settings, get_settings

# ---------------------------------------------------------------------------
# Constantes métier (spécification ProximityPrep)
# ---------------------------------------------------------------------------

# Commerces : 100 m, 200 m, 300 m, 400 m, 500 m
COMMERCE_RADII_M: tuple[int, ...] = (100, 200, 300, 400, 500)

# Plage : présence dans 1 km … 5 km
BEACH_RADII_KM: tuple[int, ...] = (1, 2, 3, 4, 5)

# Catégories shop OSM suivies (F&B vs non-F&B pour les agrégats)
FB_CATEGORIES: tuple[str, ...] = (
    "convenience",
    "bakery",
    "supermarket",
    "alcohol",
    "confectionery",
    "beverages",
    "grocery",
    "ice_cream",
    "fast_food",
)
NON_FB_CATEGORIES: tuple[str, ...] = (
    "cosmetics",
    "gift",
    "tobacco",
    "kiosk",
    "pharmacy",
    "chemist",
)
SHOP_CATEGORIES: tuple[str, ...] = FB_CATEGORIES + NON_FB_CATEGORIES

BEACH_TAGS: tuple[tuple[str, str], ...] = (
    ("natural", "beach"),
    ("leisure", "beach_resort"),
    ("leisure", "swimming_area"),
)

# Overpass : chercher un peu plus large que le max utile (500 m / 5 km)
_COMMERCE_FETCH_M = max(COMMERCE_RADII_M)
_BEACH_FETCH_M = max(BEACH_RADII_KM) * 1000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance orthodromique en mètres."""
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def empty_proximity_features() -> dict[str, float]:
    """Grille complète de features à 0 (commerce) / 0 (plage absente)."""
    features: dict[str, float] = {}
    for radius_m in COMMERCE_RADII_M:
        for cat in SHOP_CATEGORIES:
            features[f"commerce_{cat}_{radius_m}m"] = 0.0
        features[f"commerce_fb_{radius_m}m"] = 0.0
        features[f"commerce_non_fb_{radius_m}m"] = 0.0
    for radius_km in BEACH_RADII_KM:
        features[f"plage_{radius_km}km"] = 0.0
    features["plage_distance_km"] = float("nan")
    return features


def count_commerce_by_category(
    shops: Sequence[dict[str, Any]],
    *,
    radii_m: Sequence[int] = COMMERCE_RADII_M,
    categories: Sequence[str] = SHOP_CATEGORIES,
) -> dict[str, float]:
    """Compte les commerces par catégorie et par rayon (cumulatif ≤ R).

    Chaque élément de ``shops`` doit avoir ``shop`` (catégorie) et ``distance_m``.
    """
    features: dict[str, float] = {}
    fb_set = set(FB_CATEGORIES)
    nfb_set = set(NON_FB_CATEGORIES)

    for radius_m in radii_m:
        within = [s for s in shops if float(s.get("distance_m", 1e18)) <= radius_m]
        for cat in categories:
            features[f"commerce_{cat}_{radius_m}m"] = float(
                sum(1 for s in within if s.get("shop") == cat)
            )
        features[f"commerce_fb_{radius_m}m"] = float(
            sum(1 for s in within if s.get("shop") in fb_set)
        )
        features[f"commerce_non_fb_{radius_m}m"] = float(
            sum(1 for s in within if s.get("shop") in nfb_set)
        )
    return features


def beach_presence_flags(
    beach_distances_m: Sequence[float],
    *,
    radii_km: Sequence[int] = BEACH_RADII_KM,
) -> dict[str, float]:
    """Indicateurs 0/1 : existe-t-il une plage à ≤ R km ?"""
    features: dict[str, float] = {}
    dists = [float(d) for d in beach_distances_m if d is not None and d == d]
    nearest_m = min(dists) if dists else None

    for radius_km in radii_km:
        max_m = radius_km * 1000.0
        features[f"plage_{radius_km}km"] = (
            1.0 if any(d <= max_m for d in dists) else 0.0
        )

    if nearest_m is None:
        features["plage_distance_km"] = float("nan")
    else:
        features["plage_distance_km"] = nearest_m / 1000.0
    return features


class ProximityFeatures:
    """Calcule les indicateurs de proximité pour un point géographique.

    Indépendant du domaine hôtel : pas de code Accor, pas de géocodage d'adresse.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        fetch_shops: Callable[[float, float], list[dict[str, Any]]] | None = None,
        fetch_beaches: Callable[[float, float], list[float]] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._fetch_shops = fetch_shops or self._overpass_shops
        self._fetch_beaches = fetch_beaches or self._overpass_beach_distances_m

    def for_point(self, lat: float, lon: float) -> dict[str, float]:
        """Point → features commerce (100–500 m) + plage (1–5 km)."""
        shops = self._fetch_shops(float(lat), float(lon))
        beach_dists = self._fetch_beaches(float(lat), float(lon))
        features = empty_proximity_features()
        features.update(count_commerce_by_category(shops))
        features.update(beach_presence_flags(beach_dists))
        return features

    # ------------------------------------------------------------------
    # Overpass
    # ------------------------------------------------------------------

    def _overpass_shops(self, lat: float, lon: float) -> list[dict[str, Any]]:
        types_regex = "|".join(SHOP_CATEGORIES)
        query = f"""
[out:json][timeout:40];
(
  node["shop"~"{types_regex}"](around:{_COMMERCE_FETCH_M},{lat},{lon});
  way["shop"~"{types_regex}"](around:{_COMMERCE_FETCH_M},{lat},{lon});
  relation["shop"~"{types_regex}"](around:{_COMMERCE_FETCH_M},{lat},{lon});
);
out center tags;
"""
        elements = self._overpass(query)
        shops: list[dict[str, Any]] = []
        for element in elements:
            p_lat, p_lon = self._element_coords(element)
            if p_lat is None or p_lon is None:
                continue
            shop = element.get("tags", {}).get("shop", "")
            if shop not in SHOP_CATEGORIES:
                continue
            shops.append(
                {
                    "lat": p_lat,
                    "lon": p_lon,
                    "shop": shop,
                    "distance_m": haversine_m(lat, lon, p_lat, p_lon),
                }
            )
        return shops

    def _overpass_beach_distances_m(self, lat: float, lon: float) -> list[float]:
        tag_filters = "\n".join(
            f'  node["{key}"="{value}"](around:{_BEACH_FETCH_M},{lat},{lon});\n'
            f'  way["{key}"="{value}"](around:{_BEACH_FETCH_M},{lat},{lon});\n'
            f'  relation["{key}"="{value}"](around:{_BEACH_FETCH_M},{lat},{lon});'
            for key, value in BEACH_TAGS
        )
        query = f"""
[out:json][timeout:40];
(
{tag_filters}
);
out center tags;
"""
        distances: list[float] = []
        for element in self._overpass(query):
            p_lat, p_lon = self._element_coords(element)
            if p_lat is None or p_lon is None:
                continue
            distances.append(haversine_m(lat, lon, p_lat, p_lon))
        return distances

    def _overpass(self, query: str, *, retries: int = 2) -> list[dict[str, Any]]:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = requests.post(
                    self.settings.overpass_url,
                    data={"data": query},
                    headers={"User-Agent": self.settings.user_agent},
                    timeout=50,
                )
                if response.status_code in (429, 504, 502) and attempt < retries:
                    import time

                    time.sleep(1.5 * (attempt + 1))
                    continue
                response.raise_for_status()
                return list(response.json().get("elements", []))
            except Exception as exc:
                last_exc = exc
                if attempt < retries:
                    import time

                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        if last_exc:
            raise last_exc
        return []


    @staticmethod
    def _element_coords(element: dict[str, Any]) -> tuple[float | None, float | None]:
        p_lat = element.get("lat") or element.get("center", {}).get("lat")
        p_lon = element.get("lon") or element.get("center", {}).get("lon")
        if p_lat is None or p_lon is None:
            return None, None
        return float(p_lat), float(p_lon)
