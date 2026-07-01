from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List
from .hotel import HotelIdentity, HotelOperatingState
from .store import StoreConfiguration

@dataclass
class EnrichedHotelFeatures:
    lat: float | None = None
    lon: float | None = None
    address_resolved: str = ""
    poi: Dict[str, float] = field(default_factory=dict)
    weather_monthly: Dict[str, float] = field(default_factory=dict)
    nearest: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "EnrichedHotelFeatures":
        data = data or {}
        return cls(
            lat=data.get("lat"),
            lon=data.get("lon"),
            address_resolved=data.get("address_resolved", data.get("address", "")),
            poi=data.get("poi", {}),
            weather_monthly=data.get("weather_monthly", data.get("weather", {})),
            nearest=data.get("nearest", {}),
        )

@dataclass
class RodSimulationRequest:
    identity: HotelIdentity
    operating: HotelOperatingState
    store: StoreConfiguration
    enriched: EnrichedHotelFeatures = field(default_factory=EnrichedHotelFeatures)

    @classmethod
    def from_dict(cls, data: dict) -> "RodSimulationRequest":
        return cls(
            identity=HotelIdentity.from_dict(data.get("identity", {})),
            operating=HotelOperatingState.from_dict(data.get("operating", data.get("metrics", {}))),
            store=StoreConfiguration.from_dict(data.get("store", {})),
            enriched=EnrichedHotelFeatures.from_dict(data.get("enriched")),
        )

@dataclass
class MonthlyProjection:
    month: int
    ca: float
    nbr_ventes: float
    margin: float = 0.0
    cost: float = 0.0

@dataclass
class SimulationResult:
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
        d = asdict(self)
        d["monthly"] = [asdict(m) for m in self.monthly]
        return d
