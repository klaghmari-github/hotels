"""Tests export audit ZIP."""

from __future__ import annotations

import zipfile
from pathlib import Path

from run_export import collect_files, create_archive


ROOT = Path(__file__).resolve().parents[1]


def test_collect_includes_sources_and_excludes_processed():
    stats = collect_files(ROOT)
    included = set(stats.included)

    assert "README.md" in included
    assert "requirements.txt" in included
    assert "pyproject.toml" in included
    assert "rod_ia/api/app_factory.py" in included
    assert "rod_ia/web/index.html" in included
    assert "tests/test_simulation.py" in included
    assert "docs/consignes.md" in included
    assert "data/reference/hotel_identity_registry.json" in included
    assert any(p.startswith("sources/raw/") and p.endswith(".csv") for p in included)

    assert "data/processed/dataset_meta.json" not in included
    assert "rod_ia/web/docs/index.html" not in included
    assert not any(p.startswith("rod_ia/feature_store/") for p in included)
    assert not any(p.endswith(".joblib") for p in included)
    assert "data/reference/rod_reference.json" not in included


def test_create_archive_writes_manifest(tmp_path):
    archive = create_archive(ROOT, tmp_path, stamp="test")
    assert archive.exists()

    with zipfile.ZipFile(archive, "r") as zf:
        names = set(zf.namelist())
        assert "EXPORT_MANIFEST.txt" in names
        assert "rod_ia/domain/services/simulation_orchestrator.py" in names
        manifest = zf.read("EXPORT_MANIFEST.txt").decode("utf-8")
        assert "Fichiers inclus" in manifest
        assert all("/feature_store/" not in n for n in names)
        assert all(not n.startswith("data/processed/") for n in names)