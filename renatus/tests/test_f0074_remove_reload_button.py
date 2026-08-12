"""F0074 — plus de bouton Recharger dans View."""

from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0074_registered():
    assert "F0074" in (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")


def test_no_reload_button_in_html():
    from tests.helpers.static_sources import read_index
    html = read_index()
    assert 'id="btn-dv-reload"' not in html
    assert 'data-testid="btn-dv-reload"' not in html
    assert ">Recharger<" not in html
    assert 'id="btn-dv-build"' in html
    assert "Renatus" in html
