"""F0097 — zone Objects: view chips + edit popup (dropdown zone, dblclick)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0097_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0097" in features


def test_html_zone_objects_dialog_and_view():
    html = read_index()
    assert 'data-testid="zone-objects-edit-dialog"' in html
    assert 'data-testid="zone-objects-zone-select"' in html
    assert 'data-testid="zone-objects-edit-canvas"' in html
    assert 'data-testid="edit-cfg-zone-objects"' in html
    assert 'data-testid="cfg-zone-objects-selected"' in html
    assert 'data-edit-target="cfg-zone-objects"' in html
    # picker legacy cache
    assert 'data-testid="cfg-zone-objects-picker"' in html


def test_js_zone_objects_editor():
    js = read_all_js()
    assert "openZoneObjectsEditor" in js
    assert "wireZoneObjectsEditor" in js
    assert "zone-object-pick-node" in js or "toggleZoInEditor" in js
    assert "dblclick" in js
    assert "renderZoneObjectsPicker" in js
    # view: pas de checkboxes comme source de verite
    assert "getSelectedZoneObjects" in js
    assert "setZoneObjectsMirror" in js


def test_css_reuses_requires_edit_styles():
    css = read_css()
    assert "requires-edit-dialog" in css or "requires-edit-canvas" in css
