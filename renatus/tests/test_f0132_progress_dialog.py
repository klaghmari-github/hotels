"""F0132 — pop bloquante « traitement en cours » + barre de progression."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0132_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0132" in text


def test_html_progress_dialog():
    html = read_index()
    assert 'data-testid="progress-dialog"' in html
    assert 'id="progress-dialog"' in html
    assert 'data-testid="progress-dialog-fill"' in html
    assert 'data-testid="progress-dialog-label"' in html
    assert 'data-testid="progress-dialog-title"' in html
    assert 'data-testid="progress-dialog-message"' in html
    assert "progress-dialog" in html
    # cache-bust F0132
    assert "main.js?v=F0132" in html or "F0132" in html


def test_js_progress_dialog_api_and_import_wire():
    js = read_all_js()
    assert "openProgressDialog" in js
    assert "closeProgressDialog" in js
    assert "withProgress" in js
    assert "progress-dialog" in js
    # branchement import
    assert "withProgress" in js
    assert "Import en cours" in js or "Upload du dossier" in js
    # ESC bloque
    assert 'addEventListener("cancel"' in js or "addEventListener('cancel'" in js


def test_css_progress_dialog():
    css = read_css()
    assert "progress-dialog" in css
    assert "progress-dialog-fill" in css
    assert "is-indeterminate" in css
    assert "progress-spin" in css or "progress-indeterminate" in css
