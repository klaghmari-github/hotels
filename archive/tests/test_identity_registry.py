from pathlib import Path

from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry


def test_resolve_ventes_name_to_hotel_id():
    registry = HotelIdentityRegistry(
        Path(__file__).resolve().parents[1] / "data/reference/hotel_identity_registry.json"
    )
    hotel_id = registry.resolve("ventes", "Ibis budget Nice")
    assert hotel_id == "ibis-budget-nice"


def test_resolve_rod_name_differs_from_ventes():
    registry = HotelIdentityRegistry(
        Path(__file__).resolve().parents[1] / "data/reference/hotel_identity_registry.json"
    )
    hotel_id = registry.resolve("rod", "Paris Centre Tour Eiffel")
    assert hotel_id == "novotel-paris-tour-eiffel"