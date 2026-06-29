"""
Script d'enrichissement IA pour un hôtel (partie "data collection + nettoyage").

Objectif (selon ta description) :
1. Partir d'un hôtel (nom + ville optionnelle)
2. Trouver sa géolocalisation (lat/lon) via Nominatim
3. À partir de la géoloc :
   - Récupérer les données météo (via meteostat)
   - Récupérer les données de proximité / POI (via Overpass / OSM : commerces)
4. Nettoyer et structurer les données dans le format attendu par les simulateurs / modèles IA
   (poi_fb/not_fb par rayon, weather stats mensuelles, etc.)

Ce module produit un dict "hotel_enriched" prêt à être passé à :
- hotel_ca_projector.project(...)
- rod_full_simulator
- etc.

Dépendances recommandées :
    pip install meteostat requests pandas
"""

import json
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

# Optionnel : meteostat
try:
    from meteostat import Hourly, Point
    HAS_METEOSTAT = True
except ImportError:
    HAS_METEOSTAT = False

# ============================================================
# Configuration
# ============================================================

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "accor-rod-enricher/1.0 (contact: data-team)"

# Types de commerces (comme dans le projet)
FB_TYPES = ["convenience", "bakery", "supermarket", "alcohol", "confectionery",
            "beverages", "grocery", "ice_cream"]
NOT_FB_TYPES = ["cosmetics", "gift", "tobacco", "kiosk", "pharmacy"]

DEFAULT_RADII = [1.0, 2.0, 3.0, 4.0, 5.0]   # km


# ============================================================
# Géolocalisation
# ============================================================

def geocode_hotel(hotel_name: str, city: Optional[str] = None, country: str = "France") -> Optional[Dict]:
    """
    Trouve lat/lon + ville via Nominatim.
    Retourne dict avec 'lat', 'lon', 'city', 'address' ou None.
    """
    query = hotel_name
    if city:
        query += f", {city}"
    if country:
        query += f", {country}"

    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None

        item = data[0]
        lat = float(item["lat"])
        lon = float(item["lon"])

        address = item.get("address", {})
        resolved_city = address.get("city") or address.get("town") or address.get("village") or city

        return {
            "lat": lat,
            "lon": lon,
            "city": resolved_city,
            "country": country,
            "address": item.get("display_name", ""),
            "hotel_name_input": hotel_name,
        }
    except Exception as e:
        print(f"[geocode] Erreur pour '{hotel_name}': {e}")
        return None


# ============================================================
# POI (Proximité / commerces)
# ============================================================

def fetch_poi(lat: float, lon: float, radius_km: float = 3.0) -> pd.DataFrame:
    """
    Récupère les POI commerces autour d'un point via Overpass.
    Retourne un DataFrame brut (à nettoyer ensuite).
    """
    shop_types = FB_TYPES + NOT_FB_TYPES
    shop_filter = "|".join(shop_types)

    query = f"""
    [out:json][timeout:60];
    (
      node["shop"](around:{radius_km*1000},{lat},{lon});
      way["shop"](around:{radius_km*1000},{lat},{lon});
      node["amenity"="pharmacy"](around:{radius_km*1000},{lat},{lon});
    );
    out center;
    """

    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=90)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception as e:
        print(f"[poi] Erreur Overpass: {e}")
        return pd.DataFrame()

    records = []
    for el in elements:
        tags = el.get("tags", {})
        shop_type = tags.get("shop") or ("pharmacy" if tags.get("amenity") == "pharmacy" else None)
        if not shop_type:
            continue

        # Coordonnées
        if "center" in el:
            plat, plon = el["center"]["lat"], el["center"]["lon"]
        else:
            plat, plon = el.get("lat"), el.get("lon")
            if plat is None:
                continue

        dist = _haversine(lat, lon, plat, plon)

        records.append({
            "lat": plat,
            "lon": plon,
            "dist_km": dist,
            "shop_type": shop_type.lower(),
            "name": tags.get("name", ""),
            "brand": tags.get("brand", ""),
        })

    return pd.DataFrame(records)


