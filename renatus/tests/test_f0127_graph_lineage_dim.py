"""F0127 — selection graphe: grise hors lineage (requires recursifs)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0127_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0127" in text


def test_js_lineage_highlight():
    js = read_all_js()
    assert "computeLineageSet" in js
    assert "applyLineageHighlight" in js
    assert "lineage-dim" in js
    assert "lineage-focus" in js
    # appele apres render
    assert "applyLineageHighlight()" in js


def test_js_zone_selection_no_dim_f0134():
    """F0134: zone selectionnee → pas de grise des membres."""
    js = (REPO / "src/renatus/gui/static/app/graph.js").read_text(encoding="utf-8")
    assert "selectionIsZoneLike" in js
    assert "F0134" in js
    # branche zone: clearAll / return sans dim
    assert 't === "zone"' in js or '=== "zone"' in js


def test_css_lineage_dim():
    css = read_css()
    assert ".node.lineage-dim" in css
    assert ".edge.lineage-dim" in css
    assert ".edge.lineage-focus" in css
    assert "grayscale" in css
