"""Modèles de requête et résultat de simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List

from .hotel import HotelIdentity, HotelOperatingState
from .store import StoreConfiguration


@dataclass
class EnrichedHotelFeatures:
    """Features enrichies (géo, POI, météo) — persistées dans le feature store."""

    lat: float | None = None
    lon: float | None = None
    address_resolved: str = ""
    poi: Dict[str, float] = field(default_factory=dict)
    weather_monthly: Dict[str, float] = field(default_factory=dict)
    nearest: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> EnrichedHotelFeatures:
        data = data or {}
        return cls(
            lat=data.get("lat"),
            lon=data.get("lon"),
            address_resolved=data.get("address_resolved", data.get("address", "")),
            poi=dict(data.get("poi") or {}),
            weather_monthly=dict(data.get("weather_monthly") or data.get("weather") or {}),
            nearest={k: v for k, v in (data.get("nearest") or {}).items() if v is not None},
        )


@dataclass
class RodSimulationRequest:
    """Payload complet pour simulateur ROD et prédicteur IA."""

    identity: HotelIdentity
    operating: HotelOperatingState
    store: StoreConfiguration
    enriched: EnrichedHotelFeatures = field(default_factory=EnrichedHotelFeatures)

    @classmethod
    def from_dict(cls, data: dict) -> RodSimulationRequest:
        return cls(
            identity=HotelIdentity.from_dict(data.get("identity", {})),
            operating=HotelOperatingState.from_dict(
                data.get("operating", data.get("metrics", {}))
            ),
            store=StoreConfiguration.from_dict(data.get("store", {})),
            enriched=EnrichedHotelFeatures.from_dict(data.get("enriched")),
        )


@dataclass
class MonthlyProjection:
    """Projection mensuelle (CA, ventes, coûts, marge)."""

    month: int
    ca: float
    nbr_ventes: float
    margin: float = 0.0
    cost: float = 0.0


@dataclass
class SimulationResult:
    """Résultat agrégé d'une simulation (ROD, IA ou optimiseur)."""

    source: str
    concept: str
    m_lin: float
    ca_annuel: float
    nbr_ventes_annuel: float
    marge_annuelle: float
    cout_annuel: float
    roi_months: float | None
    monthly: List[MonthlyProjection]
    breakdown: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    trace: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["monthly"] = [asdict(m) for m in self.monthly]
        return payload