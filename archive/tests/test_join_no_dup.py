"""Tests merge_no_duplicate_columns."""

from __future__ import annotations

import pandas as pd

from prepare._shared.join import merge_no_duplicate_columns


def test_merge_skips_existing_columns():
    left = pd.DataFrame(
        [{"hotel_code": "H1", "annee": 2024, "mois": 1, "hotel_name": "A", "ventes": 1}]
    )
    right = pd.DataFrame(
        [
            {
                "hotel_code": "H1",
                "annee": 2024,
                "mois": 1,
                "hotel_name": "B",
                "meteo_x": 10.0,
            }
        ]
    )
    out = merge_no_duplicate_columns(
        left, right, on=["hotel_code", "annee", "mois"], how="left"
    )
    assert out.loc[0, "hotel_name"] == "A"
    assert out.loc[0, "meteo_x"] == 10.0
    assert "hotel_name_x" not in out.columns
    assert list(out.columns).count("hotel_name") == 1
