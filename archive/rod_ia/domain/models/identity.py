"""Modèles du registre d'identité hôtel (clé canonique de jointure)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass(frozen=True)
class GeoCoordinates:
    """Coordonnées géographiques avec source de provenance."""

    lat: float
    lon: float
    source: str = "unknown"

    def rounded(self, decimals: int = 5) -> tuple[float, float]:
        return round(self.lat, decimals), round(self.lon, decimals)


@dataclass
class HotelRecord:
    """Entrée du registre d'identité — relie toutes les sources à un ``hotel_id``."""

    hotel_id: str
    brand: str
    city: str
    name_display: str
    name_ventes: Optional[str] = None
    name_rod: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    lat_canonical: Optional[float] = None
    lon_canonical: Optional[float] = None
    geo_source: str = "manual"
    lat_rod: Optional[float] = None
    lon_rod: Optional[float] = None
    lat_nominatim: Optional[float] = None
    lon_nominatim: Optional[float] = None
    has_sales: bool = False
    has_rod: bool = False
    nb_chambres: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> HotelRecord:
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})

    def canonical_coords(self) -> Optional[GeoCoordinates]:
        if self.lat_canonical is not None and self.lon_canonical is not None:
            return GeoCoordinates(self.lat_canonical, self.lon_canonical, self.geo_source)
        return None