"""F0100 — Config view strict: edition seulement apres crayon."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0100_registered():
    assert "F0100" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_file_editor_only_when_editing():
    js = read_all_js()
    # plus de empty || editing
    assert 'toggle("show-file-editor", editing)' in js or (
        "show-file-editor" in js and "empty || editing" not in js
    )
    assert "show-file-editor" in js
    assert "updateFileFieldMode" in js


def test_html_file_display_value():
    html = read_index()
    assert 'data-testid="display-cfg-file"' in html
    assert 'data-display="cfg-file"' in html
    assert "is-presentation" in html
    assert "field-editable" in html


def test_css_file_control_hidden_unless_editing():
    css = read_css()
    assert "#field-file:not(.is-editing) .field-control-file" in css
    assert "display: none !important" in css
    # presentation globale
    assert ".config-form.is-presentation .field-editable:not(.is-editing) .field-control" in css


def test_f0047_still_presentation():
    html = read_index()
    assert "is-presentation" in html
    assert "btn-pencil" in html
