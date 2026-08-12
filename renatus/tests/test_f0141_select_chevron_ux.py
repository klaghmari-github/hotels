"""F0141 — fleche / hint pour indiquer liste deroulante (Flat zone + selects)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0141_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0141" in text


def test_js_chevron_and_flat_parent_wrap():
    js = read_all_js()
    assert "rs-chevron" in js
    assert "flat-parent-select-wrap" in js or "renatus-select-wrap" in js
    assert "enhanceRenatusSelect" in js
    assert "liste deroulante" in js.lower() or "cliquer pour" in js.lower()


def test_css_chevron_and_flat_parent():
    css = read_css()
    assert ".rs-chevron" in css
    assert "flat-parent" in css
    assert "rotate(180deg)" in css


def test_cache_bust_f0141():
    assert "F0141" in read_index()
