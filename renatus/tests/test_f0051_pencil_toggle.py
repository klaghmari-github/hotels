"""
F0051 — bouton modifier (crayon) activable / desactivable.

- Defaut: non actif, valeurs en presentation
- Click: actif, champ en edition
- Re-click: desactive, restaure les valeurs et revient en presentation
- Save conserve les modifications (flux existant via enterConfigPresentation)
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"
FEATURES = REPO / "gestion_projet" / "features.csv"


def test_feature_f0051_registered():
    features = FEATURES.read_text(encoding="utf-8")
    assert "F0051" in features
    assert "crayon toggle" in features or "toggle" in features.lower()


def test_html_pencil_aria_pressed_default_false():
    html = INDEX.read_text(encoding="utf-8")
    assert 'aria-pressed="false"' in html
    assert 'data-testid="edit-cfg-name"' in html
    # chaque crayon principal a aria-pressed
    for tid in (
        "edit-cfg-name",
        "edit-cfg-type",
        "edit-cfg-file",
        "edit-cfg-relation-name",
        "edit-cfg-mode",
        "edit-cfg-script",
        "edit-cfg-iter",
    ):
        assert tid in html
    assert html.count('aria-pressed="false"') >= 7


def test_js_toggle_and_cancel_api():
    js = read_all_js()
    assert "cancelEditField" in js
    assert "snapshotFieldControls" in js
    assert "restoreFieldControls" in js
    assert "fieldSnapshots" in js
    assert "setPencilActive" in js
    # toggle: re-click annule
    assert 'classList.contains("is-editing")' in js
    assert "Annuler et revenir a la presentation" in js
    # ne plus ouvrir tout le formulaire en retirant is-presentation
    # (seul le champ cible passe en edition)
    assert "el.configForm.classList.add(\"is-presentation\")" in js
    # startEditField appelle cancel si deja en edition
    assert "cancelEditField(field)" in js


def test_js_enter_presentation_clears_snapshots():
    js = read_all_js()
    # apres load/save: presentation + reset snapshots
    enter_idx = js.find("function enterConfigPresentation")
    assert enter_idx > 0
    block = js[enter_idx : enter_idx + 800]
    assert "fieldSnapshots" in block
    assert "is-editing" in block


def test_css_active_pencil_state():
    css = CSS.read_text(encoding="utf-8")
    assert 'aria-pressed="true"' in css or "aria-pressed=\"true\"" in css
    assert ".field-editable.is-editing .btn-pencil" in css
