"""Tests MeteoPrep — années cibles, imputation N←N-1, pas de fill 0."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prepare" / "MeteoPrep" / "Src"))

from meteo_prep.prep import MeteoPrep, default_target_years
from meteo_prep.weather import MonthlyWeather, impute_previous_year_month


@pytest.fixture
def meteo_dirs(tmp_path: Path) -> tuple[Path, Path]:
    input_dir = tmp_path / "Input"
    output_dir = tmp_path / "Output"
    input_dir.mkdir()
    output_dir.mkdir()
    return input_dir, output_dir


def _write_hotels(input_dir: Path) -> None:
    frame = pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "hotel_name": "Ibis budget Nice",
                "hotel_brand": "IBIS BUDGET",
                "hotel_city": "Nice",
                "hotel_lat": 43.689186,
                "hotel_lon": 7.240512,
            }
        ]
    )
    frame.to_parquet(input_dir / "hotels.parquet", index=False)
    frame.to_csv(input_dir / "hotels.csv", index=False)


def test_default_target_years_is_current_year():
    years = default_target_years()
    assert len(years) == 1
    assert years[0] > 2000


def test_empty_target_years_falls_back_to_current(meteo_dirs):
    input_dir, output_dir = meteo_dirs
    prep = MeteoPrep(input_dir, output_dir, target_years=())
    assert prep.target_years == default_target_years()


def test_impute_uses_previous_year_same_month_not_zero(meteo_dirs):
    input_dir, output_dir = meteo_dirs
    prep = MeteoPrep(input_dir, output_dir, target_years=(2025, 2026))

    frame = pd.DataFrame(
        [
            {
                "hotel_code": "H1",
                "hotel_name": "A",
                "annee": 2025,
                "mois": 3,
                "meteo_temperature_c_mean": 12.0,
            },
            {
                "hotel_code": "H1",
                "hotel_name": "A",
                "annee": 2025,
                "mois": 7,
                "meteo_temperature_c_mean": 22.0,
            },
            {
                "hotel_code": "H1",
                "hotel_name": "A",
                "annee": 2026,
                "mois": 3,
                "meteo_temperature_c_mean": None,
            },
            {
                "hotel_code": "H1",
                "hotel_name": "A",
                "annee": 2026,
                "mois": 7,
                "meteo_temperature_c_mean": None,
            },
            {
                "hotel_code": "H1",
                "hotel_name": "A",
                "annee": 2026,
                "mois": 11,
                "meteo_temperature_c_mean": None,
            },
        ]
    )
    out = prep._impute_missing(frame)
    by_key = {
        (int(r.annee), int(r.mois)): r.meteo_temperature_c_mean
        for r in out.itertuples()
    }
    assert by_key[(2026, 3)] == pytest.approx(12.0)
    assert by_key[(2026, 7)] == pytest.approx(22.0)
    # Pas de valeur en 2025-11 → reste NaN, jamais 0
    assert pd.isna(by_key[(2026, 11)])
    assert 0.0 not in set(out["meteo_temperature_c_mean"].dropna())


def test_run_does_not_crash_when_weather_empty(meteo_dirs):
    input_dir, output_dir = meteo_dirs
    _write_hotels(input_dir)
    prep = MeteoPrep(input_dir, output_dir, target_years=(2026,))

    with patch.object(prep, "_fetch_weather_by_year_month", return_value={}):
        frame = prep.run()

    assert not frame.empty
    assert set(frame["annee"].unique()) == {2026}
    assert len(frame) == 12  # 12 mois
    assert (frame["hotel_code"] == "H2075").all()
    # colonnes météo absentes ou NaN, mais pas de plantage
    meteo_cols = [c for c in frame.columns if c.startswith("meteo_")]
    if meteo_cols:
        assert not (frame[meteo_cols] == 0).all().any()


def test_run_builds_year_month_grid_and_imputes(meteo_dirs):
    input_dir, output_dir = meteo_dirs
    _write_hotels(input_dir)
    prep = MeteoPrep(input_dir, output_dir, target_years=(2026,))

    fake = {
        (2025, m): {
            "meteo_temperature_c_mean": float(10 + m),
            "meteo_temperature_c_min": float(5 + m),
            "meteo_temperature_c_max": float(15 + m),
        }
        for m in range(1, 13)
    }
    # Année en cours : seulement janv–juin
    for m in range(1, 7):
        fake[(2026, m)] = {
            "meteo_temperature_c_mean": float(20 + m),
            "meteo_temperature_c_min": float(15 + m),
            "meteo_temperature_c_max": float(25 + m),
        }

    with patch.object(prep, "_fetch_weather_by_year_month", return_value=fake):
        frame = prep.run()

    assert set(frame["annee"].unique()) == {2026}
    assert list(frame["mois"]) == list(range(1, 13))
    # Mois 1 réel 2026
    jan = frame.loc[frame["mois"] == 1, "meteo_temperature_c_mean"].iloc[0]
    assert jan == pytest.approx(21.0)
    # Mois 8 manquant en 2026 → repris de 2025 (= 10+8)
    aug = frame.loc[frame["mois"] == 8, "meteo_temperature_c_mean"].iloc[0]
    assert aug == pytest.approx(18.0)
    assert (output_dir / "meteo_monthly.parquet").exists()


def test_weather_for_hotel_missing_coords_no_crash(meteo_dirs):
    """Sans lat/lon : échec propre, pas de géocodage d'adresse."""
    input_dir, output_dir = meteo_dirs
    prep = MeteoPrep(input_dir, output_dir, target_years=(2026,))
    hotel = pd.Series(
        {
            "hotel_code": "X",
            "hotel_name": "Unknown",
            "hotel_city": "",
            "hotel_lat": None,
            "hotel_lon": None,
        }
    )
    info = prep.weather_for_hotel(hotel)
    assert info["source"] == "failed"
    assert info["weather_by_year_month"] == {}
    assert info["nb_cles_meteo"] == 0
    assert any("Coordonnées absentes" in w for w in info["warnings"])


