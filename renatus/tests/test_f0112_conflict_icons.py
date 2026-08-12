"""F0112 — pictogrammes strategies conflit import (keep_both / keep_existing / replace)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0112_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0112" in text


def test_html_conflict_icons():
    html = read_index()
    assert 'data-testid="conflict-icon-keep_both"' in html
    assert 'data-testid="conflict-icon-keep_existing"' in html
    assert 'data-testid="conflict-icon-replace"' in html
    assert 'data-conflict="keep_both"' in html
    assert 'data-conflict="keep_existing"' in html
    assert 'data-conflict="replace"' in html
    assert "card-icon" in html
    assert "card-emoji" in html
    # pictogrammes emoji + SVG
    assert "📑" in html or "Renommer" in html
    assert "🛡️" in html or "Ignorer" in html
    assert "⬇️" in html or "Remplacer" in html
    assert html.count("<svg") >= 3


def test_css_conflict_icon_styles():
    css = read_css()
    assert "card-icon" in css
    assert "card-emoji" in css
    assert 'data-conflict="keep_both"' in css
    assert 'data-conflict="keep_existing"' in css
    assert 'data-conflict="replace"' in css
    assert "display: flex !important" in css or "display:flex !important" in css


def test_js_ensures_conflict_icons():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "ensureConflictIcons" in js
    assert "openImportFlowDialog" in js
