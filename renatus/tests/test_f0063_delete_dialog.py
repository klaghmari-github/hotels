"""
F0063 — dialogue suppression stylé + raccourci clavier Delete.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0063_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0063" in text


def test_confirm_dialog_in_html():
    from tests.helpers.static_sources import read_index

    html = read_index()
    assert 'data-testid="confirm-dialog"' in html
    assert 'data-testid="confirm-ok"' in html
    assert 'data-testid="confirm-cancel"' in html
    assert "confirm-dialog" in html


def test_js_confirm_and_delete_key():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "confirmDialog" in js
    assert "Delete" in js
    assert "deleteStep" in js
    # plus de confirm natif pour delete step
    assert 'confirm("Supprimer la step' not in js


def test_css_confirm_dialog():
    from tests.helpers.static_sources import read_css

    css = read_css()
    assert ".confirm-dialog" in css
    assert ".btn.danger" in css
