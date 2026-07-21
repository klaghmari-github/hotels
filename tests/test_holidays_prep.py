"""Tests HolidaysPrep — fériés, vacances hors fériés, zone, Excel."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from prepare.holidays_prep import (
    HolidaysPrep,
    SchoolHolidayCalendar,
    SchoolPeriod,
    french_public_holidays,
    monthly_counts_for_year,
)
from prepare.holidays_prep.calendar import (
    GeoZone,
    extract_departement,
    school_holiday_days,
)


def test_french_public_holidays_2024():
    days = french_public_holidays(2024)
    assert date(2024, 1, 1) in days
    assert date(2024, 5, 1) in days
    assert date(2024, 5, 8) in days
    assert date(2024, 7, 14) in days
    assert date(2024, 12, 25) in days
    # Lundi de Pâques 2024 = 1er avril
    assert date(2024, 4, 1) in days
    # Alsace-Moselle
    am = french_public_holidays(2024, departement="67")
    assert date(2024, 12, 26) in am
    assert date(2024, 3, 29) in am  # vendredi saint 2024


def test_school_holiday_days_and_monthly_split():
    # Vacances du 20 oct au 5 nov (reprise = 5 nov exclus) → 16 jours
    periods = [
        SchoolPeriod(
            description="Toussaint",
            start=date(2024, 10, 20),
            end=date(2024, 11, 5),
            zone="C",
        )
    ]
    oct_days = school_holiday_days(periods, 2024, 10)
    nov_days = school_holiday_days(periods, 2024, 11)
    assert date(2024, 10, 20) in oct_days
    assert date(2024, 10, 31) in oct_days
    assert date(2024, 11, 1) in nov_days
    assert date(2024, 11, 4) in nov_days
    assert date(2024, 11, 5) not in nov_days

    rows = monthly_counts_for_year(2024, periods=periods, departement="75")
    by_month = {r.mois: r for r in rows}
    # Nov 2024 : 1er (Toussaint) + 11 (Armistice) = 2 fériés
    assert by_month[11].nb_jours_feries == 2
    assert by_month[11].nb_jours_vacances_scolaires == 4  # 1-4 nov
    # 1er nov férié ∩ vacances → hors_feries = 2,3,4 nov
    assert by_month[11].nb_jours_vacances_hors_feries == 3
    assert by_month[10].nb_jours_vacances_scolaires == 12  # 20-31 oct
    assert by_month[10].nb_jours_vacances_hors_feries == 12



def test_extract_departement_from_props():
    assert extract_departement({"codeDepartement": "06"}) == "06"
    assert extract_departement({"citycode": "75105", "postcode": "75005"}) == "75"
    assert extract_departement({"postcode": "06000"}) == "06"
    assert extract_departement({"postcode": "20200"}) == "2B"
    assert extract_departement({"context": "69, Rhône, Auvergne-Rhône-Alpes"}) == "69"


def test_holidays_prep_run_writes_excel(tmp_path: Path):
    input_dir = tmp_path / "Input"
    output_dir = tmp_path / "Output"
    input_dir.mkdir()
    output_dir.mkdir()

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

    def resolve(_lat, _lon):
        return GeoZone(zone="B", departement="06", commune="Nice", label="Nice (06)")

    def fetch_periods(zone, years):
        assert zone == "B"
        return [
            SchoolPeriod(
                description="Été",
                start=date(2025, 7, 5),
                end=date(2025, 9, 1),
                zone="B",
            )
        ]

    cal = SchoolHolidayCalendar(resolve_zone=resolve, fetch_periods=fetch_periods)
    prep = HolidaysPrep(
        input_dir, output_dir, target_years=(2025,), calendar=cal
    )
    frame = prep.run()

    assert len(frame) == 12
    assert set(frame["mois"]) == set(range(1, 13))
    july = frame[frame["mois"] == 7].iloc[0]
    assert july["zone_scolaire"] == "B"
    assert july["nb_jours_vacances_scolaires"] == 27  # 5-31 juil
    assert july["nb_jours_feries"] == 1  # 14 juil
    assert july["nb_jours_vacances_hors_feries"] == 26

    assert (output_dir / "holidays_monthly.xlsx").exists()
    assert (output_dir / "holidays_monthly.parquet").exists()
    assert (output_dir / "holidays_monthly.csv").exists()

    xl = pd.read_excel(output_dir / "holidays_monthly.xlsx", sheet_name="holidays_monthly")
    assert len(xl) == 12
    resume = pd.read_excel(output_dir / "holidays_monthly.xlsx", sheet_name="resume_annuel")
    assert len(resume) == 1
    assert resume.loc[0, "nb_jours_feries"] >= 1
