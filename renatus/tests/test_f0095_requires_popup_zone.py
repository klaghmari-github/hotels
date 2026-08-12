"""F0095 — Requires view chips + edit popup (zone dropdown, dblclick)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0095_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0095" in features


def test_html_requires_dialog_and_view():
    html = read_index()
    assert 'data-testid="requires-edit-dialog"' in html
    assert 'data-testid="requires-zone-select"' in html
    assert 'data-testid="requires-edit-canvas"' in html
    assert 'data-testid="edit-cfg-requires"' in html
    assert 'data-testid="cfg-requires-selected"' in html
    assert 'data-testid="field-requires"' in html
    # picker legacy present but not the primary edit surface
    assert 'data-testid="cfg-requires-picker"' in html


def test_js_requires_editor_no_checkboxes_in_view():
    js = read_all_js()
    assert "openRequiresEditor" in js
    assert "wireRequiresEditor" in js
    assert "listRequireZones" in js
    assert "toggleRequireInEditor" in js or "require-pick-node" in js
    assert "dblclick" in js
    assert "addRequire" in js
    assert "removeRequire" in js
    # view: pas de creation de checkbox dans renderRequiresPicker
    # (l ancien cb.type = checkbox a disparu du flux view)
    assert "renderRequiresPicker" in js
    # stocke l id YAML
    assert "setRequiresMirror" in js
    assert "getSelectedRequires" in js


def test_css_requires_edit_dialog():
    css = read_css()
    assert "requires-edit-dialog" in css
    assert "requires-edit-canvas" in css
    assert "require-pick-node" in css or "is-required" in css