def _haversine(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def compute_poi_features(poi_df: pd.DataFrame, radii: List[float] = None) -> Dict:
    """Agrège les POI comme dans le projet (fb / not_fb par rayon)."""
    if poi_df.empty or "shop_type" not in poi_df.columns:
        return {f"{t}_{r}km": 0 for t in ["fb", "not_fb"] for r in (radii or DEFAULT_RADII)}

    radii = radii or DEFAULT_RADII
    poi_df = poi_df.copy()
    poi_df["is_fb"] = poi_df["shop_type"].isin(FB_TYPES)
    poi_df["is_not_fb"] = poi_df["shop_type"].isin(NOT_FB_TYPES)

    features = {}
    for r in radii:
        mask = poi_df["dist_km"] <= r
        features[f"fb_{r}km"] = int(mask & poi_df["is_fb"]).sum()
        features[f"not_fb_{r}km"] = int(mask & poi_df["is_not_fb"]).sum()

    return features


# ============================================================
# Météo
# ============================================================

def fetch_weather(lat: float, lon: float, days: int = 365) -> pd.DataFrame:
    """Récupère les données météo via meteostat (si disponible)."""
    if not HAS_METEOSTAT:
        print("[weather] meteostat non installé → retour vide")
        return pd.DataFrame()

    end = datetime.now()
    start = end - timedelta(days=days)

    try:
        point = Point(lat, lon)
        data = Hourly(point, start, end).fetch()
        if data.empty:
            return pd.DataFrame()
        data = data.reset_index()
        data["lat"] = lat
        data["lon"] = lon
        return data
    except Exception as e:
        print(f"[weather] Erreur: {e}")
        return pd.DataFrame()


def aggregate_weather(weather_df: pd.DataFrame) -> Dict:
    """Crée des features mensuelles / saisonnières (similaire à weather_data.ipynb)."""
    if weather_df.empty:
        return {"weather_available": False}

    weather_df = weather_df.copy()
    weather_df["month"] = pd.to_datetime(weather_df["time"]).dt.month

    agg = {}
    for m in range(1, 13):
        month_data = weather_df[weather_df["month"] == m]
        if month_data.empty:
            continue
        agg[f"m{m:02d}_temp_mean"] = month_data["temp"].mean()
        agg[f"m{m:02d}_prcp_mean"] = month_data.get("prcp", pd.Series([0])).mean()
        agg[f"m{m:02d}_rhum_mean"] = month_data.get("rhum", pd.Series([0])).mean()

    agg["weather_available"] = True
    return agg


# ============================================================
# Nettoyage global
# ============================================================

def clean_hotel_name(name: str) -> str:
    """Nettoyage basique des noms d'hôtels."""
    if not isinstance(name, str):
        return ""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = " ".join(name.split())
    return name.strip().lower().title()


def enrich_hotel(
    hotel_name: str,
    city: Optional[str] = None,
    country: str = "France",
    poi_radii: List[float] = None,
    weather_days: int = 365,
) -> Dict:
    """
    Pipeline complet : géo + meteo + POI + nettoyage.
    Retourne un dict prêt pour les modèles/simulateurs.
    """
    hotel_name_clean = clean_hotel_name(hotel_name)

    # 1. Géolocalisation
    loc = geocode_hotel(hotel_name, city, country)
    if not loc:
        return {"hotel_name": hotel_name, "error": "geocoding_failed"}

    lat, lon = loc["lat"], loc["lon"]

    result = {
        "hotel_name": hotel_name,
        "hotel_name_clean": hotel_name_clean,
        "lat": lat,
        "lon": lon,
        "city": loc.get("city"),
        "country": country,
    }

    # 2. POI
    poi_df = fetch_poi(lat, lon, max(poi_radii or DEFAULT_RADII))
    poi_features = compute_poi_features(poi_df, poi_radii)
    result.update(poi_features)
    result["poi_raw_count"] = len(poi_df)

    # 3. Météo
    wdf = fetch_weather(lat, lon, weather_days)
    weather_features = aggregate_weather(wdf)
    result.update(weather_features)

    # 4. Nettoyage final + features dérivées
    result = _final_cleaning(result)

    return result


def _final_cleaning(data: Dict) -> Dict:
    """Nettoyage et ajouts de features utiles pour l'IA."""
    # Remplacer NaN
    for k, v in list(data.items()):
        if isinstance(v, float) and (pd.isna(v) or v != v):
            data[k] = 0.0

    # Features dérivées simples
    if "fb_3km" in data and "not_fb_3km" in data:
        total = data["fb_3km"] + data["not_fb_3km"]
        data["poi_density_3km"] = total
        data["fb_ratio_3km"] = data["fb_3km"] / total if total > 0 else 0.5

    data["enriched_at"] = datetime.now().isoformat()
    return data


# ============================================================
# Exemple d'utilisation
# ============================================================

if __name__ == "__main__":
    hotels = [
        "Ibis Budget Nice",
        "Novotel Paris Tour Eiffel",
        "Mercure Lyon Centre",
    ]

    for h in hotels:
        print(f"\n=== Enrichissement : {h} ===")
        enriched = enrich_hotel(h, city=None)
        print({k: v for k, v in enriched.items() if not k.startswith("m0") and not k.endswith("km") or k in ["fb_3km", "not_fb_3km", "poi_density_3km"]})
        print("...")
