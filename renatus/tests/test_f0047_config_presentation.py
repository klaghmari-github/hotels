"""
F0047 — config en presentation + crayon pour editer.

- Selection d un objet configure: valeurs en lecture (pas de saisie permanente)
- Bouton crayon par champ
- Fichier: dropzone seulement en edition (crayon) — F0100
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


def test_feature_f0047_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0047" in features


def test_html_presentation_structure():
    html = INDEX.read_text(encoding="utf-8")
    assert "is-presentation" in html
    assert "btn-pencil" in html
    assert 'data-testid="file-summary"' in html
    assert 'data-testid="edit-cfg-file"' in html
    assert 'data-testid="edit-cfg-name"' in html
    assert 'data-display="cfg-name"' in html


def test_js_presentation_mode():
    js = read_all_js()
    assert "enterConfigPresentation" in js
    assert "startEditField" in js
    assert "updateFileFieldMode" in js
    assert "file-summary" in js or "fileSummary" in js


def test_css_presentation_rules():
    css = CSS.read_text(encoding="utf-8")
    assert ".btn-pencil" in css
    assert "is-presentation" in css
    assert "file-summary" in css
    assert "show-file-editor" in css
