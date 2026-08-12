"""F0080 — Flux sans +/refresh ; pictos Composant/Flux/Config."""

from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0080_registered():
    assert "F0080" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_no_plus_refresh_in_flux():
    from tests.helpers.static_sources import read_css, read_index

    html = read_index()
    assert 'id="btn-tab-add"' not in html
    assert 'id="btn-refresh-graph"' not in html
    assert "<h2>Flux</h2>" in html
    assert "<h2>Composant</h2>" in html
    assert "Config" in html

    css = read_css()
    assert "mask-image" in css or "-webkit-mask-image" in css
    assert ".sidebar .panel-head h2::before" in css
    assert ".graph-zone .panel-head h2::before" in css
    assert ".config-zone .panel-head h2::before" in css
