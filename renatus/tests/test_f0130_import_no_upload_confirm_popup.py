"""F0130 — import dossier: eviter popup Chromium « Importer N fichiers »."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0130_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0130" in text


def test_js_prefers_fsa_over_webkitdirectory_for_folder():
    """
    webkitdirectory declenche « Importer N fichiers sur ce site » (Chromium).
    showDirectoryPicker (FSA) evite ce dialogue de televersement multi-fichiers.
    """
    js = read_all_js()
    assert "F0130" in js
    assert "openDirectoryPickerSync" in js
    assert "openWebkitDirectoryFallback" in js
    assert "showDirectoryPicker" in js
    assert "confirmDialog" in js
    # ordre dans openDirectoryPickerSync: FSA avant fallback webkit
    idx_fn = js.find("function openDirectoryPickerSync")
    assert idx_fn >= 0
    chunk = js[idx_fn : idx_fn + 2200]
    idx_fsa = chunk.find("showDirectoryPicker")
    idx_fallback = chunk.find("openWebkitDirectoryFallback")
    assert idx_fsa >= 0
    assert idx_fallback >= 0
    assert idx_fsa < idx_fallback, (
        "showDirectoryPicker doit etre tente avant webkitdirectory fallback"
    )


def test_html_recommends_drop_and_has_dir_picker():
    html = read_index()
    assert "import-flow-browse-dir" in html
    assert "webkitdirectory" in html
    assert "glissez" in html.lower() or "glisser" in html.lower()
