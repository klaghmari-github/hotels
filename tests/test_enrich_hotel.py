"""Tests enrichissement — cache feature store vs calcul frais."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rod_ia.config.settings import get_settings
from rod_ia.domain.models.simulation import EnrichedHotelFeatures
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.enrich_hotel import EnrichHotelService


@pytest.fixture
def enrich_service(tmp_path: Path) -> EnrichHotelService:
    settings = get_settings()
    registry = HotelIdentityRegistry(
        Path(__file__).resolve().parents[1] / "data/reference/hotel_identity_registry.json"
    )
    feature_store = FeatureStoreRepository(tmp_path / "feature_store")
    return EnrichHotelService(feature_store, registry, settings)


def test_enrich_returns_cache_when_already_computed(enrich_service: EnrichHotelService):
    hotel_id = "ibis-budget-nice"
    fingerprint = enrich_service._enrichment_fingerprint("Ibis budget Nice", "", "Nice")
    cached_features = EnrichedHotelFeatures(lat=43.7, lon=7.25, address_resolved="Nice")
    enrich_service.feature_store.save_enriched(hotel_id, cached_features, fingerprint=fingerprint)

    result = enrich_service.enrich("Ibis budget Nice", city="Nice")

    assert result.source == "cache"
    assert result.hotel_id == hotel_id
    assert result.features.lat == 43.7
    assert result.from_cache is True


def test_enrich_computes_when_not_in_feature_store(enrich_service: EnrichHotelService):
    geo = {"lat": 48.85, "lon": 2.35, "address_resolved": "Paris"}

    with patch.object(enrich_service, "_geocode_hotel", return_value=geo), patch.object(
        enrich_service, "_fetch_weather_12_months", return_value={"m01_temp_mean": 5.0}
    ), patch.object(enrich_service, "_fetch_poi", return_value=[]):
        result = enrich_service.enrich("Novotel Paris Tour Eiffel", city="Paris")

    assert result.source == "computed"
    assert result.features.lat == 48.85
    assert enrich_service.feature_store.has_valid_enrichment(result.hotel_id)


def test_enrich_recomputes_when_address_changes(enrich_service: EnrichHotelService):
    hotel_id = "ibis-budget-nice"
    old_fp = enrich_service._enrichment_fingerprint("Ibis budget Nice", "", "Nice")
    enrich_service.feature_store.save_enriched(
        hotel_id, EnrichedHotelFeatures(lat=43.7, lon=7.25), fingerprint=old_fp
    )

    geo = {"lat": 43.71, "lon": 7.26, "address_resolved": "Nice centre"}

    with patch.object(enrich_service, "_geocode_hotel", return_value=geo), patch.object(
        enrich_service, "_fetch_weather_12_months", return_value={}
    ), patch.object(enrich_service, "_fetch_poi", return_value=[]):
        result = enrich_service.enrich(
            "Ibis budget Nice", address="10 avenue nouvelle", city="Nice"
        )

    assert result.source == "computed"
    assert result.features.lat == 43.71


def test_force_refresh_bypasses_cache(enrich_service: EnrichHotelService):
    hotel_id = "ibis-budget-nice"
    fingerprint = enrich_service._enrichment_fingerprint("Ibis budget Nice", "", "Nice")
    enrich_service.feature_store.save_enriched(
        hotel_id, EnrichedHotelFeatures(lat=1.0, lon=2.0), fingerprint=fingerprint
    )

    geo = {"lat": 43.7, "lon": 7.25, "address_resolved": "Nice"}

    with patch.object(enrich_service, "_geocode_hotel", return_value=geo), patch.object(
        enrich_service, "_fetch_weather_12_months", return_value={}
    ), patch.object(enrich_service, "_fetch_poi", return_value=[]):
        result = enrich_service.enrich("Ibis budget Nice", city="Nice", force_refresh=True)

    assert result.source == "computed"
    assert result.features.lat == 43.7