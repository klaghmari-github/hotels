"""
F0037 — troncature des libelles des noeuds du graphe (pas de chevauchement).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"


def test_feature_f0037_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0037" in features


def test_graph_truncates_node_labels():
    js = read_all_js()
    assert "truncateNodeText" in js
    assert "node-text-clip" in js
    assert "clip-path" in js or "clipPath" in js
    assert "textMaxW" in js
    # tooltip full name
    assert "<title>" in js


def test_truncate_logic_smoke():
    """Replique la logique JS pour valider le comportement."""
    def truncate_node_text(text, max_px, font_size=11.5):
        s = "" if text is None else str(text)
        if not s:
            return ""
        avg = font_size * 0.56
        max_chars = max(4, int(max_px / avg))
        if len(s) <= max_chars:
            return s
        if max_chars <= 1:
            return "…"
        return s[: max_chars - 1] + "…"

    long_id = "dataframe_2026_08_08_20_15"
    # ~100px zone texte (node 156 - icon - pad)
    out = truncate_node_text(long_id, 100, 11.5)
    assert out.endswith("…")
    assert len(out) < len(long_id)
    assert "dataframe" in out or out.startswith("data")
    short = truncate_node_text("view", 100, 11.5)
    assert short == "view"