def test_monthly_weather_for_point_builds_grid():
    """MonthlyWeather produit une grille année×mois indépendante du domaine hôtel."""
    mw = MonthlyWeather(years=(2024, 2025))
    fake = {
        (2024, 1): {"meteo_temperature_c_mean": 5.0},
        (2025, 6): {"meteo_temperature_c_mean": 20.0},
    }
    with patch.object(mw, "fetch_by_year_month", return_value=fake):
        frame = mw.for_point(43.7, 7.2)

    assert len(frame) == 24  # 2 ans × 12 mois
    assert set(frame["annee"].unique()) == {2024, 2025}
    assert list(frame["mois"].unique()) == list(range(1, 13))
    assert (frame["lat"] == 43.7).all()
    assert (frame["lon"] == 7.2).all()
    jan24 = frame.loc[(frame["annee"] == 2024) & (frame["mois"] == 1), "meteo_temperature_c_mean"]
    assert jan24.iloc[0] == pytest.approx(5.0)
    feb24 = frame.loc[(frame["annee"] == 2024) & (frame["mois"] == 2), "meteo_temperature_c_mean"]
    assert pd.isna(feb24.iloc[0])


def test_monthly_weather_for_points_propagates_ids():
    mw = MonthlyWeather(years=(2025,))
    locations = pd.DataFrame(
        [
            {"point_id": "A", "lat": 48.8, "lon": 2.3},
            {"point_id": "B", "lat": 43.6, "lon": 1.4},
        ]
    )

    def fake_fetch(lat, lon, start_year=None, end_year=None):
        return {(2025, 1): {"meteo_temperature_c_mean": float(lat)}}

    with patch.object(mw, "fetch_by_year_month", side_effect=fake_fetch):
        frame = mw.for_points(locations, id_cols=("point_id",))

    assert set(frame["point_id"].unique()) == {"A", "B"}
    assert len(frame) == 24  # 2 points × 12 mois
    a_jan = frame.loc[
        (frame["point_id"] == "A") & (frame["mois"] == 1), "meteo_temperature_c_mean"
    ].iloc[0]
    assert a_jan == pytest.approx(48.8)


def test_monthly_weather_invalid_coords_returns_empty_grid():
    mw = MonthlyWeather(years=(2026,))
    frame = mw.for_point(None, None)  # type: ignore[arg-type]
    assert len(frame) == 12
    assert frame["lat"].isna().all()
    assert "meteo_temperature_c_mean" not in frame.columns or frame.filter(
        like="meteo_"
    ).isna().all().all()


