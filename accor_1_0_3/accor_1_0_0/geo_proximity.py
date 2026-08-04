"""
ProximityFromGeo — commerces / plage à partir de (lat, lon).

Utilisé optionnellement lors du rebuild All Data
(``fill_proximity=True``) pour enrichir la jointure.

Source : **Overpass API** (OpenStreetMap) — indépendant du domaine hôtel.

Features produites
------------------
* Commerces par catégorie OSM : rayons 100 → 500 m (pas de 100 m).
* Présence de plage : 0/1 aux distances 1 → 5 km + distance km min.

Les requêtes réseau peuvent être lentes / rate-limitées ; le rebuild
All Data désactive souvent ce fill par défaut pour rester réactif.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd
import requests

# Rayons commerces (mètres)
COMMERCE_RADII_M: tuple[int, ...] = (100, 200, 300, 400, 500)
# Rayons plage (km)
BEACH_RADII_KM: tuple[int, ...] = (1, 2, 3, 4, 5)

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

OVERPASS_URL = "https://overpass.openstreetmap.fr/api/interpreter"
USER_AGENT = "accord-data-studio/1.0"


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


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance orthodromique en mètres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def empty_proximity_features() -> dict[str, float]:
    """Grille complète de features à 0 / NaN plage."""
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


class ProximityFromGeo:
    """
    Calcule les indicateurs de proximité pour un point ``(lat, lon)``.

    Exemple
    -------
    >>> p = ProximityFromGeo()
    >>> feats = p.for_point(43.69, 7.24)
    >>> feats["commerce_fb_500m"]
    """

    def __init__(
        self,
        *,
        overpass_url: str = OVERPASS_URL,
        user_agent: str = USER_AGENT,
        fetch_shops: Callable[[float, float], list[dict[str, Any]]] | None = None,
        fetch_beaches: Callable[[float, float], list[float]] | None = None,
    ) -> None:
        self.overpass_url = overpass_url
        self.user_agent = user_agent
        self._fetch_shops = fetch_shops or self._overpass_shops
        self._fetch_beaches = fetch_beaches or self._overpass_beach_distances_m
        # Cache point arrondi → features (évite double appel Overpass)
        self._cache: dict[tuple[float, float], dict[str, float]] = {}

    def for_point(self, lat: float, lon: float) -> dict[str, float]:
        """Point → dict de features commerce + plage."""
        lat_f, lon_f = as_coord(lat), as_coord(lon)
        if lat_f is None or lon_f is None:
            return empty_proximity_features()
        key = (round(lat_f, 5), round(lon_f, 5))
        if key in self._cache:
            return dict(self._cache[key])
        try:
            shops = self._fetch_shops(lat_f, lon_f)
            beaches = self._fetch_beaches(lat_f, lon_f)
        except Exception:
            features = empty_proximity_features()
            self._cache[key] = features
            return dict(features)

        features = empty_proximity_features()
        features.update(self._count_shops(shops))
        features.update(self._beach_flags(beaches))
        self._cache[key] = features
        return dict(features)

    def for_hotels(
        self,
        hotels: pd.DataFrame,
        *,
        lat_col: str = "hotel_lat",
        lon_col: str = "hotel_lon",
        id_cols: Sequence[str] | None = None,
        pause_s: float = 1.0,
    ) -> pd.DataFrame:
        """Une ligne de proximité par hôtel."""
        id_cols = id_cols or ("hotel_code", "hotel_name")
        if hotels is None or hotels.empty:
            return pd.DataFrame()
        rows: list[dict[str, Any]] = []
        for i, (_, h) in enumerate(hotels.iterrows()):
            if i > 0 and pause_s > 0:
                time.sleep(pause_s)
            feats = self.for_point(h.get(lat_col), h.get(lon_col))
            row: dict[str, Any] = {**feats, lat_col: h.get(lat_col), lon_col: h.get(lon_col)}
            for col in id_cols:
                if col in hotels.columns:
                    row[col] = h.get(col)
            rows.append(row)
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Calculs locaux
    # ------------------------------------------------------------------

    @staticmethod
    def _count_shops(shops: list[dict[str, Any]]) -> dict[str, float]:
        features: dict[str, float] = {}
        fb_set, nfb_set = set(FB_CATEGORIES), set(NON_FB_CATEGORIES)
        for radius_m in COMMERCE_RADII_M:
            within = [s for s in shops if float(s.get("distance_m", 1e18)) <= radius_m]
            for cat in SHOP_CATEGORIES:
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

    @staticmethod
    def _beach_flags(dists_m: list[float]) -> dict[str, float]:
        features: dict[str, float] = {}
        dists = [float(d) for d in dists_m if d is not None and d == d]
        nearest = min(dists) if dists else None
        for radius_km in BEACH_RADII_KM:
            max_m = radius_km * 1000.0
            features[f"plage_{radius_km}km"] = (
                1.0 if any(d <= max_m for d in dists) else 0.0
            )
        features["plage_distance_km"] = (
            nearest / 1000.0 if nearest is not None else float("nan")
        )
        return features

    # ------------------------------------------------------------------
    # Overpass
    # ------------------------------------------------------------------

    def _overpass_shops(self, lat: float, lon: float) -> list[dict[str, Any]]:
        radius = max(COMMERCE_RADII_M)
        types_regex = "|".join(SHOP_CATEGORIES)
        query = f"""
