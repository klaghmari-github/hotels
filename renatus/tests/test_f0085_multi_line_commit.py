"""F0085 — multi-ligne: Ctrl+Enter ou blur → commit + save (Enter = newline)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0085_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0085" in text


def test_js_multiline_ctrl_enter_and_blur():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "isMultiLineControl" in js
    assert "isFieldEditControl" in js
    assert "TEXTAREA" in js
    # Ctrl/Cmd+Enter
    assert "ctrlKey" in js
    assert "metaKey" in js
    # commit partage avec mono
    assert "commitEditField" in js
    assert "flushAutoSave" in js
    # focusout couvre multi-ligne (isFieldEditControl)
    assert "focusout" in js


def test_html_script_title_mentions_ctrl_enter():
    from tests.helpers.static_sources import read_index

    html = read_index()
    assert 'data-testid="cfg-script"' in html
    # aide utilisateur
    assert "Ctrl+Entr" in html or "Ctrl+Enter" in html or "ctrl" in html.lower()
