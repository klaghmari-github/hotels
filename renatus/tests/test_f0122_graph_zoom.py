"""F0122 — zoom in/out dans la region Flux (graphe)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0122_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0122" in text


def test_html_zoom_controls():
    html = read_index()
    assert 'data-testid="graph-zoom-controls"' in html
    assert 'data-testid="btn-graph-zoom-in"' in html
    assert 'data-testid="btn-graph-zoom-out"' in html
    assert 'data-testid="btn-graph-zoom-reset"' in html
    assert 'data-testid="graph-zoom-label"' in html
    assert "graph-canvas-wrap" in html


def test_js_zoom_api():
    js = read_all_js()
    assert "setGraphZoom" in js
    assert "zoomGraphIn" in js
    assert "zoomGraphOut" in js
    assert "resetGraphZoom" in js
    assert "wireGraphZoom" in js
    assert "clampGraphZoom" in js
    assert "GRAPH_ZOOM_MIN" in js
    assert "GRAPH_ZOOM_MAX" in js
    assert "graphZoom" in js
    assert "viewBox" in js
    # Ctrl+molette
    assert "ctrlKey" in js
    assert "wheel" in js


def test_css_zoom_controls():
    css = read_css()
    assert ".graph-zoom-controls" in css
    assert ".graph-canvas-wrap" in css
