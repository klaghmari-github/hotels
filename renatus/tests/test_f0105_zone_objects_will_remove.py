"""F0105 — popup Objects: noeud grisé (will-remove) quand on retire un membre."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0105_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0105" in text


def test_js_will_remove_on_deselect():
    js = read_all_js()
    assert "will-remove" in js
    assert "markZoEditNodes" in js
    assert "zoNodeTitle" in js or "sera retire" in js
    # snapshot d ouverture pour distinguer retrait vs candidat
    assert "_zoEditSnapshot" in js
    assert "data-will-remove" in js


def test_css_will_remove_gray_style():
    css = read_css()
    assert "will-remove" in css
    assert "grayscale" in css or "opacity: 0.42" in css or "opacity:0.42" in css
