"""F0135 — liens graphe orthogonaux (H/V) sans traverser les composants."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0135_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0135" in text


def test_js_orthogonal_routing_api():
    js = (REPO / "src/renatus/gui/static/app/graph.js").read_text(encoding="utf-8")
    assert "routeOrthogonalEdge" in js
    assert "buildNodeBoxes" in js
    assert "pathHitsNodes" in js
    assert "segmentHitsBox" in js
    assert "pointsToSvgPath" in js
    # plus de bezier C dans le rendu des edges (routage L only)
    # (le path d arrow marker peut encore avoir L)
    assert "edge-ortho" in js
    assert "F0135" in js
    # l ancien pattern de courbe pour edges ne doit plus etre le defaut
    assert ' " C" +' not in js and '" C"+' not in js


def test_js_exported_helpers_in_bundle():
    js = read_all_js()
    assert "routeOrthogonalEdge" in js
    assert "pathHitsNodes" in js


def test_css_edge_ortho():
    css = read_css()
    assert "stroke-linejoin" in css
    assert ".edge" in css


def test_cache_bust_f0135():
    assert "F0135" in read_index()
