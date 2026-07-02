"""Configuration centralisée du projet ROD-IA."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Chemins et constantes applicatives (immutable)."""

    project_root: Path
    sources_raw_dir: Path
    data_reference_dir: Path
    data_processed_dir: Path
    feature_store_dir: Path
    artifacts_dir: Path
    web_dir: Path

    default_poi_radii_km: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5)
    default_country: str = "France"
    geo_match_tolerance_m: float = 200.0
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    user_agent: str = "accor-rod-ia/0.1"

    @property
    def sales_csv_path(self) -> Path:
        return self.sources_raw_dir / "001.queryVentes.csv"

    @property
    def identity_registry_path(self) -> Path:
        return self.data_reference_dir / "hotel_identity_registry.json"

    @property
    def rod_reference_path(self) -> Path:
        extracted = self.data_reference_dir / "rod_reference.json"
        if extracted.exists():
            return extracted
        return self.data_reference_dir / "rod_reference_demo.json"

    @property
    def brand_projections_path(self) -> Path:
        return self.data_reference_dir / "brand_projections.json"

    @property
    def performance_report_path(self) -> Path:
        return self.data_processed_dir / "performance_report.json"

    @property
    def column_manifest_path(self) -> Path:
        return self.data_processed_dir / "column_manifest.json"

    @property
    def rod_recap_path(self) -> Path | None:
        """Fichier « Récapitulatif … ROD » dans ``sources/raw`` (si présent)."""
        for path in self.sources_raw_dir.iterdir():
            name = path.name.lower()
            if "capitulatif" in name or "recap" in name:
                if path.suffix.lower() in {".xlsx", ".xlsm"}:
                    return path
        return None

    @property
    def rod_recap_reference_dir(self) -> Path:
        return self.data_reference_dir / "rod_recap"


@lru_cache(maxsize=1)
def get_settings(project_root: str | Path | None = None) -> Settings:
    """Retourne la configuration singleton (racine = parent de ``rod_ia/``)."""
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    return Settings(
        project_root=root,
        sources_raw_dir=root / "sources" / "raw",
        data_reference_dir=root / "data" / "reference",
        data_processed_dir=root / "data" / "processed",
        feature_store_dir=root / "rod_ia" / "feature_store" / "hotels",
        artifacts_dir=root / "rod_ia" / "artifacts",
        web_dir=root / "rod_ia" / "web",
    )