"""F0142 — barre de progression pendant creation auto-zone (flat/bac/for/bid)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0142_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0142" in text


def test_js_autozone_uses_progress_dialog():
    js = (REPO / "src/renatus/gui/static/app/toolbox.js").read_text(
        encoding="utf-8"
    )
    assert "withProgress" in js
    assert "Création Flat zone" in js or "Creation Flat zone" in js or "Flat zone" in js
    assert "/gui/auto-zone" in js
    # phases apres API
    assert "refreshTabs" in js
    assert "member_count" in js or "composant" in js


def test_progress_dialog_still_present():
    html = read_index()
    assert 'data-testid="progress-dialog"' in html
    js = read_all_js()
    assert "withProgress" in js
    assert "openProgressDialog" in js


def test_cache_bust_f0142():
    # cache-bust avance avec les features suivantes (ex. F0144)
    assert "main.js?v=F" in read_index()
