"""
F0038 — dialogue stylé pour nouvel onglet pipeline (remplace window.prompt).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


def test_feature_f0038_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0038" in features


def test_ui_new_tab_dialog():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-testid="new-tab-dialog"' in html
    assert 'data-testid="new-tab-name"' in html
    assert 'data-testid="new-tab-confirm"' in html
    # F0045: libelle « Nouvelle zone » (ex. Nouvel onglet)
    assert "Nouvelle zone" in html or "Nouvel onglet" in html

    js = read_all_js()
    assert "openNewTabDialog" in js
    assert "createPipelineTab" in js
    assert "new-tab-dialog" in js or "newTabDialog" in js
    # plus de prompt principal pour les onglets
    assert 'window.prompt("Nom du nouvel onglet pipeline"' not in js

    css = CSS.read_text(encoding="utf-8")
    assert "new-tab-form" in css
    assert "dialog-head" in css


def test_btn_tab_add_opens_dialog_not_prompt():
    js = read_all_js()
    assert "btnTabAdd" in js
    assert "openNewTabDialog" in js
