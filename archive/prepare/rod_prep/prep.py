"""RodPrep — extraction et nettoyage du récapitulatif Excel ROD."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from rod_ia.config.settings import Settings, get_settings
from rod_ia.domain.models.identity import HotelRecord
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.enrich_hotel import geocode_hotel
from rod_ia.domain.services.rod_recap_extractor import (
    RECAP_GEO_ADDRESS_COLUMNS,
    RECAP_GEO_CITY_COLUMN,
    RECAP_GEO_COORDINATE_COLUMNS,
    RECAP_GEO_LATITUDE_COLUMN,
    RECAP_GEO_LONGITUDE_COLUMN,
    RECAP_NON_FEATURE_COLUMNS,
    RodRecapExtractor,
)


class RodPrep:
    """Prépare la table hôtel (code Accor, alias de nom, coordonnées) depuis le récap."""

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        registry_path: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._settings = settings or get_settings()
        self.registry_path = Path(registry_path or self._settings.identity_registry_path)
        self._registry = HotelIdentityRegistry(self.registry_path)

    def resolve_recap_path(self) -> Path:
        explicit = self.input_dir / "recapitulatif_rod.xlsx"
        if explicit.exists():
            return explicit
        for path in sorted(self.input_dir.glob("*.xlsx")):
            return path
        recap = self._settings.rod_recap_path
        if recap and recap.exists():
            return recap
        raise FileNotFoundError(
            f"Aucun Excel récap dans {self.input_dir} — copier le fichier dans Input/"
        )

    def seed_input_from_sources(self) -> Path:
        """Copie l'Excel récap depuis sources/raw vers Input si absent."""
        recap = self._settings.rod_recap_path
        if not recap or not recap.exists():
            raise FileNotFoundError("Récap Excel introuvable dans sources/raw")
        self.input_dir.mkdir(parents=True, exist_ok=True)
        target = self.input_dir / "recapitulatif_rod.xlsx"
        if not target.exists():
            shutil.copy2(recap, target)
        return target

    def run(self, *, geocode_missing: bool = True) -> pd.DataFrame:
        recap_path = self.resolve_recap_path()
        extractor = RodRecapExtractor(
            recap_path=recap_path,
            identity_registry=self._registry,
            output_path=self.output_dir / "rod_recap",
        )
        wide_internal = extractor.extract_wide()
        lookup = self._build_hotel_lookup(wide_internal, geocode_missing=geocode_missing)
        wide_public = self._public_wide(wide_internal)
        wide_public.to_parquet(self.output_dir / "rod_features.parquet", index=False)
        wide_public.to_csv(self.output_dir / "rod_features.csv", index=False)
        lookup.to_parquet(self.output_dir / "hotel_lookup.parquet", index=False)
        lookup.to_csv(self.output_dir / "hotel_lookup.csv", index=False)
        return lookup

    @staticmethod
    def _recap_feature_columns(columns: pd.Index) -> list[str]:
        skip = {"hotel_id", "code_h", *RECAP_NON_FEATURE_COLUMNS}
        return [c for c in columns if c not in skip]

    def _public_wide(self, wide: pd.DataFrame) -> pd.DataFrame:
        if wide.empty:
            return pd.DataFrame(columns=["hotel_code"])
        out = wide.copy()
        if "code_h" in out.columns:
            out.insert(0, "hotel_code", out["code_h"])
        drop = {"hotel_id", "code_h", *RECAP_NON_FEATURE_COLUMNS}
        out = out.drop(columns=[c for c in drop if c in out.columns])
        return out

    def _build_hotel_lookup(
        self,
        wide: pd.DataFrame,
        *,
        geocode_missing: bool = True,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        recap_slugs: set[str] = set()

        if not wide.empty and "hotel_id" in wide.columns:
            feature_cols = self._recap_feature_columns(wide.columns)
            for _, wrow in wide.iterrows():
                slug = str(wrow["hotel_id"])
                recap_slugs.add(slug)
                record = self._registry.get(slug)
                hotel_code = self._normalize_code_h(wrow.get("code_h"))
                rows.append(
                    {
                        "hotel_code": hotel_code,
                        **self._registry_metadata(record, slug),
                        "_registry_slug": slug,
                        **{c: wrow.get(c) for c in feature_cols},
                        RECAP_GEO_LATITUDE_COLUMN: wrow.get(RECAP_GEO_LATITUDE_COLUMN),
                        RECAP_GEO_LONGITUDE_COLUMN: wrow.get(RECAP_GEO_LONGITUDE_COLUMN),
                    }
                )

        for record in self._registry.all_records():
            if record.hotel_id in recap_slugs:
                continue
            rows.append(
                {
                    "hotel_code": None,
                    **self._registry_metadata(record, record.hotel_id),
                    "_registry_slug": record.hotel_id,
                    RECAP_GEO_LATITUDE_COLUMN: None,
                    RECAP_GEO_LONGITUDE_COLUMN: None,
                }
            )

        lookup = pd.DataFrame(rows)
        lookup = self._apply_hotel_coordinates(lookup, geocode_missing=geocode_missing)
        drop_cols = [
            c
            for c in (*RECAP_GEO_COORDINATE_COLUMNS, "_registry_slug")
            if c in lookup.columns
        ]
        return lookup.drop(columns=drop_cols)

    @staticmethod
    def _registry_metadata(record: HotelRecord | None, fallback: str) -> dict[str, Any]:
        if record is None:
            return {
                "hotel_name": fallback,
                "nom_hotel": fallback,
                "hotel_brand": None,
                "hotel_city": None,
                "nb_chambres": None,
            }
        return {
            "hotel_name": record.name_display or record.name_ventes or record.hotel_id,
            "nom_hotel": record.name_ventes or record.name_display or record.hotel_id,
            "hotel_brand": record.brand,
            "hotel_city": record.city,
            "nb_chambres": record.nb_chambres,
        }

    @staticmethod
    def _normalize_code_h(value: Any) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip()
        return text or None

    def _apply_hotel_coordinates(
        self,
        lookup: pd.DataFrame,
        *,
        geocode_missing: bool,
    ) -> pd.DataFrame:
        if lookup.empty:
            return lookup

        lats: list[float | None] = []
        lons: list[float | None] = []
        sources: list[str | None] = []
        registry_dirty = False

        for _, row in lookup.iterrows():
            lat, lon, source = self._resolve_hotel_coordinates(
                row, geocode=geocode_missing
            )
            lats.append(lat)
            lons.append(lon)
            sources.append(source)
            if source == "nominatim":
                slug = str(row.get("_registry_slug", ""))
                if slug and lat is not None and lon is not None:
                    self._registry.update_nominatim_coords(slug, lat, lon)
                    registry_dirty = True

        lookup = lookup.copy()
        lookup["hotel_lat"] = lats
        lookup["hotel_lon"] = lons
        lookup["hotel_geo_source"] = sources
        if registry_dirty:
            self._registry.save()
        return lookup

    def _resolve_hotel_coordinates(
        self,
        row: pd.Series,
        *,
        geocode: bool,
    ) -> tuple[float | None, float | None, str | None]:
        lat = self._parse_coord(row.get(RECAP_GEO_LATITUDE_COLUMN))
        lon = self._parse_coord(row.get(RECAP_GEO_LONGITUDE_COLUMN))
        if lat is not None and lon is not None:
            return lat, lon, "recap"

        slug = str(row.get("_registry_slug", ""))
        record = self._registry.get(slug) if slug else None
        if record:
            lat = self._parse_coord(record.lat_nominatim or record.lat_canonical)
            lon = self._parse_coord(record.lon_nominatim or record.lon_canonical)
            if lat is not None and lon is not None:
                return lat, lon, "registry"

        if not geocode:
            return None, None, None

        hotel_name = str(row.get("hotel_name") or row.get("nom_hotel") or "").strip()
        address = " ".join(
            str(row.get(col)).strip()
            for col in RECAP_GEO_ADDRESS_COLUMNS
            if col in row.index
            and row.get(col) is not None
            and str(row.get(col)).strip()
        )
        city = str(
            row.get(RECAP_GEO_CITY_COLUMN) or row.get("hotel_city") or ""
        ).strip()
        if not hotel_name and not address and not city:
            return None, None, None

        geo = geocode_hotel(hotel_name, address, city, settings=self._settings)
        if geo:
            return float(geo["lat"]), float(geo["lon"]), "nominatim"
        return None, None, None

    @staticmethod
    def _parse_coord(value: Any) -> float | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def to_meteo_input(self) -> pd.DataFrame:
        """Produit l'entrée MeteoPrep depuis la sortie RodPrep."""
        path = self.output_dir / "hotel_lookup.parquet"
        if not path.exists():
            raise FileNotFoundError("Exécuter RodPrep.run() avant to_meteo_input()")
        frame = pd.read_parquet(path)
        cols = [
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
        return frame[cols].dropna(subset=["hotel_code"]).drop_duplicates()