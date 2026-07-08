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
from rod_ia.domain.services.rod_recap_extractor import (
    RECAP_GEO_COORDINATE_COLUMNS,
    RECAP_HOTEL_CODE_COLUMN,
    RECAP_HOTEL_NAME_ALIAS_COLUMNS,
    RodRecapExtractor,
)
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
    assert "hotel_id" in wide.columns
    assert "code_h" in wide.columns
    recap_cols = [c for c in wide.columns if c.startswith("d_recap_")]
    assert len(recap_cols) >= 50


def _rod_prep_src_path() -> Path:
    return Path(__file__).resolve().parents[1] / "prepare/RodPrep/Src"


def _registry_copy(tmp_path: Path, settings) -> Path:
    import shutil

    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "hotel_identity_registry.json"
    shutil.copy2(settings.identity_registry_path, target)
    return target


def test_rod_prep_geo_priority_recap_over_registry(registry, settings, tmp_path):
    """Les coordonnées saisies dans le récap priment sur le registre."""
    recap = _find_recap(settings)
    if not recap:
        pytest.skip("Fichier récap absent")
    import sys

    sys.path.insert(0, str(_rod_prep_src_path()))
    from rod_prep.prep import RodPrep

    prep = RodPrep(
        Path(__file__).resolve().parents[1] / "prepare/RodPrep/Input",
        settings.data_reference_dir / "rod_recap_geo_test",
        registry_path=_registry_copy(tmp_path, settings),
    )
    lookup = prep.run(geocode_missing=False)
    row = lookup[lookup["hotel_code"] == "HB6A3"].iloc[0]
    assert row["hotel_geo_source"] == "recap"
    assert row["hotel_lat"] == pytest.approx(48.591522)
    assert row["hotel_lon"] == pytest.approx(7.754599)


def test_rod_prep_geocodes_when_recap_and_registry_empty(
    registry, settings, tmp_path, monkeypatch
):
    recap = _find_recap(settings)
    if not recap:
        pytest.skip("Fichier récap absent")
    import sys

    sys.path.insert(0, str(_rod_prep_src_path()))
    import rod_prep.prep as rod_prep_module
    from rod_prep.prep import RodPrep

    monkeypatch.setattr(
        rod_prep_module,
        "geocode_hotel",
        lambda hotel_name, address="", city="", **_: {
            "lat": 48.88,
            "lon": 2.33,
            "address_resolved": "Paris",
        },
    )

    prep = RodPrep(
        Path(__file__).resolve().parents[1] / "prepare/RodPrep/Input",
        settings.data_reference_dir / "rod_recap_geo_test2",
        registry_path=_registry_copy(tmp_path / "geo2", settings),
    )
    lookup = prep.run(geocode_missing=True)
    row = lookup[lookup["hotel_code"] == "H0373"].iloc[0]
    assert row["hotel_geo_source"] == "recap"
    porte = lookup[lookup["nom_hotel"] == "Novotel Porte d'Italie"].iloc[0]
    assert porte["hotel_geo_source"] == "nominatim"
    assert porte["hotel_lat"] == pytest.approx(48.88)


def test_rod_prep_hotel_code_is_accor_code(registry, settings, tmp_path):
    """``hotel_code`` = CODE H Accor ; les alias de nom restent dans hotel_name / nom_hotel."""
    recap = _find_recap(settings)
    if not recap:
        pytest.skip("Fichier récap absent")
    import sys

    sys.path.insert(0, str(_rod_prep_src_path()))
    from rod_prep.prep import RodPrep

    out_dir = settings.data_reference_dir / "rod_recap_code_test"
    prep = RodPrep(
        Path(__file__).resolve().parents[1] / "prepare/RodPrep/Input",
        out_dir,
        registry_path=_registry_copy(tmp_path, settings),
    )
    lookup = prep.run(geocode_missing=False)
    features = pd.read_csv(out_dir / "rod_features.csv")
    assert set(lookup["hotel_code"].dropna()) == {
        "H2075",
        "HB6A3",
        "H0815",
        "HB5I0",
        "H3546",
        "H0373",
        "H6188",
    }
    assert "hotel_id" not in lookup.columns
    assert "hotel_code" in features.columns
    assert RECAP_HOTEL_CODE_COLUMN not in features.columns
    assert not RECAP_GEO_COORDINATE_COLUMNS.intersection(features.columns)
    assert not RECAP_HOTEL_NAME_ALIAS_COLUMNS.intersection(features.columns)


def test_recap_extractor_no_hotel_split_columns(registry, settings):
    """Un champ Excel ne doit pas être éclaté entre hôtels (bug _rN)."""
    recap = _find_recap(settings)
    if not recap:
        pytest.skip("Fichier récap absent")
    from rod_ia.domain.services.ml_column_naming import MLColumnNaming

    wide = RodRecapExtractor(recap, registry).extract_wide()
    col = MLColumnNaming.recap_column(
        "5_simulateur_de_revenus_ecran_de_controle_parametres_nb_de_chambres"
    )
    suffixed = f"{col}_r126"
    assert col in wide.columns
    assert suffixed not in wide.columns
    assert wide[col].notna().all()


def test_recap_column_names_fold_accents_and_strip_prefixes():
    from rod_ia.domain.services.ml_column_naming import MLColumnNaming

    col = MLColumnNaming.recap_column(
        "1_informations_generales_localisation_environnement_nb_supermarches"
    )
    assert col == "d_recap_generales_localisation_environnement_nb_supermarches"
    assert "_s" not in col.split("supermarches")[0]

    col = MLColumnNaming.recap_column(
        "5_simulateur_de_revenus_ecran_de_controle_parametres_nb_de_chambres"
    )
    assert col == "d_recap_de_controle_parametres_nb_de_chambres"
    assert "informations_" not in col
    assert "simulateur_de_revenus_ecran_" not in col


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