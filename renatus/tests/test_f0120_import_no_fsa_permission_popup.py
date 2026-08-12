"""F0120 — import dossier: pas de popup permission File System Access (Chromium)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0120_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0120" in text


def test_js_directory_picker_still_present_after_f0130():
    """
    F0120 historique: eviter FSA permission.
    F0130: priorite inversee (FSA avant webkitdirectory) pour eviter
    « Importer N fichiers ». On verifie seulement que les deux chemins existent.
    """
    js = read_all_js()
    assert "openDirectoryPickerSync" in js
    assert "webkitdirectory" in js
    assert "showDirectoryPicker" in js
    # F0130: fallback themé
    assert "openWebkitDirectoryFallback" in js or "F0130" in js


def test_html_dir_picker_still_present():
    html = read_index()
    assert 'id="import-flow-dir-picker"' in html
    assert "webkitdirectory" in html
