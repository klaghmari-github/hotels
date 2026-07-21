"""Tests ProximityPrep — identité RodPrep, coords prioritaires, pas de nom-as-code."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from prepare.proximity_prep import HOTEL_IDENTITY_COLS, ProximityPrep, as_coord
from rod_ia.domain.models.enrichment import EnrichResult
from rod_ia.domain.models.simulation import EnrichedHotelFeatures


@pytest.fixture
def prox_dirs(tmp_path: Path) -> tuple[Path, Path]:
    input_dir = tmp_path / "Input"
    output_dir = tmp_path / "Output"
    input_dir.mkdir()
    output_dir.mkdir()
    return input_dir, output_dir


def _mock_enrich(
    *,
    lat: float = 43.69,
    lon: float = 7.24,
    source: str = "computed",
    poi: dict | None = None,
    nearest: dict | None = None,
) -> MagicMock:
    features = EnrichedHotelFeatures(
        lat=lat,
        lon=lon,
        poi=poi
        or {
            "d_poi_fb_0_0_1km": 2.0,
            "d_poi_fb_0_0_5km": 10.0,
            "d_poi_not_fb_0_0_1km": 1.0,
            "d_poi_not_fb_0_0_5km": 4.0,
        },
        nearest=nearest
        or {
            "d_nearest_beach_km": 0.15,
            "d_nearest_beach_m": 150.0,
            "d_nearest_bakery_m": 40.0,
        },
    )
    enrich = MagicMock()
    enrich.enrich.return_value = EnrichResult(
        hotel_id="H2075",
        features=features,
        source=source,
        warnings=[],
    )
    return enrich


def test_as_coord_invalid():
    assert as_coord(None) is None
    assert as_coord(float("nan")) is None
    assert as_coord("x") is None
    assert as_coord("43.5") == pytest.approx(43.5)


def test_fill_input_from_rod_keeps_accor_codes_and_coords(prox_dirs, tmp_path: Path):
    input_dir, output_dir = prox_dirs
    rod_out = tmp_path / "rod"
    rod_out.mkdir()
    lookup = pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "hotel_name": "Ibis budget Nice Californie",
                "nom_hotel": "Ibis budget Nice",
                "hotel_brand": "IBIS BUDGET",
                "hotel_city": "Nice",
                "hotel_lat": 43.689186,
                "hotel_lon": 7.240512,
                "d_recap_foo": 1,
            },
            {
                "hotel_code": None,
                "hotel_name": "Novotel Porte d'Italie",
                "nom_hotel": "Novotel Porte d'Italie",
                "hotel_brand": "NOVOTEL",
                "hotel_city": "Paris",
                "hotel_lat": None,
                "hotel_lon": None,
                "d_recap_foo": 0,
            },
            {
                "hotel_code": "HB6A3",
                "hotel_name": "Ibis budget Strasbourg",
                "nom_hotel": "Ibis budget Strasbourg Centre République",
                "hotel_brand": "IBIS BUDGET",
                "hotel_city": "Strasbourg",
                "hotel_lat": 48.591522,
                "hotel_lon": 7.754599,
                "d_recap_foo": 2,
            },
        ]
    )
    lookup.to_parquet(rod_out / "hotel_lookup.parquet", index=False)

    prep = ProximityPrep(input_dir, output_dir, enrich=_mock_enrich())
    path = prep.fill_input_from_rod(rod_out)
    frame = pd.read_parquet(path)

    assert list(frame.columns) == [c for c in HOTEL_IDENTITY_COLS if c in frame.columns]
    assert "d_recap_foo" not in frame.columns
    assert set(frame["hotel_code"]) == {"H2075", "HB6A3"}
    assert frame["hotel_lat"].notna().all()
    assert not frame["hotel_code"].str.contains("-", regex=False).any()
    assert "Ibis" not in " ".join(frame["hotel_code"].tolist())


def test_run_passes_lat_lon_and_accor_code(prox_dirs):
    input_dir, output_dir = prox_dirs
    hotels = pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "hotel_name": "Ibis budget Nice Californie",
                "hotel_brand": "IBIS BUDGET",
                "hotel_city": "Nice",
                "hotel_lat": 43.689186,
                "hotel_lon": 7.240512,
            }
        ]
    )
    hotels.to_parquet(input_dir / "hotels.parquet", index=False)

    enrich = _mock_enrich()
    prep = ProximityPrep(input_dir, output_dir, enrich=enrich)
    frame = prep.run()

    assert len(frame) == 1
    assert frame.loc[0, "hotel_code"] == "H2075"
    assert frame.loc[0, "geo_source"] == "rod_coords"
    assert frame.loc[0, "commerce_fb_100m"] == 2.0
    assert frame.loc[0, "plage_distance_km"] == pytest.approx(0.15)
    assert frame.loc[0, "distance_beach_m"] == pytest.approx(150.0)
    assert frame.loc[0, "distance_bakery_m"] == pytest.approx(40.0)

    kwargs = enrich.enrich.call_args.kwargs
    assert kwargs["hotel_id"] == "H2075"
    assert kwargs["lat"] == pytest.approx(43.689186)
    assert kwargs["lon"] == pytest.approx(7.240512)
    assert kwargs["hotel_name"] == "Ibis budget Nice Californie"


def test_run_fallback_geocode_when_coords_missing(prox_dirs):
    input_dir, output_dir = prox_dirs
    hotels = pd.DataFrame(
        [
            {
                "hotel_code": "H9999",
                "hotel_name": "Hotel Sans Coords",
                "hotel_city": "Lyon",
                "hotel_lat": None,
                "hotel_lon": None,
            }
        ]
    )
    hotels.to_parquet(input_dir / "hotels.parquet", index=False)

    enrich = _mock_enrich(lat=45.75, lon=4.85)
    prep = ProximityPrep(input_dir, output_dir, enrich=enrich)
    frame = prep.run()

    assert frame.loc[0, "hotel_code"] == "H9999"
    assert frame.loc[0, "geo_source"] == "name_geocode"
    kwargs = enrich.enrich.call_args.kwargs
    assert kwargs["lat"] is None
    assert kwargs["lon"] is None
    assert kwargs["hotel_name"] == "Hotel Sans Coords"


def test_run_writes_output_files(prox_dirs):
    input_dir, output_dir = prox_dirs
    pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "hotel_name": "Nice",
                "hotel_city": "Nice",
                "hotel_lat": 43.7,
                "hotel_lon": 7.2,
            }
        ]
    ).to_parquet(input_dir / "hotels.parquet", index=False)

    prep = ProximityPrep(input_dir, output_dir, enrich=_mock_enrich())
    prep.run()
    assert (output_dir / "proximity.parquet").exists()
    assert (output_dir / "proximity.csv").exists()
