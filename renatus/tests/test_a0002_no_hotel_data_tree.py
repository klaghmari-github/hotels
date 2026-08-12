"""
A0002 — pas d'arborescence hotels (data/sim_v1, models catboost, ...) dans le depot.

Le coeur renatus ne versionne pas data/ ni de sous-dossiers metier hotels.
Paths n'expose plus les chemins sim_v1 / sim_v2 / ml hotels.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repo_has_no_data_directory():
    """Le depot renatus ne contient pas data/ (runtime hors package)."""
    assert not (REPO_ROOT / "data").exists(), (
        "data/ ne doit pas etre versionne dans renatus (A0002)"
    )


def test_repo_has_no_hotel_model_subdirs():
    """Pas de models/catboost|xgboost|ml1|ml2|super hotels dans le depot."""
    models = REPO_ROOT / "models"
    if not models.exists():
        return
    forbidden = {"catboost", "xgboost", "ml1", "ml2", "super", "sim_v1", "sim_v2"}
    present = {p.name for p in models.iterdir() if p.is_dir()}
    assert not (present & forbidden), f"dossiers models hotels: {present & forbidden}"


def test_paths_has_no_hotel_specific_attributes():
    """Paths generique : plus d'attributs sim_v1 / models_ml* hotels."""
    from renatus.pipeline import Paths

    paths = Paths(root=REPO_ROOT)
    hotel_attrs = [
        "output_sim_v1",
        "output_sim_v2",
        "output_ml",
        "output_common",
        "pipeline_sim_v1",
        "pipeline_sim_v2",
        "pipeline_ml",
        "pipeline_common",
        "models_catboost",
        "models_xgboost",
        "models_ml1",
        "models_ml2",
        "models_super",
        "out_sim_v1",
        "out_sim_v2",
        "out_ml",
    ]
    for name in hotel_attrs:
        assert not hasattr(paths, name), f"attribut hotels encore present: {name}"


def test_paths_source_has_no_hotel_path_assignments():
    """Le source paths.py n'assigne plus de chemins hotels (output/sim_*, models/*)."""
    text = (REPO_ROOT / "src" / "renatus" / "pipeline" / "paths.py").read_text(
        encoding="utf-8"
    )
    assert 'output / "sim_' not in text
    assert 'models / "catboost"' not in text
    assert 'models / "xgboost"' not in text
    assert "output_sim_" not in text
