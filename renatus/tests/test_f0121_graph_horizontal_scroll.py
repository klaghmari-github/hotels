"""F0121 — region Flux: scroll horizontal + vertical sur grands graphes."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0121_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0121" in text


def test_css_graph_allows_horizontal_scroll():
    css = read_css()
    # conteneur scrollable
    assert ".graph-canvas" in css
    assert "overflow: auto" in css or "overflow-x: auto" in css
    # SVG ne doit plus etre force a width:100% seul
    # (regle F0121: width:auto + max-width:none)
    assert "max-width: none" in css
    # l'ancien pattern qui cassait le scroll H
    # ne doit plus etre la regle unique .graph-svg { width: 100%; ... }
    assert ".graph-svg {\n  display: block;\n  width: auto;" in css or (
        "width: auto" in css and ".graph-svg" in css
    )
    # min-width 0 sur zone / canvas pour flex overflow
    assert "min-width: 0" in css


def test_html_cache_bust_css():
    html = read_index()
    assert "style.css" in html
    assert "gui-canvas" in html or "graph-canvas" in html
