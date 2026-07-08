"""RodPrep — extraction et nettoyage du récapitulatif Excel ROD."""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.rod_recap_extractor import RodRecapExtractor


class RodPrep:
    """Prépare la table hôtel (code, nom, marque, coordonnées) depuis le récap Excel."""

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        registry_path: Path | None = None,
    ) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        settings = get_settings()
        self.registry_path = Path(registry_path or settings.identity_registry_path)
        self._registry = HotelIdentityRegistry(self.registry_path)

    def resolve_recap_path(self) -> Path:
        explicit = self.input_dir / "recapitulatif_rod.xlsx"
        if explicit.exists():
            return explicit
        for path in sorted(self.input_dir.glob("*.xlsx")):
            return path
        settings = get_settings()
        recap = settings.rod_recap_path
        if recap and recap.exists():
            return recap
        raise FileNotFoundError(
            f"Aucun Excel récap dans {self.input_dir} — copier le fichier dans Input/"
        )

    def seed_input_from_sources(self) -> Path:
        """Copie l'Excel récap depuis sources/raw vers Input si absent."""
        settings = get_settings()
        recap = settings.rod_recap_path
        if not recap or not recap.exists():
            raise FileNotFoundError("Récap Excel introuvable dans sources/raw")
        self.input_dir.mkdir(parents=True, exist_ok=True)
        target = self.input_dir / "recapitulatif_rod.xlsx"
        if not target.exists():
            shutil.copy2(recap, target)
        return target

    def run(self) -> pd.DataFrame:
        recap_path = self.resolve_recap_path()
        extractor = RodRecapExtractor(
            recap_path=recap_path,
            identity_registry=self._registry,
            output_path=self.output_dir / "rod_recap",
        )
        wide = extractor.extract_wide()
        lookup = self._build_hotel_lookup(wide)
        wide.to_parquet(self.output_dir / "rod_features.parquet", index=False)
        wide.to_csv(self.output_dir / "rod_features.csv", index=False)
        lookup.to_parquet(self.output_dir / "hotel_lookup.parquet", index=False)
        lookup.to_csv(self.output_dir / "hotel_lookup.csv", index=False)
        return lookup

    def _build_hotel_lookup(self, wide: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict] = []
        for record in self._registry.all_records():
            rows.append(
                {
                    "hotel_code": record.hotel_id,
                    "hotel_name": record.name_display or record.name_ventes or record.hotel_id,
                    "nom_hotel": record.name_ventes or record.name_display or record.hotel_id,
                    "hotel_brand": record.brand,
                    "hotel_city": record.city,
                    "hotel_lat": record.lat_nominatim or record.lat_canonical,
                    "hotel_lon": record.lon_nominatim or record.lon_canonical,
                    "nb_chambres": record.nb_chambres,
                }
            )
        lookup = pd.DataFrame(rows)
        if not wide.empty and "hotel_id" in wide.columns:
            recap_cols = [c for c in wide.columns if c != "hotel_id"]
            recap_part = wide.rename(columns={"hotel_id": "hotel_code"})
            lookup = lookup.merge(recap_part, on="hotel_code", how="left")
        return lookup

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
        return frame[cols].drop_duplicates()