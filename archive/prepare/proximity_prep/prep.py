"""ProximityPrep — commerces par catégorie (100–500 m) et présence plage (1–5 km).

Orchestration pipeline :
  - charge les hôtels (``hotel_code`` Accor + coords RodPrep) ;
  - calcule les indicateurs via :class:`ProximityFeatures` au point
    ``(hotel_lat, hotel_lon)`` ;
  - sérialise une table à grain ``hotel_code``.

Spécification
-------------
* **Commerces** : pour chaque catégorie OSM (bakery, convenience, …) et
  chaque rayon 100, 200, 300, 400, 500 m → nombre de commerces ≤ rayon.
  Agrégats ``commerce_fb_{R}m`` / ``commerce_non_fb_{R}m``.
* **Plage** : pour chaque rayon 1, 2, 3, 4, 5 km → indicateur 0/1
  (au moins une plage dans le rayon) + ``plage_distance_km`` (plus proche).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from prepare.proximity_prep.features import (
    BEACH_RADII_KM,
    COMMERCE_RADII_M,
    SHOP_CATEGORIES,
    ProximityFeatures,
    empty_proximity_features,
)
from rod_ia.config.settings import Settings, get_settings
from rod_ia.domain.services.enrich_hotel import geocode_hotel

# Champs d'identité hôtel (RodPrep) — miroir MeteoPrep.
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
        features: ProximityFeatures | None = None,
        # compat anciens appels / tests
        enrich: Any = None,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._settings = settings or get_settings()
        self._features = features or ProximityFeatures(self._settings)
        # ``enrich`` conservé pour compat signature (ignoré si features fourni)
        self._enrich = enrich

    def fill_input_from_rod(self, rod_output_dir: Path) -> Path:
        """Copie les champs d'identité depuis la sortie RodPrep.

        - ``hotel_code`` = code Accor (pas un slug, pas un nom)
        - ``hotel_lat`` / ``hotel_lon`` déjà résolus par RodPrep
        - lignes sans ``hotel_code`` exclues
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
        _ = force_refresh  # réservé (pas de cache interne ProximityFeatures)
        hotels = self.load_input()
        rows: list[dict[str, Any]] = []
        for i, (_, hotel) in enumerate(hotels.iterrows()):
            if i > 0:
                # Évite le rate-limit Overpass entre hôtels
                import time

                time.sleep(1.0)
            try:
                rows.append(self._row_for_hotel(hotel))
            except Exception as exc:
                rows.append(self._empty_row(hotel, warnings=[str(exc)]))
        frame = pd.DataFrame(rows)

        if frame.empty:
            frame = pd.DataFrame(columns=self._base_columns() + self._feature_columns())
        frame.to_parquet(self.output_dir / "proximity.parquet", index=False)
        frame.to_csv(self.output_dir / "proximity.csv", index=False)
        return frame

    def _row_for_hotel(self, hotel: pd.Series | dict[str, Any]) -> dict[str, Any]:
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

        geo_source = "rod_coords"
        warnings: list[str] = []

        if lat is None or lon is None:
            geo = geocode_hotel(name, "", city, settings=self._settings)
            if not geo:
                return self._empty_row(
                    hotel,
                    warnings=["Coordonnées absentes et géocodage nom échoué."],
                )
            lat = float(geo["lat"])
            lon = float(geo["lon"])
            geo_source = "name_geocode"

        try:
            feats = self._features.for_point(lat, lon)
        except Exception as exc:
            feats = empty_proximity_features()
            warnings.append(f"Calcul proximité en erreur: {exc}")

        row: dict[str, Any] = {
            "hotel_code": code,
            "hotel_name": name,
            "hotel_lat": lat,
            "hotel_lon": lon,
            "geo_source": geo_source,
        }
        row.update(feats)
        if warnings:
            row["warnings"] = "; ".join(warnings)
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
        }
        row.update(empty_proximity_features())
        if warnings:
            row["warnings"] = "; ".join(warnings)
        return row

    @staticmethod
    def _base_columns() -> list[str]:
        return ["hotel_code", "hotel_name", "hotel_lat", "hotel_lon", "geo_source"]

    @staticmethod
    def _feature_columns() -> list[str]:
        cols: list[str] = []
        for radius_m in COMMERCE_RADII_M:
            for cat in SHOP_CATEGORIES:
                cols.append(f"commerce_{cat}_{radius_m}m")
            cols.append(f"commerce_fb_{radius_m}m")
            cols.append(f"commerce_non_fb_{radius_m}m")
        for radius_km in BEACH_RADII_KM:
            cols.append(f"plage_{radius_km}km")
        cols.append("plage_distance_km")
        return cols

    @staticmethod
    def _normalize_code(value: Any) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "nan", "null"}:
            return None
        return text