[out:json][timeout:40];
(
  node["shop"~"{types_regex}"](around:{radius},{lat},{lon});
  way["shop"~"{types_regex}"](around:{radius},{lat},{lon});
  relation["shop"~"{types_regex}"](around:{radius},{lat},{lon});
);
out center tags;
"""
        shops: list[dict[str, Any]] = []
        for el in self._overpass(query):
            p_lat, p_lon = self._element_coords(el)
            if p_lat is None or p_lon is None:
                continue
            shop = (el.get("tags") or {}).get("shop", "")
            if shop not in SHOP_CATEGORIES:
                continue
            shops.append(
                {
                    "shop": shop,
                    "distance_m": haversine_m(lat, lon, p_lat, p_lon),
                }
            )
        return shops

    def _overpass_beach_distances_m(self, lat: float, lon: float) -> list[float]:
        radius = max(BEACH_RADII_KM) * 1000
        tag_filters = "\n".join(
            f'  node["{k}"="{v}"](around:{radius},{lat},{lon});\n'
            f'  way["{k}"="{v}"](around:{radius},{lat},{lon});\n'
            f'  relation["{k}"="{v}"](around:{radius},{lat},{lon});'
            for k, v in BEACH_TAGS
        )
        query = f"""
[out:json][timeout:40];
(
{tag_filters}
);
out center tags;
"""
        dists: list[float] = []
        for el in self._overpass(query):
            p_lat, p_lon = self._element_coords(el)
            if p_lat is None or p_lon is None:
                continue
            dists.append(haversine_m(lat, lon, p_lat, p_lon))
        return dists

    # Fallbacks si le endpoint principal est down / rate-limité
    OVERPASS_FALLBACKS: tuple[str, ...] = (
        "https://overpass.openstreetmap.fr/api/interpreter",
        "https://overpass.osm.ch/api/interpreter",
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    )

    def _overpass(self, query: str, *, retries: int = 1) -> list[dict[str, Any]]:
        last_exc: Exception | None = None
        # essayer URL configurée puis fallbacks (dédupliqués)
        urls: list[str] = []
        for u in (self.overpass_url, *self.OVERPASS_FALLBACKS):
            if u and u not in urls:
                urls.append(u)
        for url in urls:
            for attempt in range(retries + 1):
                try:
                    resp = requests.post(
                        url,
                        data={"data": query},
                        headers={"User-Agent": self.user_agent},
                        timeout=35,
                    )
                    if resp.status_code in (429, 502, 503, 504) and attempt < retries:
                        time.sleep(1.2 * (attempt + 1))
                        continue
                    resp.raise_for_status()
                    # mémoriser le miroir qui marche
                    self.overpass_url = url
                    return list(resp.json().get("elements", []))
                except Exception as exc:
                    last_exc = exc
                    if attempt < retries:
                        time.sleep(0.8 * (attempt + 1))
                        continue
                    break  # next mirror
        if last_exc:
            raise last_exc
        return []

    @staticmethod
    def _element_coords(element: dict[str, Any]) -> tuple[float | None, float | None]:
        p_lat = element.get("lat") or (element.get("center") or {}).get("lat")
        p_lon = element.get("lon") or (element.get("center") or {}).get("lon")
        if p_lat is None or p_lon is None:
            return None, None
        return float(p_lat), float(p_lon)

    @staticmethod
    def proximity_columns() -> list[str]:
        return list(empty_proximity_features().keys())


# ---------------------------------------------------------------------------
# Persistance sous accord/data/hotel_proximity_data.xlsx
# ---------------------------------------------------------------------------

PROXIMITY_FILENAME = "hotel_proximity_data.xlsx"
PROXIMITY_SHEET = "hotel_proximity"
DATA_DIR = Path(__file__).resolve().parent / "data"


def proximity_path() -> Path:
    """Chemin du fichier Excel de proximité."""
    return DATA_DIR / PROXIMITY_FILENAME


def id_and_feature_columns() -> list[str]:
    """Colonnes standard du fichier proximité (ids + features numériques)."""
    return ["hotel_code", "hotel_name", "hotel_lat", "hotel_lon", *ProximityFromGeo.proximity_columns()]


def load_proximity_frame(path: Path | None = None) -> pd.DataFrame:
    """Charge hotel_proximity_data.xlsx si présent, sinon DataFrame vide."""
    path = path or proximity_path()
    if not path.exists():
        return pd.DataFrame(columns=id_and_feature_columns())
    try:
        frame = pd.read_excel(path, sheet_name=PROXIMITY_SHEET)
    except ValueError:
        frame = pd.read_excel(path, sheet_name=0)
    return frame


def save_proximity_frame(frame: pd.DataFrame, path: Path | None = None) -> Path:
    """Écrit le DataFrame proximité (remplit les colonnes manquantes à 0)."""
    path = path or proximity_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame.copy()
    # Colonnes features manquantes → 0
    for col in ProximityFromGeo.proximity_columns():
        if col not in out.columns:
            out[col] = 0.0
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    # plage_distance_km : 0 si inconnu pour éviter null UI (ou garder NaN→0)
    if "plage_distance_km" in out.columns:
        out["plage_distance_km"] = pd.to_numeric(out["plage_distance_km"], errors="coerce").fillna(0.0)
    cols = [c for c in id_and_feature_columns() if c in out.columns]
    rest = [c for c in out.columns if c not in cols]
    out = out[cols + rest]
    out.to_excel(path, index=False, sheet_name=PROXIMITY_SHEET)
    return path


def _hotels_from_data() -> pd.DataFrame:
    """Lit hotel_data.xlsx pour les coords."""
    hotel_path = DATA_DIR / "hotel_data.xlsx"
    if not hotel_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(hotel_path, sheet_name=0)
    except Exception:
        return pd.DataFrame()


def ensure_hotel_proximity_data(
    *,
    force_refresh: bool = False,
    pause_s: float = 1.0,
    hotels: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Garantit ``data/hotel_proximity_data.xlsx``.

    * Si le fichier existe et ``force_refresh=False`` → charge et retourne.
    * Sinon calcule via Overpass pour chaque hôtel de ``hotel_data``
      (lat/lon), sauvegarde, retourne.

    Parameters
    ----------
    force_refresh :
        Recalcule même si le fichier existe.
    pause_s :
        Pause entre hôtels (rate-limit Overpass).
    hotels :
        DataFrame optionnel (sinon lit hotel_data.xlsx).
    """
    path = proximity_path()
    if path.exists() and not force_refresh:
        frame = load_proximity_frame(path)
        if not frame.empty and "hotel_code" in frame.columns:
            return frame

    hotels = hotels if hotels is not None else _hotels_from_data()
    if hotels is None or hotels.empty:
        empty = pd.DataFrame(columns=id_and_feature_columns())
        save_proximity_frame(empty, path)
        return empty

    engine = ProximityFromGeo()
    frame = engine.for_hotels(
        hotels,
        lat_col="hotel_lat",
        lon_col="hotel_lon",
        id_cols=("hotel_code", "hotel_name"),
        pause_s=pause_s,
    )
    # Remplir features manquantes / NaN
    for col in ProximityFromGeo.proximity_columns():
        if col not in frame.columns:
            frame[col] = 0.0
        else:
            frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    save_proximity_frame(frame, path)
    return frame


def rebuild_hotel_proximity_data(*, pause_s: float = 1.0) -> dict[str, Any]:
    """
    Recalcule ``hotel_proximity_data.xlsx`` pour **chaque hôtel** de hotel_data.

    * Commerces par catégorie OSM : 100 → 500 m
    * Plage : présence 1 → 5 km + distance km
    * Écrit le Excel puis prêt pour rechargement UI
    """
    from geo_common import load_hotels

    hotels = load_hotels()
    if hotels.empty:
        raise ValueError("hotel_data.xlsx vide ou introuvable.")

    frame = ensure_hotel_proximity_data(
        force_refresh=True,
        pause_s=pause_s,
        hotels=hotels,
    )
    return {
        "ok": True,
        "path": str(proximity_path()),
        "rows": len(frame),
        "columns": list(frame.columns),
        "n_columns": len(frame.columns),
        "n_hotels": len(frame),
    }
