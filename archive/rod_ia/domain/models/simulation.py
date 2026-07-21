"""Modèles de requête et résultat de simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .director_inputs import (
    ClientProfile,
    CornerInfo,
    HotelGeneralInfo,
    HotelServices,
)
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
    """Entrées hôtel — la configuration store est une SORTIE, pas une entrée obligatoire."""

    identity: HotelIdentity
    operating: HotelOperatingState
    enriched: EnrichedHotelFeatures = field(default_factory=EnrichedHotelFeatures)
    general: HotelGeneralInfo = field(default_factory=HotelGeneralInfo)
    services: HotelServices = field(default_factory=HotelServices)
    client_profile: ClientProfile = field(default_factory=ClientProfile)
    corner: CornerInfo = field(default_factory=CornerInfo)
    analyze_with_ai: bool = False
    constraints: Dict[str, object] = field(default_factory=dict)
    store: Optional[StoreConfiguration] = None

    @classmethod
    def from_dict(cls, data: dict) -> RodSimulationRequest:
        store_data = data.get("store")
        return cls(
            identity=HotelIdentity.from_dict(data.get("identity", {})),
            operating=HotelOperatingState.from_dict(
                data.get("operating", data.get("metrics", {}))
            ),
            enriched=EnrichedHotelFeatures.from_dict(data.get("enriched")),
            general=HotelGeneralInfo.from_dict(data.get("general")),
            services=HotelServices.from_dict(data.get("services")),
            client_profile=ClientProfile.from_dict(data.get("client_profile")),
            corner=CornerInfo.from_dict(data.get("corner")),
            analyze_with_ai=bool(data.get("analyze_with_ai", False)),
            constraints=dict(data.get("constraints") or {}),
            store=StoreConfiguration.from_dict(store_data) if store_data else None,
        )


@dataclass
class MonthlyProjection:
    """Projection mensuelle (CA, ventes, coûts, marges)."""

    month: int
    ca: float
    nbr_ventes: float
    margin: float = 0.0
    cost: float = 0.0
    marge_produit: float = 0.0
    marge_nette: float = 0.0


@dataclass
class SimulationResult:
    """Résultat d'une simulation pour un concept donné."""

    source: str
    concept: str
    m_lin: float
    ca_annuel: float
    nbr_ventes_annuel: float
    marge_annuelle: float
    cout_annuel: float
    roi_months: float | None
    monthly: List[MonthlyProjection]
    ca_mensuel_moyen: float = 0.0
    nbr_ventes_mensuel_moyen: float = 0.0
    store_config: Dict[str, object] = field(default_factory=dict)
    breakdown: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    trace: List[dict] = field(default_factory=list)
    pipeline: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["monthly"] = [asdict(m) for m in self.monthly]
        return payload


@dataclass
class FullSimulationResponse:
    """Comparaison SIMPLY / LIBERTY / CONNECTED + recommandation."""

    rod_by_concept: Dict[str, SimulationResult]
    ai_by_concept: Dict[str, SimulationResult]
    recommended_concept: str
    best_margin_concept: str
    recommendation_reason: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rod_by_concept": {k: v.to_dict() for k, v in self.rod_by_concept.items()},
            "ai_by_concept": {k: v.to_dict() for k, v in self.ai_by_concept.items()},
            "recommended_concept": self.recommended_concept,
            "best_margin_concept": self.best_margin_concept,
            "recommendation_reason": self.recommendation_reason,
            "warnings": self.warnings,
        }


@dataclass
class PerformanceComparisonRow:
    """Comparaison sur la période de test/évaluation (holdout, règle de 3)."""

    hotel_id: str
    hotel_name: str
    brand: str
    concept: str
    evaluation_year: int
    n_months_present: int
    months_present: List[int]
    nb_chambres: int
    taux_occupation: float
    guests_per_chambre: float
    actual_ca_period: float
    actual_ca_annualized: float
    rod_ca_period: float
    ai_ca_period: float
    rod_ca_annualized: float
    ai_ca_annualized: float
    rod_error_pct: float
    ai_error_pct: float
    rod_ca_mensuel_moyen: float
    ai_ca_mensuel_moyen: float
    actual_ca_mensuel_moyen: float
    recommended_concept: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PerformanceReport:
    """Rapport d'évaluation ROD brut vs IA sur hôtels pivots."""

    evaluation_year: int
    rows: List[PerformanceComparisonRow]
    summary: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    comparison_basis: str = "period_with_rule_of_three"

    def to_dict(self) -> dict:
        return {
            "evaluation_year": self.evaluation_year,
            "comparison_basis": self.comparison_basis,
            "rows": [r.to_dict() for r in self.rows],
            "summary": self.summary,
            "warnings": self.warnings,
        }