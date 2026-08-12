"""
F0018 — panneau YAML brut en pleine largeur de la sidebar config.
"""

from __future__ import annotations

from pathlib import Path


def test_css_yaml_full_width():
    root = Path(__file__).resolve().parents[1]
    css = (
        root / "src" / "renatus" / "gui" / "static" / "style.css"
    ).read_text(encoding="utf-8")
    assert ".raw-yaml" in css
    assert "#config-editor" in css
    assert "width: 100%" in css
    # pas seulement l'ancien selecteur raw-json
    assert "raw-yaml #config-editor" in css or ".raw-yaml #config-editor" in css
    # hauteur confortable (14rem historique, 16rem depuis F0020)
    assert "min-height: 14rem" in css or "min-height: 16rem" in css


def test_html_yaml_panel_testid():
    root = Path(__file__).resolve().parents[1]
    html = (
        root / "src" / "renatus" / "gui" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert "YAML" in html
    assert 'data-testid="raw-yaml-panel"' in html
    assert 'data-testid="config-yaml"' in html
    assert "JSON brut" not in html


def test_capture_and_feature():
    root = Path(__file__).resolve().parents[1]
    features = (root / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0018" in features
    assert "F0018_yaml_panel_too_narrow.png" in features
    cap = (
        root
        / "gestion_projet"
        / "agentic"
        / "captures"
        / "F0018_yaml_panel_too_narrow.png"
    )
    assert cap.is_file()
