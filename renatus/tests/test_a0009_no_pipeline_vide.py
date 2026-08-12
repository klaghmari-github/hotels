"""A0009 — ne jamais afficher "Pipeline vide" dans le Flux."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_anomaly_a0009_registered():
    text = (REPO / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0009" in text


def test_html_no_pipeline_vide_message():
    from tests.helpers.static_sources import read_all_js, read_css, read_index

    html = read_index()
    assert "Pipeline vide" not in html
    css = read_css()
    # empty state force cache
    assert "#graph-empty" in css
    assert "display: none" in css or "display:none" in css
    js = read_all_js()
    assert "graphEmpty" in js
