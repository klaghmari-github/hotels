"""F0081 — selection config toujours zone ou objet de la zone."""

from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0081_registered():
    assert "F0081" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_js_ensure_selection():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "ensureSelection" in js
    assert "zoneIdFromTab" in js
    assert "lastSelectedByTab" in js
    assert "lastManipulatedZone" in js
    # switchTab ne laisse plus la config vide sans fallback
    assert "ensureSelection" in js
    # F0099: fallback = zone courante (pas last object en tete)
    assert "currentZoneStepId" in js
    assert "selectCurrentZone" in js
