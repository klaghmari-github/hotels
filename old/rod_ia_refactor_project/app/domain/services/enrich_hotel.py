from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta
import json, math, unicodedata
import requests
import pandas as pd

from app.config.settings import DEFAULT_POI_RADII_KM, NOMINATIM_URL, OVERPASS_URL, USER_AGENT, DEFAULT_COUNTRY
from app.domain.models.simulation import EnrichedHotelFeatures

try:
    from meteostat import Hourly, Point
    HAS_METEOSTAT = True
except Exception:
    HAS_METEOSTAT = False

FB_TYPES = ["convenience", "bakery", "supermarket", "alcohol", "confectionery", "beverages", "grocery", "ice_cream", "fast_food"]
NOT_FB_TYPES = ["cosmetics", "gift", "tobacco", "kiosk", "pharmacy", "chemist"]

class EnrichHotelService:
    """Géocodage + météo + POI 0.1 à 0.5 km + cache feature store."""
    def __init__(self, feature_store_dir: str | Path):
        self.feature_store_dir = Path(feature_store_dir)
        self.feature_store_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_hotel_id(hotel_name: str, city: str = '') -> str:
        raw = f"{hotel_name}_{city}".lower().strip()
        raw = ''.join(c for c in unicodedata.normalize('NFKD', raw) if not unicodedata.combining(c))
        return ''.join(c if c.isalnum() else '_' for c in raw).strip('_')[:80] or 'unknown_hotel'

    def hotel_dir(self, hotel_id: str) -> Path:
        d = self.feature_store_dir / hotel_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def load_cached(self, hotel_id: str) -> EnrichedHotelFeatures | None:
        p = self.hotel_dir(hotel_id) / 'enriched.json'
        if p.exists():
            return EnrichedHotelFeatures.from_dict(json.loads(p.read_text(encoding='utf-8')))
        return None

    def save_cached(self, hotel_id: str, features: EnrichedHotelFeatures) -> None:
        p = self.hotel_dir(hotel_id) / 'enriched.json'
        p.write_text(json.dumps(features.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')

    def geocode_hotel(self, hotel_name: str, address: str = '', city: str = '', country: str = DEFAULT_COUNTRY) -> Dict | None:
        query = ', '.join([x for x in [hotel_name, address, city, country] if x])
        params = {'q': query, 'format': 'json', 'limit': 1, 'addressdetails': 1}
        r = requests.get(NOMINATIM_URL, params=params, headers={'User-Agent': USER_AGENT}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        item = data[0]
        return {'lat': float(item['lat']), 'lon': float(item['lon']), 'address_resolved': item.get('display_name','')}

    def fetch_weather_12_months(self, lat: float, lon: float) -> Dict[str, float]:
        if not HAS_METEOSTAT:
            return {}
        end = datetime.utcnow().replace(day=1)
        start = (end - timedelta(days=370)).replace(day=1)
        df = Hourly(Point(lat, lon), start, end).fetch()
        if df.empty:
            return {}
        df = df.reset_index()
        df['month'] = pd.to_datetime(df['time']).dt.month
        features = {}
        for month, g in df.groupby('month'):
            prefix = f'm{int(month):02d}'
            for col in ['temp','dwpt','rhum','prcp','snow','wspd','pres','tsun']:
                if col in g:
                    s = pd.to_numeric(g[col], errors='coerce')
                    features[f'{prefix}_{col}_mean'] = float(s.mean()) if not s.dropna().empty else 0.0
                    features[f'{prefix}_{col}_min'] = float(s.min()) if not s.dropna().empty else 0.0
                    features[f'{prefix}_{col}_max'] = float(s.max()) if not s.dropna().empty else 0.0
        return features

    def fetch_poi(self, lat: float, lon: float, radii_km: List[float] | None = None) -> List[Dict]:
        radii_km = radii_km or DEFAULT_POI_RADII_KM
        max_radius_m = int(max(radii_km) * 1000)
        types_regex = '|'.join(FB_TYPES + NOT_FB_TYPES)
        query = f'''
[out:json][timeout:25];
(
  node["shop"~"{types_regex}"](around:{max_radius_m},{lat},{lon});
  way["shop"~"{types_regex}"](around:{max_radius_m},{lat},{lon});
  relation["shop"~"{types_regex}"](around:{max_radius_m},{lat},{lon});
);
out center tags;
'''
        r = requests.post(OVERPASS_URL, data={'data': query}, headers={'User-Agent': USER_AGENT}, timeout=40)
        r.raise_for_status()
        pois=[]
        for e in r.json().get('elements', []):
            p_lat = e.get('lat') or e.get('center',{}).get('lat')
            p_lon = e.get('lon') or e.get('center',{}).get('lon')
            shop = e.get('tags',{}).get('shop','')
            if p_lat is None or p_lon is None:
                continue
            pois.append({'lat': float(p_lat), 'lon': float(p_lon), 'shop': shop, 'name': e.get('tags',{}).get('name',''), 'distance_m': self.haversine_m(lat, lon, float(p_lat), float(p_lon))})
        return pois

    @staticmethod
    def haversine_m(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2-lat1)
        dlambda = math.radians(lon2-lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return 2*R*math.asin(math.sqrt(a))

    def compute_poi_features(self, pois: List[Dict], radii_km: List[float] | None = None) -> tuple[Dict[str,float], Dict[str,float]]:
        radii_km = radii_km or DEFAULT_POI_RADII_KM
        features = {}
        nearest = {}
        for r in radii_km:
            key = str(r).replace('.', '_')
            max_m = r * 1000
            fb = [p for p in pois if p['distance_m'] <= max_m and p.get('shop') in FB_TYPES]
            nf = [p for p in pois if p['distance_m'] <= max_m and p.get('shop') in NOT_FB_TYPES]
            features[f'fb_0_{key}km'] = len(fb)
            features[f'not_fb_0_{key}km'] = len(nf)
        for shop in sorted(set(FB_TYPES + NOT_FB_TYPES)):
            dists = [p['distance_m'] for p in pois if p.get('shop') == shop]
            nearest[f'nearest_{shop}_m'] = min(dists) if dists else None
        return features, nearest

    def enrich(self, hotel_name: str, address: str = '', city: str = '', force_refresh: bool = False) -> tuple[str, EnrichedHotelFeatures]:
        hotel_id = self.make_hotel_id(hotel_name, city)
        cached = None if force_refresh else self.load_cached(hotel_id)
        if cached:
            return hotel_id, cached
        geo = self.geocode_hotel(hotel_name, address, city)
        if not geo:
            features = EnrichedHotelFeatures()
            self.save_cached(hotel_id, features)
            return hotel_id, features
        lat, lon = geo['lat'], geo['lon']
        weather = self.fetch_weather_12_months(lat, lon)
        try:
            pois = self.fetch_poi(lat, lon)
            poi_features, nearest = self.compute_poi_features(pois)
        except Exception:
            poi_features, nearest = {}, {}
        features = EnrichedHotelFeatures(lat=lat, lon=lon, address_resolved=geo.get('address_resolved',''), poi=poi_features, weather_monthly=weather, nearest=nearest)
        self.save_cached(hotel_id, features)
        return hotel_id, features
