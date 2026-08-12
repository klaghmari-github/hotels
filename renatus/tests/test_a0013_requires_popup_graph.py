"""A0013 — popup Requires OK → persist + aretes Flux a jour."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js

REPO = Path(__file__).resolve().parents[1]


def test_anomaly_a0013_registered():
    text = (REPO / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0013" in text


def test_js_close_requires_persists_and_refreshes_graph():
    js = read_all_js()
    assert "closeRequiresEditor" in js
    assert "refreshGraph" in js
    assert "persistCurrentStep" in js
    assert "refreshGraph: true" in js or "refreshGraph:true" in js
    # miroir prioritaires a la persist
    assert "getSelectedRequires" in js


def test_put_requires_updates_graph_edges(tmp_path: Path):
    """PUT requires → graphe expose arete dep → step."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "g.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "src_a",
                    "config": {
                        "type": "table",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": "SELECT 1 AS n",
                    },
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "child_b",
                    "config": {
                        "type": "view",
                        "mode": "create_or_replace",
                        "requires": [],
                        "script": "SELECT n FROM src_a",
                    },
                },
            ).status_code
            == 200
        )
        g0 = client.get("/gui/graph?tab=main").json()
        edges0 = {
            (e.get("from") or e.get("from_"), e["to"]) for e in g0["edges"]
        }
        assert ("src_a", "child_b") not in edges0

        # simule OK popup: PUT requires
        r = client.put(
            "/gui/step/child_b",
            json={
                "config": {
                    "type": "view",
                    "label": "child_b",
                    "mode": "create_or_replace",
                    "requires": ["src_a"],
                    "script": "SELECT n FROM src_a",
                }
            },
        )
        assert r.status_code == 200, r.text

        g1 = client.get("/gui/graph?tab=main").json()
        edges1 = {
            (e.get("from") or e.get("from_"), e["to"]) for e in g1["edges"]
        }
        assert ("src_a", "child_b") in edges1

        # disque
        raw = yaml.safe_load(
            (pipe / "default" / "child_b.yaml").read_text(encoding="utf-8")
        )
        assert raw["child_b"]["requires"] == ["src_a"]
