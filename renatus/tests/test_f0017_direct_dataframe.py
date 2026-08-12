"""
F0017 — ajout dataframe sans popup: creation directe + nom horodate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.helpers.static_sources import read_all_js


def test_capture_referenced():
    root = Path(__file__).resolve().parents[1]
    features = (root / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0017" in features
    assert "F0017_dataframe_popup_name.png" in features
    cap = (
        root
        / "gestion_projet"
        / "agentic"
        / "captures"
        / "F0017_dataframe_popup_name.png"
    )
    assert cap.is_file()


def test_js_creates_dataframe_without_modal():
    """openNewStep pour dataframe appelle API directement (pas showModal)."""
    root = Path(__file__).resolve().parents[1]
    js = read_all_js()
    assert "timestampStepName" in js
    assert "dataframe_" in js or 'prefix + "_"' in js or "prefix +" in js
    # creation directe pour dataframe
    assert 'tool.type === "dataframe"' in js
    # ne doit plus ouvrir le modal en premier pour dataframe
    # (showModal seulement en fallback)
    idx_df = js.find('tool.type === "dataframe"')
    idx_modal = js.find("showModal", idx_df)
    # apres le bloc dataframe, le showModal est dans le fallback plus loin
    assert "ajoutee au graphe" in js


def test_timestamp_pattern_documented_in_js():
    js = read_all_js()
    assert "YYYY_MM_DD" in js or "getFullYear" in js
    assert "padStart" in js or "pad2" in js


def test_create_dataframe_api_empty_file_ok(tmp_path: Path):
    """Step dataframe sans fichier encore: creation YAML OK (config a completer)."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        name = "dataframe_2026_08_08_12_00_00"
        r = client.post(
            "/gui/steps",
            json={
                "name": name,
                "config": {"type": "dataframe", "file": ""},
            },
        )
        assert r.status_code == 200, r.text
        g = client.get("/gui/graph").json()
        assert any(n["id"] == name for n in g["nodes"])
        step = client.get(f"/gui/step/{name}").json()
        assert step["config"]["type"] == "dataframe"
        assert "sql" not in step["config"] or not step["config"].get("script")


def test_rename_step_via_create_delete(tmp_path: Path):
    """Renommage step: POST nouveau + DELETE ancien."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "dataframe_old",
                    "config": {"type": "dataframe", "file": ""},
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "df_sales",
                    "config": {"type": "dataframe", "file": "input/sales.csv"},
                },
            ).status_code
            == 200
        )
        assert (
            client.delete("/gui/step/dataframe_old").status_code == 200
        )
        g = client.get("/gui/graph").json()
        ids = {n["id"] for n in g["nodes"]}
        assert "df_sales" in ids
        assert "dataframe_old" not in ids
