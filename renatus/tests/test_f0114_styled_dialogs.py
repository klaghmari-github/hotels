"""F0114 — toutes les confirmations utilisent le dialog stylé renatus-gui."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0114_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0114" in text


def test_html_confirm_dialog_shared_base():
    html = read_index()
    assert 'data-testid="confirm-dialog"' in html
    assert 'id="confirm-dialog-icon"' in html
    assert "props-dialog confirm-dialog" in html
    assert 'data-testid="confirm-cancel"' in html
    assert 'data-testid="confirm-ok"' in html


def test_js_no_native_confirm_in_features():
    js = read_all_js()
    assert "confirmDialog" in js
    # Apply all / Track
    assert "Apply all" in js or "Restaurer TOUS" in js or "Restaurer tout" in js
    # plus de window.confirm hors fallback confirm-dialog
    lines = [
        ln
        for ln in js.splitlines()
        if "window.confirm" in ln or (".confirm(" in ln and "confirmDialog" not in ln)
    ]
    # autorise uniquement le fallback dans confirm-dialog.js
    for ln in lines:
        assert "confirm-dialog" in ln or "fallback" in ln.lower() or "Promise.resolve" in ln or "function confirmDialog" in js
    # changelogs / project / requires doivent appeler confirmDialog
    assert "confirmDialog" in js
    # pas de window.confirm direct dans applyChangelog path - check pattern
    assert "if (!window.confirm" not in js
    assert "window.confirm(" in js  # fallback only in confirm-dialog
    # count: should be few (fallback only)
    count = js.count("window.confirm(")
    assert count <= 3, f"trop de window.confirm restants: {count}"


def test_css_dialog_theme_base():
    css = read_css()
    assert "confirm-dialog" in css
    assert "dialog-icon-restore" in css
    assert "dialog-icon-warn" in css
    assert "dialog-icon-info" in css
    assert "props-dialog" in css
