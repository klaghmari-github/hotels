"""F0111 — import flux: selection dossier (arborescence) fiable."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0111_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0111" in text


def test_html_directory_browse_button():
    html = read_index()
    assert 'data-testid="import-flow-browse-dir"' in html
    assert 'data-testid="import-flow-dir-picker"' in html
    assert 'data-testid="import-flow-browse-file"' in html
    assert "Dossier" in html or "dossier" in html
    # F0113: webkitdirectory present in HTML (pas seulement via JS)
    assert "webkitdirectory" in html
    assert "visually-hidden-file" in html
    # pas de hidden HTML sur le dir picker (casse le selecteur dossier)
    # le tag dir-picker ne doit pas contenir l attribut bare "hidden"
    import re

    m = re.search(
        r'<input[^>]*id="import-flow-dir-picker"[^>]*>',
        html,
        re.I | re.S,
    )
    assert m, "dir picker input manquant"
    tag = m.group(0)
    assert "webkitdirectory" in tag
    assert " hidden" not in tag and not tag.endswith(" hidden>")
    assert "arborescence" in html.lower() or "dossier parent" in html.lower()


def test_js_directory_picker_and_drop():
    js = read_all_js()
    assert "openDirectoryPickerSync" in js
    assert "showDirectoryPicker" in js or "webkitdirectory" in js
    assert "handleDirectoryFiles" in js
    assert "filesFromDataTransfer" in js or "webkitGetAsEntry" in js
    assert "readDirEntry" in js or "collectFilesFromDirHandle" in js
    assert "ensureDirPickerAttrs" in js
    # ne pas await avant click (geste utilisateur)
    assert "openDirectoryPickerSync" in js


def test_css_browse_row():
    css = read_css()
    assert "import-flow-browse-row" in css
    assert "visually-hidden-file" in css


def test_feature_f0113_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0113" in text
