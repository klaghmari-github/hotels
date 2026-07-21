"""Tests ProximityPrep — commerces 100–500 m, plage 1–5 km, codes Accor."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from prepare.proximity_prep import (
    BEACH_RADII_KM,
    COMMERCE_RADII_M,
    HOTEL_IDENTITY_COLS,
    ProximityFeatures,
    ProximityPrep,
    as_coord,
    beach_presence_flags,
    count_commerce_by_category,
    empty_proximity_features,
)


@pytest.fixture
def prox_dirs(tmp_path: Path) -> tuple[Path, Path]:
    input_dir = tmp_path / "Input"
    output_dir = tmp_path / "Output"
    input_dir.mkdir()
    output_dir.mkdir()
    return input_dir, output_dir


def test_as_coord_invalid():
    assert as_coord(None) is None
    assert as_coord(float("nan")) is None
    assert as_coord("x") is None
    assert as_coord("43.5") == pytest.approx(43.5)


def test_count_commerce_by_category_cumulative_radii():
    shops = [
        {"shop": "bakery", "distance_m": 50},
        {"shop": "bakery", "distance_m": 150},
        {"shop": "convenience", "distance_m": 250},
        {"shop": "pharmacy", "distance_m": 450},
        {"shop": "supermarket", "distance_m": 600},  # hors 500 m
    ]
    feats = count_commerce_by_category(shops)

    assert feats["commerce_bakery_100m"] == 1
    assert feats["commerce_bakery_200m"] == 2
    assert feats["commerce_bakery_500m"] == 2
    assert feats["commerce_convenience_100m"] == 0
    assert feats["commerce_convenience_300m"] == 1
    assert feats["commerce_pharmacy_400m"] == 0
    assert feats["commerce_pharmacy_500m"] == 1
    assert feats["commerce_supermarket_500m"] == 0  # > 500

    # Agrégats F&B / non-F&B
    assert feats["commerce_fb_100m"] == 1  # bakery 50
    assert feats["commerce_fb_300m"] == 3  # 2 bakery + convenience
    assert feats["commerce_non_fb_500m"] == 1  # pharmacy


def test_beach_presence_flags_by_km():
    # Plage à 1.5 km
    feats = beach_presence_flags([1500.0])
    assert feats["plage_1km"] == 0.0
    assert feats["plage_2km"] == 1.0
    assert feats["plage_3km"] == 1.0
    assert feats["plage_5km"] == 1.0
    assert feats["plage_distance_km"] == pytest.approx(1.5)

    empty = beach_presence_flags([])
    assert all(empty[f"plage_{k}km"] == 0.0 for k in BEACH_RADII_KM)
    assert pd.isna(empty["plage_distance_km"])


def test_empty_features_has_all_expected_columns():
    feats = empty_proximity_features()
    for r in COMMERCE_RADII_M:
        assert f"commerce_fb_{r}m" in feats
        assert f"commerce_non_fb_{r}m" in feats
        assert f"commerce_bakery_{r}m" in feats
    for k in BEACH_RADII_KM:
        assert f"plage_{k}km" in feats
    assert "plage_distance_km" in feats


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
                "hotel_city": "Paris",
                "hotel_lat": None,
                "hotel_lon": None,
            },
            {
                "hotel_code": "HB6A3",
                "hotel_name": "Ibis budget Strasbourg",
                "hotel_city": "Strasbourg",
                "hotel_lat": 48.591522,
                "hotel_lon": 7.754599,
            },
        ]
    )
    lookup.to_parquet(rod_out / "hotel_lookup.parquet", index=False)

    prep = ProximityPrep(
        input_dir,
        output_dir,
        features=ProximityFeatures(
            fetch_shops=lambda lat, lon: [],
            fetch_beaches=lambda lat, lon: [],
        ),
    )
    path = prep.fill_input_from_rod(rod_out)
    frame = pd.read_parquet(path)

    assert list(frame.columns) == [c for c in HOTEL_IDENTITY_COLS if c in frame.columns]
    assert "d_recap_foo" not in frame.columns
    assert set(frame["hotel_code"]) == {"H2075", "HB6A3"}
    assert frame["hotel_lat"].notna().all()


def test_run_uses_coords_and_outputs_full_grid(prox_dirs):
    input_dir, output_dir = prox_dirs
    hotels = pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "hotel_name": "Ibis budget Nice Californie",
                "hotel_city": "Nice",
                "hotel_lat": 43.689186,
                "hotel_lon": 7.240512,
            }
        ]
    )
    hotels.to_parquet(input_dir / "hotels.parquet", index=False)

    def fake_shops(lat, lon):
        assert lat == pytest.approx(43.689186)
        assert lon == pytest.approx(7.240512)
        return [
            {"shop": "bakery", "distance_m": 80},
            {"shop": "convenience", "distance_m": 220},
            {"shop": "gift", "distance_m": 350},
        ]

    def fake_beaches(lat, lon):
        return [3200.0]  # 3.2 km

    prep = ProximityPrep(
        input_dir,
        output_dir,
        features=ProximityFeatures(
            fetch_shops=fake_shops,
            fetch_beaches=fake_beaches,
        ),
    )
    frame = prep.run()

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["hotel_code"] == "H2075"
    assert row["geo_source"] == "rod_coords"

    # Commerces par catégorie / rayon
    assert row["commerce_bakery_100m"] == 1
    assert row["commerce_bakery_500m"] == 1
    assert row["commerce_convenience_100m"] == 0
    assert row["commerce_convenience_300m"] == 1
    assert row["commerce_gift_400m"] == 1
    assert row["commerce_fb_100m"] == 1
    assert row["commerce_fb_300m"] == 2
    assert row["commerce_non_fb_500m"] == 1

    # Plage 1–5 km
    assert row["plage_1km"] == 0
    assert row["plage_2km"] == 0
    assert row["plage_3km"] == 0
    assert row["plage_4km"] == 1
    assert row["plage_5km"] == 1
    assert row["plage_distance_km"] == pytest.approx(3.2)

    # Toutes les colonnes rayon présentes
    for r in COMMERCE_RADII_M:
        assert f"commerce_fb_{r}m" in frame.columns
    for k in BEACH_RADII_KM:
        assert f"plage_{k}km" in frame.columns

    assert (output_dir / "proximity.parquet").exists()


def test_run_fallback_geocode_when_coords_missing(prox_dirs, monkeypatch):
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

    monkeypatch.setattr(
        "prepare.proximity_prep.prep.geocode_hotel",
        lambda *a, **k: {"lat": 45.75, "lon": 4.85, "address_resolved": "Lyon"},
    )

    seen: list[tuple[float, float]] = []

    def fake_shops(lat, lon):
        seen.append((lat, lon))
        return []

    prep = ProximityPrep(
        input_dir,
        output_dir,
        features=ProximityFeatures(
            fetch_shops=fake_shops,
            fetch_beaches=lambda lat, lon: [],
        ),
    )
    frame = prep.run()
    assert frame.loc[0, "hotel_code"] == "H9999"
    assert frame.loc[0, "geo_source"] == "name_geocode"
    assert seen and seen[0][0] == pytest.approx(45.75)
