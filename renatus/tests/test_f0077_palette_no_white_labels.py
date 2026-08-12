"""F0077 — palette: pas de libelles blancs redondants."""

from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0077_registered():
    assert "F0077" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_toolbox_js_no_tool_label_html():
    from tests.helpers.static_sources import read_all_js, read_css

    js = read_all_js()
    # ne plus injecter tool-label dans le HTML des boutons
    assert "tool-label" not in js or "F0077" in js
    # badge type conserve
    assert "type-tag" in js
    assert "typeIconSvg" in js

    css = read_css()
    assert ".tool .tool-label" in css
    assert "display: none" in css
