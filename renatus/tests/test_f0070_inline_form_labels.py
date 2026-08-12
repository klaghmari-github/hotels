"""
F0070 — labels de formulaire a cote des champs (pas au-dessus).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0070_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0070" in text


def test_css_inline_field_layout():
    from tests.helpers.static_sources import read_css, read_index

    css = read_css()
    assert "grid-template-columns" in css
    assert ".config-form .field" in css
    assert "F0070" in css or "label a gauche" in css or "minmax(5.5rem" in css
    # plus de marge sous label qui force le stack vertical
    assert ".field-head" in css
    html = read_index()
    # structure label + valeur (field-head + field-row / input)
    assert 'for="cfg-id"' in html
    assert 'for="cfg-name"' in html
    assert "field-head" in html
    assert "field-row" in html


def test_props_form_grid():
    from tests.helpers.static_sources import read_css

    css = read_css()
    assert ".props-form" in css
    assert "grid-column: 1 / -1" in css or "grid-column:1/-1" in css.replace(
        " ", ""
    )
