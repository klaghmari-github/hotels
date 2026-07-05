"""Tests intégration récap ROD → imputation → sélection features."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.feature_imputer import FeatureImputer
from rod_ia.domain.services.feature_selector import FeatureSelector
from rod_ia.domain.services.ml_column_naming import MLColumnNaming
from rod_ia.domain.services.rod_recap_extractor import RodRecapExtractor
from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def registry(settings):
    return HotelIdentityRegistry(settings.identity_registry_path)


def _find_recap(settings) -> Path | None:
    return settings.rod_recap_path


def test_recap_extractor_produces_hotel_columns(registry, settings):
    recap = _find_recap(settings)
    if not recap:
        pytest.skip("Fichier récap absent")
    wide = RodRecapExtractor(recap, registry).extract_wide()
    assert len(wide) == 7
    recap_cols = [c for c in wide.columns if c.startswith("d_recap_")]
    assert len(recap_cols) >= 50


def test_feature_imputer_fills_missing_booleans(registry, settings):
    recap = _find_recap(settings)
    if not recap:
        pytest.skip("Fichier récap absent")
    out = settings.data_reference_dir / "rod_recap_test"
    wide = RodRecapExtractor(recap, registry, out).extract_wide()
    schema_path = out.with_suffix(".schema.json")
    imputer = FeatureImputer(registry, schema_path=schema_path)
    frame, report = imputer.impute(wide)
    bool_cols = [
        c
        for c in frame.columns
        if c.startswith("d_recap_") and schema_path.exists()
    ]
    if bool_cols:
        sample = bool_cols[0]
        assert frame[sample].notna().all()
    assert any(e["strategy"] == "boolean_zero" for e in report.entries)


def test_feature_selector_drops_constant_columns():
    frame = pd.DataFrame(
        {
            "hotel_id": ["a", "b", "c"],
            "d_const": [1.0, 1.0, 1.0],
            "d_var": [1.0, 2.0, 3.0],
        }
    )
    selector = FeatureSelector()
    out, kept, report = selector.select(frame, ["d_const", "d_var"])
    assert "d_const" not in kept
    assert "d_var" in kept
    assert report.to_dict()["n_removed_constant"] == 1


def test_pipeline_includes_recap_features(registry, settings, tmp_path):
    recap = _find_recap(settings)
    if not recap:
        pytest.skip("Fichier récap absent")
    pipeline = SalesTargetsPipeline(
        sales_path=settings.sales_csv_path,
        identity_registry=registry,
        output_dir=tmp_path,
        evaluation_year=2026,
        recap_path=recap,
        recap_output_dir=tmp_path / "rod_recap",
    )
    dataset = pipeline.build_training_dataset()
    meta = json.loads((tmp_path / "dataset_meta.json").read_text(encoding="utf-8"))
    recap_features = [c for c in meta["feature_cols"] if c.startswith("d_recap_")]
    assert meta["n_recap_features"] > 0
    assert len(recap_features) == meta["n_recap_features"]
    assert MLColumnNaming.descriptive("clients_mois") in meta["feature_cols"]
    assert MLColumnNaming.descriptive("taux_acheteur") in meta["feature_cols"]
    assert (tmp_path / "imputation_report.json").exists()
    assert (tmp_path / "feature_selection_report.json").exists()

    x = pd.read_csv(tmp_path / "X_descriptive.csv")
    for col in meta["feature_cols"]:
        assert col in x.columns
        assert x[col].nunique(dropna=True) > 1 or col.startswith("d_pct_")


def test_porte_italie_gets_imputed_recap(registry, settings, tmp_path):
    recap = _find_recap(settings)
    if not recap:
        pytest.skip("Fichier récap absent")
    pipeline = SalesTargetsPipeline(
        sales_path=settings.sales_csv_path,
        identity_registry=registry,
        output_dir=tmp_path,
        evaluation_year=2026,
        recap_path=recap,
    )
    dataset = pipeline.build_training_dataset()
    row = dataset[dataset["hotel_id"] == "novotel-porte-italie"]
    assert not row.empty
    recap_cols = [c for c in dataset.columns if c.startswith("d_recap_")]
    assert recap_cols
    assert row[recap_cols].notna().all(axis=None)