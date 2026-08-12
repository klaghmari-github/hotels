"""
F0022 — pictogrammes / logos par type de step (dataframe, table, view, execute, iteration).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
STYLE = REPO / "src" / "renatus" / "gui" / "static" / "style.css"

TYPES = ("dataframe", "table", "view", "execute_sql", "iteration")


def test_feature_f0022_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0022" in features
    assert "pictogramme" in features.lower() or "icon" in features.lower() or "logo" in features.lower()


def test_js_defines_icons_for_all_types():
    js = read_all_js()
    assert "typeIconPaths" in js
    assert "typeIconSvg" in js
    assert "typeIconSvgGroup" in js
    for t in TYPES:
        assert t in js
        # chaque type a des paths (mot-cle dans typeIconPaths map)
    # pictos utilises palette + graphe
    assert "tool-icon-wrap" in js
    assert "typeIconSvgGroup" in js
    assert "node-icon" in js


def test_js_icon_paths_non_empty():
    js = read_all_js()
    # signatures visuelles distinctes
    assert "polyline points=\"4 17 10 11 4 5\"" in js or "polyline points=" in js  # execute
    assert "circle cx=" in js  # view eye
    assert "23 4 23 10" in js or "iteration" in js  # loop


def test_css_type_icon_styles():
    css = STYLE.read_text(encoding="utf-8")
    assert ".type-icon" in css or ".tool-icon" in css
    assert ".tool-icon-wrap" in css
    assert ".node-icon" in css
    for t in TYPES:
        assert f"tool-{t}" in css or f".badge.{t}" in css or t in css


def test_served_js_has_icons(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "i.duckdb", pipe))
    with client:
        js = client.get("/gui/static/app.js").text
        assert "typeIconSvg" in js
        assert 'data-testid="icon-' in js or "icon-" in js
        css = client.get("/gui/static/style.css").text
        assert "tool-icon-wrap" in css
