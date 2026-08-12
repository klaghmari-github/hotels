"""F0076 — panneaux collapsables Outils / Config / View."""

from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0076_registered():
    assert "F0076" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_html_collapse_controls():
    from tests.helpers.static_sources import read_css, read_index, read_all_js

    html = read_index()
    assert 'data-testid="btn-collapse-sidebar"' in html
    assert 'data-testid="btn-collapse-config"' in html
    assert 'data-testid="btn-collapse-bottom"' in html
    assert 'data-testid="rail-sidebar"' in html
    assert 'data-testid="rail-config"' in html
    assert 'data-testid="rail-bottom"' in html
    assert 'id="gui-layout"' in html

    css = read_css()
    assert "sidebar-collapsed" in css
    assert "config-collapsed" in css
    assert "bottom-collapsed" in css
    assert ".panel-rail" in css

    js = read_all_js()
    assert "wireLayout" in js
    assert "togglePanel" in js
    assert "renatus.gui.layout" in js


def test_css_collapsed_grid():
    from tests.helpers.static_sources import read_css

    css = read_css()
    assert "grid-template-columns: 44px" in css or "44px minmax" in css
    assert "bottom-collapsed" in css
