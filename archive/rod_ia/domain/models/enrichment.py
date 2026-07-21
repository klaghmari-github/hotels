"""Résultat d'enrichissement POI / météo."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from .simulation import EnrichedHotelFeatures

EnrichSource = Literal["cache", "computed", "failed"]


@dataclass
class EnrichResult:
    """Réponse structurée du service d'enrichissement.

    ``source`` indique si les données viennent du feature store (cache)
    ou d'un calcul frais (géocode + météo + POI).
    """

    hotel_id: str
    features: EnrichedHotelFeatures
    source: EnrichSource
    warnings: list[str] = field(default_factory=list)
    cached_at: str | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["features"] = self.features.to_dict()
        return payload

    @property
    def from_cache(self) -> bool:
        return self.source == "cache"