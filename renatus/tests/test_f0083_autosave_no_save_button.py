"""F0083 — autosave GUI, plus de bouton Sauver config."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0083_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0083" in text


def test_html_no_save_button():
    from tests.helpers.static_sources import read_index

    html = read_index()
    assert 'id="btn-save"' not in html
    assert 'data-testid="btn-save"' not in html
    # F0086: Supprimer / Renatus Config aussi retires
    assert 'id="btn-delete"' not in html
    assert 'id="btn-build"' not in html
    # Renatus View + Sauver projet restent
    assert 'btn-dv-build' in html
    assert 'btn-project-save' in html


def test_js_autosave_wiring():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "scheduleAutoSave" in js
    assert "flushAutoSave" in js
    assert "persistCurrentStep" in js
    assert "AUTO_SAVE" in js or "autoSave" in js or "450" in js
    # Ctrl+S flush, pas click btn-save
    assert "flushAutoSave" in js
    assert 'key === "s"' in js or "key === 's'" in js


def test_put_still_persists_without_gui_save(tmp_path: Path):
    """Backend: PUT reste le mecanisme d autosave (API inchangee)."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "t_auto",
                "tab": "default",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                },
            },
        )
        assert r.status_code == 200, r.text
        r2 = client.put(
            "/gui/step/t_auto",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 99 AS n",
                    "label": "Auto",
                }
            },
        )
        assert r2.status_code == 200, r2.text
        raw = yaml.safe_load(
            (pipe / "default" / "t_auto.yaml").read_text(encoding="utf-8")
        )
        assert "SELECT 99" in raw["t_auto"]["script"]
        assert raw["t_auto"]["label"] == "Auto"
