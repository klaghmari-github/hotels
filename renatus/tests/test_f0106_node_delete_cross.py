"""F0106 — selection Flux: croix rouge supprimer + focus Annuler sur confirm."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0106_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0106" in text


def test_js_node_delete_cross():
    js = read_all_js()
    assert "node-delete-hit" in js
    assert "nodeCanShowDelete" in js or "has-delete" in js
    assert "NODE_DEL_EXTRA" in js or "node-delete" in js
    # croix → deleteStep
    assert "deleteStep" in js
    assert "node-delete" in js


def test_css_node_delete_cross():
    css = read_css()
    assert "node-delete" in css
    assert "has-delete" in css or "node-delete-hit" in css


def test_confirm_cancel_default_focus():
    html = read_index()
    assert 'data-testid="confirm-cancel"' in html
    # Annuler avant Supprimer dans le DOM + autofocus
    idx_cancel = html.find("confirm-cancel")
    idx_ok = html.find("confirm-ok")
    assert idx_cancel > 0 and idx_ok > 0
    assert idx_cancel < idx_ok
    assert "autofocus" in html
    js = read_all_js()
    assert "focusCancel" in js or "cancelBtn.focus" in js
    assert "autofocus" in js
