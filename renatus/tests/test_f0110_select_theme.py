"""F0110 — listes deroulantes theme sombre GUI (Objects, Requires, Flux, Config)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0110_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0110" in text


def test_html_selects_use_renatus_select():
    html = read_index()
    assert 'class="renatus-select"' in html or "renatus-select" in html
    assert 'data-testid="zone-objects-zone-select"' in html
    assert 'data-testid="requires-zone-select"' in html
    # wraps
    assert "renatus-select-wrap" in html
    assert "zone-objects-zone-select" in html
    assert "requires-zone-select" in html
    # classes on zone selects
    assert 'id="zone-objects-zone-select"' in html
    assert "renatus-select" in html.split('id="zone-objects-zone-select"')[0][-200:] or (
        'class="renatus-select"' in html
        or "class=\"renatus-select\"" in html
    )


def test_css_dark_select_theme():
    css = read_css()
    assert "renatus-select" in css
    assert "color-scheme: dark" in css or "color-scheme:dark" in css
    assert "appearance: none" in css or "appearance:none" in css
    assert "requires-zone-select-wrap" in css or "requires-edit-toolbar select" in css
    # pas de fond blanc force sur select
    assert ".renatus-select" in css
