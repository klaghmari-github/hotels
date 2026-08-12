"""
F0029 — polish UX GUI (design, ergonomie, composants graphiques).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"
HTML = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"


def test_feature_f0029_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0029" in features


def test_css_design_system_tokens():
    css = CSS.read_text(encoding="utf-8")
    for token in (
        "--accent-glow",
        "--focus",
        "--shadow",
        "--radius",
        "focus-visible",
        "toast-in",
        "scrollbar",
    ):
        assert token in css, token


def test_css_button_hierarchy():
    css = CSS.read_text(encoding="utf-8")
    assert ".btn.primary" in css
    assert ".btn.danger" in css
    assert "linear-gradient" in css
    assert "transition" in css


def test_html_toolbar_and_titles():
    html = HTML.read_text(encoding="utf-8")
    assert "toolbar-sep" in html
    # F0086: plus de boutons actions Config; Sauver projet + Renatus View restent
    assert 'data-testid="btn-save"' not in html
    assert 'data-testid="btn-delete"' not in html
    assert 'data-testid="btn-build"' not in html
    assert 'data-testid="btn-project-save"' in html
    assert 'data-testid="btn-dv-build"' in html
    assert 'data-testid="pipeline-tabs"' in html
    assert 'data-testid="cfg-requires-picker"' in html
    assert "<h2>Flux</h2>" in html or "<h2>Graphe</h2>" in html
    assert "<h2>Composant</h2>" in html or "<h2>Outils</h2>" in html
    assert (
        "DataView" in html
        or "Data preview" in html
        or ">View<" in html
        or "tab-data-preview" in html
    )
    # Renatus reste dans View (F0061)
    assert ">Renatus<" in html or "Renatus</button>" in html


def test_js_keyboard_shortcuts():
    js = read_all_js()
    assert "keydown" in js
    assert "ctrlKey" in js or "metaKey" in js
    # Ctrl+S (flush autosave) / Ctrl+B (Renatus) / Delete
    assert 'key === "s"' in js or "key === 's'" in js
    assert "flushAutoSave" in js
    assert 'key === "b"' in js or "key === 'b'" in js
    assert "buildStep" in js
    assert 'key === "Delete"' in js or "key === 'Delete'" in js


def test_js_toast_visible():
    js = read_all_js()
    assert "classList.remove" in js and "hidden" in js
    assert "function toast" in js


def test_served_css_has_ux_polish(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "u.duckdb", pipe))
    with client:
        css = client.get("/gui/static/style.css").text
        assert "--accent-glow" in css
        assert "focus-visible" in css
        html = client.get("/").text
        assert "toolbar-sep" in html
        assert "pipeline-tabs" in html
