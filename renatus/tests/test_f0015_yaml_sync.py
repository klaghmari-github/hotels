"""
F0015 — YAML brut + sync config formulaire / YAML.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from tests.helpers.static_sources import read_all_js


def test_config_to_yaml_and_back():
    from renatus.gui.service import GuiService

    config = {
        "type": "dataframe",
        "file": "input/sales.csv",
    }
    text = GuiService.config_to_yaml(config)
    assert "type: dataframe" in text
    assert "file: input/sales.csv" in text
    assert "{" not in text  # pas du JSON

    back = GuiService.yaml_to_config(text)
    assert back["type"] == "dataframe"
    assert back["file"] == "input/sales.csv"


def test_yaml_roundtrip_table_requires():
    from renatus.gui.service import GuiService

    config = {
        "type": "table",
        "mode": "create_or_replace",
        "requires": ["df_sales"],
        "sql": "SELECT * FROM df_sales",
    }
    text = GuiService.config_to_yaml(config)
    back = GuiService.yaml_to_config(text)
    assert back == config


def test_api_to_yaml_from_yaml(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "x.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/config/to-yaml",
            json={"config": {"type": "view", "sql": "SELECT 1", "requires": []}},
        )
        assert r.status_code == 200, r.text
        yml = r.json()["yaml"]
        assert "type: view" in yml

        r2 = client.post(
            "/gui/config/from-yaml",
            json={"yaml": "type: dataframe\nfile: input/a.csv\n"},
        )
        assert r2.status_code == 200
        assert r2.json()["config"]["type"] == "dataframe"
        assert r2.json()["config"]["file"] == "input/a.csv"


def test_html_yaml_not_json(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "x.duckdb", pipe))
    with client:
        html = client.get("/").text
        assert "YAML" in html
        assert "JSON brut" not in html
        assert 'data-testid="config-yaml"' in html
        assert "js-yaml.min.js" in html


def test_js_yaml_static_served(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "x.duckdb", pipe))
    with client:
        r = client.get("/gui/static/js-yaml.min.js")
        assert r.status_code == 200
        assert len(r.content) > 1000


def test_capture_and_feature_ref():
    root = Path(__file__).resolve().parents[1]
    features = (root / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0015" in features
    assert "F0015_json_brut_desync.png" in features
    cap = (
        root
        / "gestion_projet"
        / "agentic"
        / "captures"
        / "F0015_json_brut_desync.png"
    )
    assert cap.is_file()


def test_app_js_uses_yaml_sync():
    root = Path(__file__).resolve().parents[1]
    js = read_all_js()
    assert "configToYaml" in js or "jsyaml" in js or "yamlLib" in js
    assert "JSON.stringify" not in js or "formToYamlEditor" in js
    assert "formToYamlEditor" in js
    assert "yamlEditorToForm" in js
