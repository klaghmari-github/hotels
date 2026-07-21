"""Tests d'intégration du package prepare (imports, chemins, pipeline mocké)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import prepare
from prepare import (
    AllPrep,
    MeteoPrep,
    PreparePipeline,
    PreparePaths,
    ProximityPrep,
    RodPrep,
    SalesPrep,
    default_paths,
    run_pipeline,
)
from prepare.paths import PACKAGE_DIR, PROJECT_ROOT


def test_package_exports():
    assert prepare.__version__
    assert RodPrep is not None
    assert MeteoPrep is not None
    assert ProximityPrep is not None
    assert SalesPrep is not None
    assert AllPrep is not None
    assert PreparePipeline is not None
    assert callable(run_pipeline)


def test_default_paths_layout():
    paths = default_paths()
    assert paths.root == PACKAGE_DIR
    assert paths.rod_output == PACKAGE_DIR / "RodPrep" / "Output"
    assert paths.meteo_input == PACKAGE_DIR / "MeteoPrep" / "Input"
    assert paths.proximity_output == PACKAGE_DIR / "ProximityPrep" / "Output"
    assert paths.sales_output == PACKAGE_DIR / "SalesPrep" / "Output"
    assert paths.all_output == PACKAGE_DIR / "AllPrep" / "Output"
    assert (PROJECT_ROOT / "prepare").is_dir()
    assert (PACKAGE_DIR / "rod_prep").is_dir()
    assert (PACKAGE_DIR / "meteo_prep").is_dir()
    assert (PACKAGE_DIR / "proximity_prep").is_dir()
    assert (PACKAGE_DIR / "sales_prep").is_dir()


def test_paths_override_root(tmp_path: Path):
    paths = PreparePaths(root=tmp_path)
    assert paths.rod_input == tmp_path / "RodPrep" / "Input"
    assert paths.all_output == tmp_path / "AllPrep" / "Output"


def test_pipeline_order_rod_first_then_consumers(tmp_path: Path):
    """RodPrep s'exécute en premier ; Meteo/Proximity/Sales reçoivent son output."""
    paths = PreparePaths(root=tmp_path)
    for p in (
        paths.rod_input,
        paths.rod_output,
        paths.meteo_input,
        paths.meteo_output,
        paths.proximity_input,
        paths.proximity_output,
        paths.sales_input,
        paths.sales_output,
        paths.all_input,
        paths.all_output,
    ):
        p.mkdir(parents=True, exist_ok=True)

    lookup = pd.DataFrame(
        [
            {
                "nom_hotel": "Ibis budget Nice",
                "hotel_code": "H2075",
                "hotel_name": "Ibis budget Nice Californie",
                "hotel_city": "Nice",
                "hotel_lat": 43.69,
                "hotel_lon": 7.24,
            }
        ]
    )
    meteo = pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "hotel_name": "Ibis budget Nice Californie",
                "annee": 2025,
                "mois": 1,
                "meteo_temperature_c_mean": 10.0,
            }
        ]
    )
    prox = pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "hotel_name": "Ibis budget Nice Californie",
                "plage_distance_km": 0.2,
                "commerce_fb_100m": 1,
                "commerce_fb_500m": 5,
                "commerce_non_fb_100m": 0,
                "commerce_non_fb_500m": 2,
            }
        ]
    )
    sales = pd.DataFrame(
        [
            {
                "nom_hotel": "Ibis budget Nice",
                "hotel_code": "H2075",
                "annee": 2025,
                "mois": 1,
                "nombre_ventes": 10.0,
            }
        ]
    )
    final = pd.DataFrame(
        [
            {
                "nom_hotel": "Ibis budget Nice",
                "hotel_code": "H2075",
                "annee": 2025,
                "mois": 1,
                "nombre_ventes": 10.0,
                "meteo_temperature_c_mean": 10.0,
                "plage_distance_km": 0.2,
            }
        ]
    )

    pipe = PreparePipeline(paths=paths)
    order: list[str] = []

    def rod_side_effect(*_a, **_k):
        order.append("rod")
        return lookup

    def meteo_side_effect(*_a, **_k):
        order.append("meteo")
        return meteo

    def prox_side_effect(*_a, **_k):
        order.append("proximity")
        return prox

    def sales_side_effect(*_a, **_k):
        order.append("sales")
        return sales

    def all_side_effect(*_a, **_k):
        order.append("all")
        return final

    with (
        patch.object(pipe, "run_rod", side_effect=rod_side_effect),
        patch.object(pipe, "run_meteo", side_effect=meteo_side_effect),
        patch.object(pipe, "run_proximity", side_effect=prox_side_effect),
        patch.object(pipe, "run_sales", side_effect=sales_side_effect),
        patch.object(pipe, "run_all", side_effect=all_side_effect),
    ):
        result = pipe.run(skip_meteo=False, skip_proximity=False)

    assert order == ["rod", "meteo", "proximity", "sales", "all"]
    assert result.hotel_lookup.loc[0, "hotel_code"] == "H2075"
    assert result.meteo is not None
    assert result.proximity is not None
    assert result.sales_joined.loc[0, "hotel_code"] == "H2075"
    assert len(result.dataset_full) == 1


