"""
Modèles métier de la saisie directeur et des résultats de simulation.

Les structures sont volontairement plates / sérialisables JSON pour l'API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Identité & exploitation
# ---------------------------------------------------------------------------


@dataclass
class HotelIdentity:
    """Identité minimale — saisie user ou préremplie depuis hotel_data admin."""

    hotel_code: str = ""
    hotel_name: str = ""
    hotel_brand: str = ""
    hotel_lat: float | None = None
    hotel_lon: float | None = None
    hotel_adresse_postale_1: str = ""
    hotel_adresse_postale_2: str = ""
    hotel_code_postal: str = ""
    hotel_city: str = ""

    def address_line(self) -> str:
        parts = [
            self.hotel_adresse_postale_1,
            self.hotel_adresse_postale_2,
            f"{self.hotel_code_postal} {self.hotel_city}".strip(),
        ]
        return ", ".join(p for p in parts if p and str(p).strip())

    def has_coords(self) -> bool:
        try:
            return self.hotel_lat is not None and self.hotel_lon is not None
        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> HotelIdentity:
        data = data or {}
        lat = data.get("hotel_lat", data.get("lat"))
        lon = data.get("hotel_lon", data.get("lon"))
        return cls(
            hotel_code=str(data.get("hotel_code") or data.get("hotel_id") or "").strip(),
            hotel_name=str(data.get("hotel_name") or "").strip(),
            hotel_brand=str(data.get("hotel_brand") or data.get("brand") or "").strip(),
            hotel_lat=float(lat) if lat not in (None, "") else None,
            hotel_lon=float(lon) if lon not in (None, "") else None,
            hotel_adresse_postale_1=str(
                data.get("hotel_adresse_postale_1") or data.get("address") or ""
            ).strip(),
            hotel_adresse_postale_2=str(data.get("hotel_adresse_postale_2") or "").strip(),
            hotel_code_postal=str(data.get("hotel_code_postal") or "").strip(),
            hotel_city=str(data.get("hotel_city") or data.get("city") or "").strip(),
        )


class HotelOperating:
    """
    État opérationnel avec grandeurs dérivées.

    * clients/jour  = nb_chambres × TO × guests_per_chambre
    * clients/mois  = clients/jour × 30.5
    """

    JOURS_MOIS = 30.5

    def __init__(
        self,
        nb_chambres: int = 80,
        taux_occupation: float = 0.65,
        guests_per_chambre: float = 1.7,
    ) -> None:
        self.nb_chambres = max(int(nb_chambres), 0)
        to = float(taux_occupation)
        if to > 1.0:
            to /= 100.0
        self.taux_occupation = min(max(to, 0.0), 1.0)
        self.guests_per_chambre = max(float(guests_per_chambre), 0.0)

    @property
    def clients_jour(self) -> float:
        return self.nb_chambres * self.taux_occupation * self.guests_per_chambre

    @property
    def clients_mois(self) -> float:
        return self.clients_jour * self.JOURS_MOIS

    def to_dict(self) -> dict[str, Any]:
        return {
            "nb_chambres": self.nb_chambres,
            "taux_occupation": self.taux_occupation,
            "guests_per_chambre": self.guests_per_chambre,
            "clients_jour": self.clients_jour,
            "clients_mois": self.clients_mois,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> HotelOperating:
        data = data or {}
        guests = data.get("guests_per_chambre")
        if guests is None:
            adults = float(data.get("adults_per_room") or 0)
            children = float(data.get("children_per_room") or 0)
            guests = (adults + children) if (adults or children) else 1.7
        return cls(
            nb_chambres=int(data.get("nb_chambres") or data.get("hotel_nb_chambres") or 80),
            taux_occupation=float(
                data.get("taux_occupation") or data.get("hotel_to_annuel") or 0.65
            ),
            guests_per_chambre=float(guests),
        )


# ---------------------------------------------------------------------------
# Saisie wizard (services, profil, corner)
# ---------------------------------------------------------------------------


@dataclass
class HotelServices:
    bar: bool = False
    restaurant: bool = False
    room_service: bool = False
    minibar: bool = False
    meeting_rooms: bool = False
    gym: bool = False
    spa: bool = False
    pool: bool = False
    lobby_fridge: bool = False
    lobby_microwave: bool = False
    lobby_water: bool = False
    lobby_coffee: bool = False
    lobby_kettle: bool = False
    lobby_seating: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> HotelServices:
        data = data or {}
        known = set(cls.__dataclass_fields__.keys())
        return cls(**{k: bool(data.get(k, False)) for k in known})


# Clés besoins clients alignées sur les coefficients Règle 3 Excel
DEFAULT_CLIENT_NEEDS: dict[str, bool] = {
    "fb_soft_drinks": True,
    "fb_alcohol": False,
    "fb_salty_snacks": False,
    "fb_salty_meals": True,
    "fb_sweet_snacks": True,
    "fb_sweet_desserts": True,
    "fb_gourmet": True,
    "nfb_sos": True,
    "nfb_hygiene": False,
    "nfb_cosmetics": True,
    "nfb_kids": True,
    "nfb_apparel": True,
    "nfb_accessories": True,
    "nfb_souvenirs": True,
}


@dataclass
class ClientProfile:
    loisirs_pct: float = 0.30
    affaires_pct: float = 0.70
    national_pct: float = 0.60
    international_pct: float = 0.40
    client_needs: dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_CLIENT_NEEDS)
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> ClientProfile:
        data = data or {}
        needs = dict(DEFAULT_CLIENT_NEEDS)
        raw = data.get("client_needs") or {}
        for k, v in raw.items():
            needs[str(k)] = bool(v)
        return cls(
            loisirs_pct=float(data.get("loisirs_pct", 0.30)),
            affaires_pct=float(data.get("affaires_pct", 0.70)),
            national_pct=float(data.get("national_pct", 0.60)),
            international_pct=float(data.get("international_pct", 0.40)),
            client_needs=needs,
        )


@dataclass
class CornerInfo:
    """Boutique / corner actuel + mètres linéaires souhaités."""

    has_corner: bool = False
    m_lin: float | None = None  # None → défaut pilote concept
    mix_fb: float | None = None  # None → défaut pilote concept

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> CornerInfo:
        data = data or {}
        m = data.get("m_lin")
        fb = data.get("mix_fb", data.get("fb_share"))
        return cls(
            has_corner=bool(data.get("has_corner", False)),
            m_lin=float(m) if m not in (None, "") else None,
            mix_fb=float(fb) if fb not in (None, "") else None,
        )


@dataclass
class StoreConfig:
    """Configuration retail **sortie** du simulateur pour un concept."""

    concept: str
    m_lin: float
    mix_fb: float
    mix_nf: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Enrichissement & requête complète
# ---------------------------------------------------------------------------


@dataclass
class EnrichedFeatures:
    """Features calculées (pas saisies) — météo, proximité, holidays, géocode."""

    lat: float | None = None
    lon: float | None = None
    address_resolved: str = ""
    geocode_source: str = ""
    weather: dict[str, float] = field(default_factory=dict)
    proximity: dict[str, float] = field(default_factory=dict)
    holidays: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationRequest:
    """Payload complet du wizard user → moteur de simulation."""

    identity: HotelIdentity = field(default_factory=HotelIdentity)
    operating: HotelOperating = field(default_factory=HotelOperating)
    services: HotelServices = field(default_factory=HotelServices)
    client_profile: ClientProfile = field(default_factory=ClientProfile)
    corner: CornerInfo = field(default_factory=CornerInfo)
    enriched: EnrichedFeatures = field(default_factory=EnrichedFeatures)
    # store rempli par l'orchestrateur par concept
    store: StoreConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "operating": self.operating.to_dict(),
            "services": self.services.to_dict(),
            "client_profile": self.client_profile.to_dict(),
            "corner": self.corner.to_dict(),
            "enriched": self.enriched.to_dict(),
            "store": self.store.to_dict() if self.store else None,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> SimulationRequest:
        data = data or {}
        op_data = data.get("operating") or data.get("metrics") or {}
        # allow flat fields at root
        if "nb_chambres" in data and "nb_chambres" not in op_data:
            op_data = {**op_data, **{k: data[k] for k in (
                "nb_chambres", "taux_occupation", "guests_per_chambre",
                "adults_per_room", "children_per_room", "hotel_nb_chambres",
                "hotel_to_annuel",
            ) if k in data}}
        return cls(
            identity=HotelIdentity.from_dict(data.get("identity") or data),
            operating=HotelOperating.from_dict(op_data),
            services=HotelServices.from_dict(data.get("services")),
            client_profile=ClientProfile.from_dict(data.get("client_profile")),
            corner=CornerInfo.from_dict(data.get("corner")),
            enriched=EnrichedFeatures(**{
                k: v for k, v in (data.get("enriched") or {}).items()
                if k in EnrichedFeatures.__dataclass_fields__
            }) if data.get("enriched") else EnrichedFeatures(),
        )


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------


@dataclass
class RevenueResult:
    """Sortie pure du moteur de revenus (sans coûts)."""

    concept: str
    ca_ht_mensuel: float
    ca_fb_mensuel: float
    ca_nf_mensuel: float
    nbr_ventes_mensuel: float
    marge_produit_mensuelle: float
    breakdown: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CostResult:
    """Sortie pure du moteur de coûts (sans revenus)."""

    concept: str
    monthly_cost: float
    annual_cost: float
    capex: float
    techno_monthly: float
    annexes_monthly: float
    agencement_monthly: float
    cost_lines: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConceptSimulation:
    """Agrégation revenus + coûts + marge pour un concept."""

    source: str  # ROD_RULES | AI (futur)
    concept: str
    store: dict[str, Any]
    ca_mensuel: float
    ca_annuel: float
    ventes_mensuel: float
    ventes_annuel: float
    marge_produit_mensuelle: float
    marge_produit_annuelle: float
    cout_mensuel: float
    cout_annuel: float
    marge_nette_mensuelle: float
    marge_nette_annuelle: float
    capex: float
    roi_months: float | None
    revenue: dict[str, Any] = field(default_factory=dict)
    costs: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FullSimulation:
    """Comparaison multi-concepts + recommandation."""

    by_concept: dict[str, ConceptSimulation]
    recommended_concept: str
    best_margin_concept: str
    recommendation_reason: str
    allowed_concepts: list[str]
    warnings: list[str] = field(default_factory=list)
    enriched: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_concept": {k: v.to_dict() for k, v in self.by_concept.items()},
            "recommended_concept": self.recommended_concept,
            "best_margin_concept": self.best_margin_concept,
            "recommendation_reason": self.recommendation_reason,
            "allowed_concepts": self.allowed_concepts,
            "warnings": self.warnings,
            "enriched": self.enriched,
        }
