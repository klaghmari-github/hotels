"""A0012 — champs config [hidden] respectes + label Name (sans SQL)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_anomaly_a0012_registered():
    text = (REPO / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0012" in text


def test_css_field_hidden_not_overridden_by_grid():
    css = read_css()
    assert ".config-form .field[hidden]" in css
    assert "display: none !important" in css


def test_name_label_without_sql_suffix():
    html = read_index()
    assert 'for="cfg-relation-name">Name</label>' in html or ">Name</label>" in html
    assert "Name (SQL)" not in html
    # champ toujours present (cache pour zone)
    assert 'id="field-relation-name"' in html
    assert "hidden" in html  # field starts hidden


def test_zone_hides_relation_name_file_and_mode():
    js = read_all_js()
    css = read_css()
    html = read_index()
    # ZoneStepType force hide
    assert "fieldRelationName" in js
    assert 'super("zone")' in js or 'type: "zone"' in js
    # visibility file/relation/mode false pour zone
    assert "relationName: false" in js or "fieldRelationName" in js
    assert "mode: false" in js
    # Mode champ present mais cache pour zone
    assert 'id="field-mode"' in html
    # F0119: mode aussi pour dataframe
    assert 'data-for-types="dataframe,table,view"' in html
    # CSS defense en profondeur pour zone
    assert 'data-step-type="zone"] #field-mode' in css
    assert "data-step-type" in js
