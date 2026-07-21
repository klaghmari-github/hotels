"""Tests pipeline SalesPrep."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from prepare._shared.months import compute_year_month_stats, missing_boundary_months
from prepare.sales_prep import SalesPrep
from prepare.sales_prep import aggregations as agg
from rod_ia.config.settings import get_settings


def test_month_stats_boundary():
    stats = compute_year_month_stats({2, 6, 9})
    assert stats.premier_mois == 2
    assert stats.dernier_mois == 9
    assert stats.mois_manquants == 4
    assert missing_boundary_months(2, 9) == [1, 10, 11, 12]


def test_sales_prep_pipeline_on_real_csv():
    settings = get_settings()
    sales_path = settings.sales_csv_path
    if not sales_path.exists():
        return
    output = Path("/tmp/rod_sales_prep_test")
    prep = SalesPrep(sales_path=sales_path, output_dir=output, holdout_year=2026)
    joined = prep.run()
    assert not joined.empty
    assert "nom_hotel" in joined.columns or "nom_hotel" in str(joined.columns)
    assert len(prep.artifacts["step_2b"]) >= len(prep.artifacts["step_2a"])
    # Sans lookup RodPrep : hotel_code reste NA (jamais remplacé par le nom)
    assert "hotel_code" in joined.columns
    assert not (joined["hotel_code"].notna() & (joined["hotel_code"] == joined["nom_hotel"])).any()


def test_sales_prep_attaches_accor_code_from_lookup(tmp_path: Path):
    settings = get_settings()
    sales_path = settings.sales_csv_path
    if not sales_path.exists():
        return
    lookup = pd.DataFrame(
        [
            {"nom_hotel": "Ibis budget Nice", "hotel_code": "H2075"},
            {"nom_hotel": "Novotel Paris Tour Eiffel", "hotel_code": "H3546"},
        ]
    )
    prep = SalesPrep(
        sales_path=sales_path,
        output_dir=tmp_path / "out",
        rod_lookup=lookup,
        holdout_year=2026,
    )
    joined = prep.run()
    codes = joined.loc[joined["nom_hotel"] == "Ibis budget Nice", "hotel_code"].dropna().unique()
    assert list(codes) == ["H2075"]
    assert not (joined["hotel_code"].notna() & (joined["hotel_code"] == joined["nom_hotel"])).any()


def test_sales_prep_exploits_hotel_holidays_data(tmp_path: Path):
    """hotel_sales_data joint hotel_holidays_data (compteurs + arrays de jours)."""
    settings = get_settings()
    sales_path = settings.sales_csv_path
    if not sales_path.exists():
        return

    lookup = pd.DataFrame(
        [
            {"nom_hotel": "Ibis budget Nice", "hotel_code": "H2075"},
        ]
    )
    holidays = pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "annee": 2024,
                "mois": 1,
                "zone_scolaire": "B",
                "departement": "06",
                "nb_jours_feries": 1,
                "nb_jours_vacances_scolaires": 7,
                "nb_jours_vacances_hors_feries": 6,
                "nb_jours_dans_mois": 31,
                "jours_feries": ["2024-01-01"],
                "jours_vacances_scolaires": [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                    "2024-01-06",
                    "2024-01-07",
                ],
                "jours_vacances_hors_feries": [
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                    "2024-01-06",
                    "2024-01-07",
                ],
            }
        ]
    )
    # Étendre holidays pour toutes années/mois possibles du holdout
    # (jointure left — au moins jan 2024 matché si présent dans ventes)
    out = tmp_path / "out"
    prep = SalesPrep(
        sales_path=sales_path,
        output_dir=out,
        rod_lookup=lookup,
        holdout_year=2026,
        holidays=holidays,
    )
    joined = prep.run()
    assert "nb_jours_feries" in joined.columns
    assert "jours_feries" in joined.columns
    assert "jours_vacances_hors_feries" in joined.columns

    matched = joined[
        (joined["hotel_code"] == "H2075")
        & (joined["annee"] == 2024)
        & (joined["mois"] == 1)
    ]
    if not matched.empty:
        row = matched.iloc[0]
        assert row["nb_jours_feries"] == 1
        assert row["zone_scolaire"] == "B"
        assert "2024-01-01" in row["jours_feries"]
        assert "2024-01-01" not in row["jours_vacances_hors_feries"]

    assert (out / "hotel_sales_data.xlsx").exists()
    assert (out / "hotel_sales_data.parquet").exists()



def test_step_1a_aggregation_synthetic():
    frame = pd.DataFrame(
        {
            "nom_hotel": ["H1", "H1", "H1"],
            "annee": [2024, 2024, 2024],
            "mois": [2, 6, 9],
            "nombre_ventes": [1.0, 2.0, 3.0],
            "montant_ventes": [10.0, 20.0, 30.0],
            "nombre_paniers": ["t1", "t2", "t2"],
            "nombre_produits": ["p1", "p2", "p3"],
            "categorie": ["F_B", "N_F_B", "F_B"],
            "sous_categorie": ["A", "B", "C"],
        }
    )
    annual = agg.step_1a_annual_raw(frame)
    assert annual.loc[0, "nombre_ventes"] == 6.0
    assert annual.loc[0, "mois_manquants"] == 4
