"""
F0072 — tete Config sticky au scroll.
F0086: plus de boutons Supprimer/Sauver/Renatus (collapse seul).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0072_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0072" in text


def test_css_config_header_sticky_body_scroll():
    from tests.helpers.static_sources import read_css, read_index

    css = read_css()
    assert ".config-zone" in css
    assert "overflow: hidden" in css
    assert ".config-form" in css
    # corps scrollable
    assert "overflow-y: auto" in css or "overflow: auto" in css
    # tete fixe
    assert "config-zone > .panel-head" in css or "sticky" in css
    html = read_index()
    # F0086: actions Config retirees
    assert 'id="btn-delete"' not in html
    assert 'id="btn-save"' not in html
    assert 'id="btn-build"' not in html
    assert 'id="btn-collapse-config"' in html
    assert 'id="config-zone"' in html
    assert 'id="config-form"' in html