def test_all_prep_joins_on_hotel_code(tmp_path: Path):
    inp = tmp_path / "in"
    out = tmp_path / "out"
    inp.mkdir()
    out.mkdir()
    pd.DataFrame(
        [
            {
                "nom_hotel": "Nice",
                "hotel_code": "H2075",
                "annee": 2025,
                "mois": 3,
                "nombre_ventes": 5,
            }
        ]
    ).to_parquet(inp / "sales_joined.parquet", index=False)
    pd.DataFrame(
        [
            {
                "hotel_code": "H2075",
                "annee": 2025,
                "mois": 3,
                "meteo_temperature_c_mean": 12.5,
            }
        ]
    ).to_parquet(inp / "meteo_monthly.parquet", index=False)
    pd.DataFrame(
        [{"hotel_code": "H2075", "plage_distance_km": 0.1, "commerce_fb_500m": 8}]
    ).to_parquet(inp / "proximity.parquet", index=False)
    pd.DataFrame(
        [{"hotel_code": "H2075", "hotel_name": "Ibis budget Nice", "hotel_city": "Nice"}]
    ).to_parquet(inp / "rod_hotel_lookup.parquet", index=False)

    frame = AllPrep(inp, out).run()
    assert len(frame) == 1
    assert frame.loc[0, "hotel_code"] == "H2075"
    assert frame.loc[0, "meteo_temperature_c_mean"] == pytest.approx(12.5)
    assert frame.loc[0, "plage_distance_km"] == pytest.approx(0.1)
    assert frame.loc[0, "commerce_fb_500m"] == 8
    assert (out / "dataset_full.parquet").exists()


def test_shim_src_imports_still_work():
    """Les notebooks qui importent via Src/ restent compatibles."""
    import sys

    root = PROJECT_ROOT
    for sub in ("RodPrep", "MeteoPrep", "ProximityPrep", "SalesPrep", "AllPrep"):
        sys.path.insert(0, str(root / "prepare" / sub / "Src"))

    from all_prep.prep import AllPrep as AllPrepShim
    from meteo_prep.prep import MeteoPrep as MeteoPrepShim
    from proximity_prep.prep import ProximityPrep as ProximityPrepShim
    from rod_prep.prep import RodPrep as RodPrepShim
    from sales_prep.pipeline import SalesPrep as SalesPrepShim

    assert RodPrepShim is RodPrep
    assert MeteoPrepShim is MeteoPrep
    assert ProximityPrepShim is ProximityPrep
    assert SalesPrepShim is SalesPrep
    assert AllPrepShim is AllPrep
