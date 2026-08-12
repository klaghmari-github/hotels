"""F0098 — popup Requires/Objects: canvas pleine largeur, pas de hint."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0098_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0098" in features


def test_html_no_lecture_seule_hint():
    html = read_index()
    assert "Lecture seule" not in html
    assert 'data-testid="requires-edit-hint"' not in html
    assert 'data-testid="zone-objects-edit-hint"' not in html
    assert 'data-testid="requires-edit-canvas"' in html
    assert 'data-testid="zone-objects-edit-canvas"' in html


def test_css_requires_edit_form_full_width():
    css = read_css()
    # override du grid props-form 2 cols
    assert "props-form.requires-edit-form" in css
    assert "flex !important" in css or "display: flex !important" in css
    assert ".requires-edit-canvas" in css
    assert "width: 100%" in css
