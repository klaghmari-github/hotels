"""Saisies directeur d'hôtel — wizard onboarding (5 étapes)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

# Besoins clients (étape 3) → (TYPE, GAMME) catalogue ventes
CLIENT_NEED_TO_GAMME: Dict[str, Tuple[str, str]] = {
    "fb_soft_drinks": ("F&B", "SANS ALCOOL"),
    "fb_alcohol": ("F&B", "ALCOOL"),
    "fb_salty_snacks": ("F&B", "FOOD SALEE"),
    "fb_salty_meals": ("F&B", "FOOD SALEE"),
    "fb_sweet_snacks": ("F&B", "FOOD SUCREE"),
    "fb_sweet_desserts": ("F&B", "FOOD SUCREE"),
    "fb_gourmet": ("F&B", "FOOD SALEE"),
    "nfb_sos": ("NON-F&B", "SOS"),
    "nfb_hygiene": ("NON-F&B", "COSMETIQUE"),
    "nfb_cosmetics": ("NON-F&B", "COSMETIQUE"),
    "nfb_kids": ("NON-F&B", "JEUX / ENFANTS"),
    "nfb_apparel": ("NON-F&B", "PAP"),
    "nfb_accessories": ("NON-F&B", "ACCESSOIRES"),
    "nfb_souvenirs": ("NON-F&B", "SOUVENIRS"),
}

DEFAULT_CLIENT_NEEDS: Dict[str, bool] = {
    key: True for key in CLIENT_NEED_TO_GAMME
}


@dataclass
class MonthlyOccupancyRange:
    """Sliders min/max TO par mois (étape 1)."""

    min_month: int = 1
    max_month: int = 8
    min_pct: float = 0.0
    max_pct: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> MonthlyOccupancyRange:
        data = data or {}
        return cls(
            min_month=int(data.get("min_month", 1)),
            max_month=int(data.get("max_month", 8)),
            min_pct=float(data.get("min_pct", 0.0)),
            max_pct=float(data.get("max_pct", 0.0)),
        )


@dataclass
class FnBOutlet:
    count: int = 0
    name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> FnBOutlet:
        data = data or {}
        return cls(count=int(data.get("count", 0)), name=str(data.get("name", "")))


@dataclass
class LobbyEquipment:
    enabled: bool = False
    quantity: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> LobbyEquipment:
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            quantity=int(data.get("quantity", 0)),
        )


@dataclass
class HotelGeneralInfo:
    contract_signed_year: Optional[int] = None
    contract_type: str = "Franchise"
    owner: str = ""
    dom_dof: str = ""
    adults_per_room: float = 1.5
    children_per_room: float = 0.2
    panier_moyen: float = 0.0
    last_hotel_renovation: Optional[int] = None
    last_lobby_renovation: Optional[int] = None
    pms: str = "FOLS"
    monthly_occupancy: MonthlyOccupancyRange = field(
        default_factory=MonthlyOccupancyRange
    )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["monthly_occupancy"] = self.monthly_occupancy.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict | None) -> HotelGeneralInfo:
        data = data or {}
        return cls(
            contract_signed_year=data.get("contract_signed_year"),
            contract_type=str(data.get("contract_type", "Franchise")),
            owner=str(data.get("owner", "")),
            dom_dof=str(data.get("dom_dof", "")),
            adults_per_room=float(data.get("adults_per_room", 1.5)),
            children_per_room=float(data.get("children_per_room", 0.2)),
            panier_moyen=float(data.get("panier_moyen", 0.0)),
            last_hotel_renovation=data.get("last_hotel_renovation"),
            last_lobby_renovation=data.get("last_lobby_renovation"),
            pms=str(data.get("pms", "FOLS")),
            monthly_occupancy=MonthlyOccupancyRange.from_dict(
                data.get("monthly_occupancy")
            ),
        )


@dataclass
class HotelServices:
    bar: FnBOutlet = field(default_factory=FnBOutlet)
    restaurant: FnBOutlet = field(default_factory=FnBOutlet)
    room_service: bool = False
    minibar: bool = False
    minibar_rooms: int = 0
    minibar_filled: int = 0
    meeting_rooms: bool = False
    gym: bool = False
    spa: bool = False
    pool: bool = False
    other_service: bool = False
    lobby_fridge: LobbyEquipment = field(default_factory=LobbyEquipment)
    lobby_microwave: LobbyEquipment = field(default_factory=LobbyEquipment)
    lobby_water_fountain: LobbyEquipment = field(default_factory=LobbyEquipment)
    lobby_coffee_machine: LobbyEquipment = field(default_factory=LobbyEquipment)
    lobby_kettle: LobbyEquipment = field(default_factory=LobbyEquipment)
    lobby_seating: bool = False
    lobby_other: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> HotelServices:
        data = data or {}
        return cls(
            bar=FnBOutlet.from_dict(data.get("bar")),
            restaurant=FnBOutlet.from_dict(data.get("restaurant")),
            room_service=bool(data.get("room_service", False)),
            minibar=bool(data.get("minibar", False)),
            minibar_rooms=int(data.get("minibar_rooms", 0)),
            minibar_filled=int(data.get("minibar_filled", 0)),
            meeting_rooms=bool(data.get("meeting_rooms", False)),
            gym=bool(data.get("gym", False)),
            spa=bool(data.get("spa", False)),
            pool=bool(data.get("pool", False)),
            other_service=bool(data.get("other_service", False)),
            lobby_fridge=LobbyEquipment.from_dict(data.get("lobby_fridge")),
            lobby_microwave=LobbyEquipment.from_dict(data.get("lobby_microwave")),
            lobby_water_fountain=LobbyEquipment.from_dict(
                data.get("lobby_water_fountain")
            ),
            lobby_coffee_machine=LobbyEquipment.from_dict(
                data.get("lobby_coffee_machine")
            ),
            lobby_kettle=LobbyEquipment.from_dict(data.get("lobby_kettle")),
            lobby_seating=bool(data.get("lobby_seating", False)),
            lobby_other=bool(data.get("lobby_other", False)),
        )


@dataclass
class ClientProfile:
    leisure_pct: float = 30.0
    leisure_individual_pct: float = 50.0
    leisure_group_pct: float = 50.0
    business_pct: float = 70.0
    business_individual_pct: float = 50.0
    business_group_pct: float = 50.0
    national_pct: float = 60.0
    international_pct: float = 40.0
    client_needs: Dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_CLIENT_NEEDS)
    )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> ClientProfile:
        data = data or {}
        needs = dict(DEFAULT_CLIENT_NEEDS)
        needs.update(data.get("client_needs") or {})
        return cls(
            leisure_pct=float(data.get("leisure_pct", 30.0)),
            leisure_individual_pct=float(data.get("leisure_individual_pct", 50.0)),
            leisure_group_pct=float(data.get("leisure_group_pct", 50.0)),
            business_pct=float(data.get("business_pct", 70.0)),
            business_individual_pct=float(data.get("business_individual_pct", 50.0)),
            business_group_pct=float(data.get("business_group_pct", 50.0)),
            national_pct=float(data.get("national_pct", 60.0)),
            international_pct=float(data.get("international_pct", 40.0)),
            client_needs=needs,
        )


@dataclass
class CornerInfo:
    has_existing_corner: bool = False
    m_lin: Optional[float] = None
    emplacement: str = "EMPLACEMENT #1"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> CornerInfo:
        data = data or {}
        m_lin_raw = data.get("m_lin")
        return cls(
            has_existing_corner=bool(data.get("has_existing_corner", False)),
            m_lin=float(m_lin_raw) if m_lin_raw is not None else None,
            emplacement=str(data.get("emplacement", "EMPLACEMENT #1")),
        )


def excluded_gammes_from_needs(client_needs: Dict[str, bool]) -> List[str]:
    """Gammes à exclure quand le toggle besoin client est désactivé."""
    excluded: list[str] = []
    for key, enabled in client_needs.items():
        if enabled:
            continue
        mapping = CLIENT_NEED_TO_GAMME.get(key)
        if mapping and mapping[1] not in excluded:
            excluded.append(mapping[1])
    return excluded


def mix_from_client_needs(
    client_needs: Dict[str, bool],
    *,
    default_fb: float = 0.7,
    default_nf: float = 0.3,
) -> tuple[float, float]:
    """Déduit le mix F&B / NON-F&B à partir des besoins activés."""
    fb_on = sum(
        1
        for key, enabled in client_needs.items()
        if enabled and key.startswith("fb_")
    )
    nfb_on = sum(
        1
        for key, enabled in client_needs.items()
        if enabled and key.startswith("nfb_")
    )
    total = fb_on + nfb_on
    if total <= 0:
        return default_fb, default_nf
    fb_share = fb_on / total
    return fb_share, 1.0 - fb_share