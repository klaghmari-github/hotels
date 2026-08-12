"""A0010 — delete retire l id des requires des dependants; load heale les orphelins."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.pipeline.engine import ConnectionPipeline

REPO = Path(__file__).resolve().parents[1]


def test_anomaly_a0010_registered():
    text = (REPO / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0010" in text


def test_delete_removes_from_dependents_requires(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "src",
                    "tab": "default",
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
                    "name": "child",
                    "tab": "default",
                    "config": {
                        "type": "view",
                        "mode": "create_or_replace",
                        "requires": ["src"],
                        "script": "SELECT n FROM src",
                    },
                },
            ).status_code
            == 200
        )
        r = client.delete("/gui/step/src")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "child" in (body.get("detached_from") or [])

        child_yaml = pipe / "default" / "child.yaml"
        assert child_yaml.is_file()
        raw = yaml.safe_load(child_yaml.read_text(encoding="utf-8"))
        assert raw["child"].get("requires") in ([], None) or "src" not in (
            raw["child"].get("requires") or []
        )

        # projet reste chargeable
        g = client.get("/gui/graph?tab=*")
        assert g.status_code == 200
        ids = {n["id"] for n in g.json()["nodes"]}
        assert "child" in ids
        assert "src" not in ids


def test_load_heals_orphan_requires(tmp_path: Path):
    pipe = tmp_path / "flow"
    main = pipe / "default"
    main.mkdir(parents=True)
    (main / "child.yaml").write_text(
        "child:\n  type: table\n  mode: create_or_replace\n"
        "  requires:\n  - gone\n  script: SELECT 1\n",
        encoding="utf-8",
    )
    db = tmp_path / "h.duckdb"
    cp = ConnectionPipeline(str(db), str(pipe))
    assert "child" in cp.pipeline
    assert "gone" not in (cp.pipeline["child"].get("requires") or [])
    # persiste le heal
    raw = yaml.safe_load((main / "child.yaml").read_text(encoding="utf-8"))
    assert "gone" not in (raw["child"].get("requires") or [])