def test_impute_previous_year_month_by_coords():
    frame = pd.DataFrame(
        [
            {"lat": 1.0, "lon": 2.0, "annee": 2024, "mois": 3, "meteo_temperature_c_mean": 10.0},
            {"lat": 1.0, "lon": 2.0, "annee": 2025, "mois": 3, "meteo_temperature_c_mean": None},
            {"lat": 1.0, "lon": 2.0, "annee": 2025, "mois": 4, "meteo_temperature_c_mean": None},
        ]
    )
    out = impute_previous_year_month(frame)
    by_m = {int(r.mois): r.meteo_temperature_c_mean for r in out[out["annee"] == 2025].itertuples()}
    assert by_m[3] == pytest.approx(10.0)
    assert pd.isna(by_m[4])


def test_compute_meteo_final_geo_and_years():
    """Tout-en-un : geo + années → grille imputée filtrée sur les années cibles."""
    geo = pd.DataFrame(
        [
            {"point_id": "P1", "lat": 43.7, "lon": 7.2},
        ]
    )
    fake = {
        (2025, m): {"meteo_temperature_c_mean": float(10 + m)} for m in range(1, 13)
    }
    for m in range(1, 7):
        fake[(2026, m)] = {"meteo_temperature_c_mean": float(20 + m)}

    with patch.object(MonthlyWeather, "fetch_by_year_month", return_value=fake):
        frame = MonthlyWeather.compute_meteo_final(
            geo,
            years=(2026,),
            id_cols=("point_id",),
        )

    assert set(frame["annee"].unique()) == {2026}
    assert len(frame) == 12
    assert (frame["point_id"] == "P1").all()
    assert "lat" in frame.columns and "lon" in frame.columns
    # mois 1 réel 2026
    assert frame.loc[frame["mois"] == 1, "meteo_temperature_c_mean"].iloc[0] == pytest.approx(21.0)
    # mois 8 manquant → imputé depuis 2025
    assert frame.loc[frame["mois"] == 8, "meteo_temperature_c_mean"].iloc[0] == pytest.approx(18.0)


def test_compute_meteo_final_preserves_lat_lon_column_names():
    """lat_col / lon_col fournis sont conservés tels quels (pas de renommage)."""
    geo = pd.DataFrame(
        [
            {
                "hotel_code": "H1",
                "hotel_name": "Nice",
                "hotel_lat": 43.7,
                "hotel_lon": 7.2,
            }
        ]
    )
    fake = {(2026, m): {"meteo_temperature_c_mean": float(m)} for m in range(1, 13)}

    with patch.object(MonthlyWeather, "fetch_by_year_month", return_value=fake):
        frame = MonthlyWeather.compute_meteo_final(
            geo,
            years=(2026,),
            lat_col="hotel_lat",
            lon_col="hotel_lon",
            id_cols=("hotel_code", "hotel_name"),
            impute=False,
        )

    assert "hotel_lat" in frame.columns
    assert "hotel_lon" in frame.columns
    assert "lat" not in frame.columns
    assert "lon" not in frame.columns
    assert frame["hotel_lat"].tolist() == pytest.approx([43.7] * 12)
    assert frame["hotel_lon"].tolist() == pytest.approx([7.2] * 12)
    assert (frame["hotel_code"] == "H1").all()


def test_meteo_prep_compute_meteo_final_from_geo(meteo_dirs):
    input_dir, output_dir = meteo_dirs
    _write_hotels(input_dir)
    prep = MeteoPrep(input_dir, output_dir, target_years=(2026,))
    hotels = prep.load_input()

    fake = {
        (2025, m): {"meteo_temperature_c_mean": float(m)} for m in range(1, 13)
    }
    with patch.object(MonthlyWeather, "fetch_by_year_month", return_value=fake):
        frame = prep.compute_meteo_final(geo=hotels, years=(2026,), use_pure_api=True)

    assert set(frame["annee"].unique()) == {2026}
    assert len(frame) == 12
    assert "lat" not in frame.columns
    assert "lon" not in frame.columns
    assert "hotel_lat" in frame.columns and "hotel_lon" in frame.columns
    assert (frame["hotel_code"] == "H2075").all()
    assert frame.loc[frame["mois"] == 3, "meteo_temperature_c_mean"].iloc[0] == pytest.approx(3.0)
