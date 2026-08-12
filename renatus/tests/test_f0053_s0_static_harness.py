"""F0053-S0 — harness sources JS GUI (mono ou modules)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import (
    STATIC,
    js_contains,
    js_source_files,
    read_all_js,
)

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0053_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0053" in features
    assert "F0053-S0" in features


def test_static_js_sources_non_empty():
    files = js_source_files()
    assert files, "au moins un fichier JS GUI"
    blob = read_all_js()
    assert len(blob) > 1000
    # Symboles critiques toujours presents quelque part
    assert "renderGraph" in blob or "GraphCanvas" in blob
    assert js_contains("bootstrap") or js_contains("GuiApp")


def test_static_dir_exists():
    assert STATIC.is_dir()
    assert (STATIC / "index.html").is_file()
