"""F0099 — clic fond Flux + fallback = zone courante (pas dernier objet)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0099_registered():
    assert "F0099" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_js_select_current_zone_and_background_click():
    js = read_all_js()
    assert "selectCurrentZone" in js
    assert "currentZoneStepId" in js
    assert "wireGraphBackgroundSelect" in js
    # clic noeud stopPropagation
    assert "stopPropagation" in js
    # ensureSelection priorise zone courante
    assert "currentZoneStepId" in js
    # main → zone main
    assert 'return "default"' in js or "return 'default'" in js


def test_f0081_still_has_ensure_selection():
    js = read_all_js()
    assert "ensureSelection" in js
    assert "zoneIdFromTab" in js
