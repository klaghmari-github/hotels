"""Distance plage — sentinelle et géométrie."""

from rod_ia.domain.services.enrich_hotel import BEACH_MISSING_SENTINEL_M, EnrichHotelService


def test_beach_sentinel_constant():
    assert BEACH_MISSING_SENTINEL_M == 99_999.0


def test_haversine_zero_distance():
    assert EnrichHotelService._haversine_m(43.7, 7.2, 43.7, 7.2) == 0.0