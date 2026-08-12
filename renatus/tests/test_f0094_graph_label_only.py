"""F0094 — noeuds graphe: label + logo uniquement (pas de sous-texte)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0094_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0094" in features


def test_graph_renders_label_only_no_ntype():
    js = read_all_js()
    # label always present
    assert 'class="nname"' in js
    # F0094: plus de sous-ligne descriptive dans le SVG
    assert 'class="ntype"' not in js
    assert "shortType" not in js
    # tooltip conserve le detail type/SQL
    assert "<title>" in js
    assert "tipDetail" in js or "fullType" in js or "relation_name" in js


def test_css_no_ntype_rule():
    css = read_css()
    assert ".node .nname" in css
    # ancienne regle sous-texte retiree
    assert ".node .ntype" not in css
