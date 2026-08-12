"""F0086 — Config sans boutons Supprimer / Sauver / Renatus."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0086_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0086" in text


def test_html_config_no_action_buttons():
    from tests.helpers.static_sources import read_index

    html = read_index()
    assert 'id="btn-delete"' not in html
    assert 'id="btn-save"' not in html
    assert 'id="btn-build"' not in html
    assert 'data-testid="btn-delete"' not in html
    assert 'data-testid="btn-save"' not in html
    assert 'data-testid="btn-build"' not in html
    # collapse config reste
    assert 'id="btn-collapse-config"' in html
    # Renatus reste dans View
    assert 'data-testid="btn-dv-build"' in html
    # Sauver projet topbar reste
    assert 'btn-project-save' in html


def test_js_shortcuts_without_config_buttons():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    # Delete clavier
    assert 'key === "Delete"' in js or "key === 'Delete'" in js
    assert "deleteStep" in js
    # Ctrl+B appelle buildStep directement
    assert "buildStep" in js
    assert 'key === "b"' in js or "key === 'b'" in js
    # main protegee cote raccourci
    assert '!== "default"' in js or "!== 'default'" in js
