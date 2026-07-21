"""Tests MeteoPrep — années cibles, imputation N←N-1, pas de fill 0."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from prepare.meteo_prep import MeteoPrep, MonthlyWeather, default_target_years, impute_previous_year_month


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
    assert pd.isna(by_key[(2026, 11)])
    assert 0.0 not in set(out["meteo_temperature_c_mean"].dropna())


def test_run_does_not_crash_when_weather_empty(meteo_dirs):
    input_dir, output_dir = meteo_dirs
    _write_hotels(input_dir)
    prep = MeteoPrep(input_dir, output_dir, target_years=(2026,))

    with patch.object(prep, "_fetch_weather_by_year_month", return_value={}):
        frame = prep.run()

    assert not frame.empty
