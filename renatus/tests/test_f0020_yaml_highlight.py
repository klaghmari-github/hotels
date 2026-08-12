"""
F0020 — YAML GUI: coloration cles/valeurs, erreurs parsing, pleine largeur.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
STYLE = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


def test_feature_f0020_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0020" in features
    assert "highlight" in features.lower() or "color" in features.lower() or "pars" in features.lower()


def test_html_yaml_editor_structure():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-testid="yaml-editor"' in html
    assert 'data-testid="yaml-highlight"' in html
    assert 'data-testid="config-yaml"' in html
    assert 'data-testid="yaml-status"' in html
    assert 'id="yaml-highlight"' in html
    assert 'id="config-editor"' in html
    # plus de cols=40 qui bridait la largeur
    assert 'cols="40"' not in html
    assert "YAML" in html


def test_css_tokens_and_full_width():
    css = STYLE.read_text(encoding="utf-8")
    # tokens
    assert ".y-key" in css
    assert ".y-string" in css
    assert ".y-number" in css
    assert ".y-bool" in css
    assert ".y-comment" in css
    # editor dual-layer
    assert ".yaml-editor" in css
    assert ".yaml-highlight" in css
    assert "color: transparent" in css or "-webkit-text-fill-color: transparent" in css
    # pleine largeur sidebar (negative margin sort du padding form)
    assert ".raw-yaml" in css
    assert "margin:" in css or "margin-left" in css
    assert "width: 100%" in css or "width: auto" in css
    # etat erreur
    assert ".yaml-editor.is-error" in css or "is-error" in css
    assert ".yaml-status.err" in css or "yaml-status" in css


def test_js_highlight_and_error_helpers():
    js = read_all_js()
    assert "highlightYaml" in js
    assert "highlightYamlLine" in js
    assert "updateYamlHighlight" in js
    assert "formatYamlError" in js
    assert "y-key" in js
    assert "y-string" in js
    assert "mark.line" in js
    assert "syncYamlScroll" in js
    # erreur parsing indique correction
    assert "Corrigez" in js or "corriger" in js.lower() or "ligne" in js


def test_js_yaml_error_uses_line_column():
    js = read_all_js()
    assert "ligne" in js
    assert "colonne" in js
    assert "formatYamlError" in js
    assert "yamlEditorToForm" in js
    # setYamlStatus bascule is-error
    assert "is-error" in js


def test_api_invalid_yaml_still_rejected(tmp_path: Path):
    """Backend from-yaml refuse le YAML casse (message d erreur)."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "y.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/config/from-yaml",
            json={"yaml": "type: table\n  bad: [unterminated"},
        )
        # parse casse → 400 avec message ligne/colonne (F0020)
        assert r.status_code == 400, r.text
        text = r.text.lower()
        assert "yaml" in text or "parsing" in text or "error" in text
        body = r.json()
        detail = str(body.get("detail") or body.get("error") or "")
        assert "ligne" in detail.lower() or "yaml" in detail.lower()


def test_valid_yaml_roundtrip_colored_subset(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "z.duckdb", pipe))
    with client:
        yml = "type: table\nmode: create_or_replace\nrequires:\n  - df_a\nsql: SELECT 1\n"
        r = client.post("/gui/config/from-yaml", json={"yaml": yml})
        assert r.status_code == 200, r.text
        cfg = r.json()["config"]
        assert cfg["type"] == "table"
        assert cfg["requires"] == ["df_a"]


def test_served_html_includes_highlight_layer(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "h.duckdb", pipe))
    with client:
        html = client.get("/").text
        assert "yaml-highlight" in html
        assert "yaml-editor" in html
        css = client.get("/gui/static/style.css").text
        assert ".y-key" in css
        js = client.get("/gui/static/app.js").text
        assert "highlightYaml" in js
