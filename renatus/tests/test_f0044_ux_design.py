"""
F0044 — polish design UX GUI (tokens, panels, tools, tabs, empty states).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
DOC = REPO / "doc" / "UX_GUI_F0044.md"


def test_feature_f0044_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0044" in features


def test_design_tokens_and_audit_doc():
    css = CSS.read_text(encoding="utf-8")
    assert "--accent-soft" in css
    assert "--space-3" in css
    assert "F0044" in css
    assert ".btn.icon" in css
    assert ".tool::before" in css
    assert DOC.is_file()
    doc = DOC.read_text(encoding="utf-8")
    assert "Topbar" in doc
    assert "Graphe" in doc or "Flux" in doc


def test_html_empty_and_icon_buttons():
    html = INDEX.read_text(encoding="utf-8")
    # A0009: plus de "Pipeline vide" dans le Flux
    assert "Pipeline vide" not in html
    # boutons icone (collapse panels F0076): classes btn + ghost + icon
    assert "btn ghost icon" in html
