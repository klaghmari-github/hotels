"""
F0066 — Required by + UI sans micro-textes descriptifs.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0066_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0066" in text


def test_required_by_label_and_no_field_hints():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert "Required by" in html
    assert "Utilise par" not in html
    # plus de paragraphes field-hint dans le HTML config
    assert "requires-hint" not in html
    assert "dependents-hint" not in html
    assert "zones-hint" not in html
    assert "name-hint" not in html
    assert "sql-name-hint" not in html
    assert "script-hint" not in html
    assert "venv-hint" not in html
    assert "zone-objects-hint" not in html
    assert "new-tab-hint" not in html
    # empty states sobres
    assert "Aucun composant ne reference celui-ci" not in html
    assert "Pipeline vide —" not in html

    js = read_all_js()
    assert "Aucun composant disponible (ajoutez" not in js
    assert "Aucun composant dans le projet (ajoutez" not in js


def test_css_hides_field_hints():
    from tests.helpers.static_sources import read_css

    css = read_css()
    assert ".field-hint" in css
    assert "display: none" in css
