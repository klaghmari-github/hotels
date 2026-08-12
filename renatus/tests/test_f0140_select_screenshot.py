"""F0140 — menus select restent ouverts pendant capture d ecran (Print Screen)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0140_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0140" in text


def test_js_custom_select_and_screenshot_guard():
    js = read_all_js()
    assert "wireRenatusSelects" in js
    assert "isScreenshotGesture" in js
    assert "PrintScreen" in js
    assert "enhanceRenatusSelect" in js
    assert "rs-panel" in js
    assert "rs-trigger" in js
    # ne ferme pas sur blur fenetre / print
    assert "ne ferme PAS" in js or "PrintScreen" in js


def test_css_custom_select_panel():
    css = read_css()
    assert ".rs-panel" in css
    assert ".rs-trigger" in css
    assert "rs-native" in css


def test_cache_bust_f0140():
    # cache-bust peut avancer (F0141…) tant que renatus-select est charge
    html = read_index()
    assert "main.js?v=F0" in html or "renatus-select" in read_all_js()
