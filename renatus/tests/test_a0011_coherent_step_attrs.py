"""A0011 — attributs YAML coherents par type (zone sans file, etc.)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.pipeline.steps import create_step
from renatus.pipeline.steps.control import IterationStep
from renatus.pipeline.steps.org import ZoneStep
from renatus.pipeline.steps.python_action import ExecutePythonStep
from renatus.pipeline.steps.relation import DataframeStep, TableStep, ViewStep
from renatus.pipeline.steps.shell_action import ExecuteShellStep
from renatus.pipeline.steps.sql_action import ExecuteStep

REPO = Path(__file__).resolve().parents[1]


def test_anomaly_a0011_registered():
    text = (REPO / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0011" in text


def test_zone_strips_file_and_incoherent_keys():
    step = create_step(
        "z1",
        {
            "type": "zone",
            "label": "Zone A",
            "file": "input/secret.csv",
            "script": "SELECT 1",
            "sql": "SELECT 2",
            "mode": "create_or_replace",
            "name": "rel_zone",
            "requires": ["x"],
            "venv": "/tmp/venv",
            "target": "t",
            "objects": {"t1": {}},
        },
    )
    assert isinstance(step, ZoneStep)
    cfg = step.to_config()
    assert cfg["type"] == "zone"
    assert cfg["label"] == "Zone A"
    assert cfg["objects"] == {"t1": {}}
    for bad in (
        "file",
        "script",
        "sql",
        "mode",
        "name",
        "requires",
        "venv",
        "target",
        "scenarios",
        "step_view",
    ):
        assert bad not in cfg, bad


def test_each_type_allow_list_rejects_foreign_keys():
    cases = [
        (
            DataframeStep,
            {
                "type": "dataframe",
                "file": "a.csv",
                "mode": "create_if_not_exists",
                "script": "X",
                "objects": {},
            },
            {"file", "mode"},
            {"script", "objects", "requires"},
        ),
        (
            TableStep,
            {
                "type": "table",
                "script": "SELECT 1",
                "mode": "create_or_replace",
                "file": "nope.csv",
                "objects": {},
            },
            {"script", "mode"},
            {"file", "objects", "venv"},
        ),
        (
            ViewStep,
            {
                "type": "view",
                "script": "SELECT 1",
                "mode": "create_or_replace",
                "file": "x",
            },
            {"script"},
            {"file", "objects"},
        ),
        (
            ExecuteStep,
            {
                "type": "execute_sql",
                "script": "DELETE FROM t",
                "file": "x",
                "mode": "create",
            },
            {"script"},
            {"file", "mode", "name"},
        ),
        (
            ExecutePythonStep,
            {
                "type": "execute_python",
                "script": "print(1)",
                "venv": ".venv",
                "file": "x",
            },
            {"script", "venv"},
            {"file", "mode", "objects"},
        ),
        (
            ExecuteShellStep,
            {"type": "execute_shell", "script": "echo hi", "file": "x"},
            {"script"},
            {"file", "mode", "venv"},
        ),
        (
            IterationStep,
            {
                "type": "iterate",
                "target": "t",
                "scenarios": "s",
                "step_view": "v",
                "file": "x",
                "objects": {},
            },
            {"target", "scenarios", "step_view"},
            {"file", "objects", "mode"},
        ),
    ]
    for cls, raw, must, must_not in cases:
        step = create_step("s", raw)
        assert isinstance(step, cls)
        cfg = step.to_config()
        for k in must:
            assert k in cfg, f"{cls.type}: missing {k}"
        for k in must_not:
            assert k not in cfg, f"{cls.type}: unexpected {k}"


def test_gui_zone_put_and_get_strip_file(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "z_bad",
                "config": {
                    "type": "zone",
                    "label": "Z",
                    "file": "input/leaked.csv",
                    "script": "SELECT 1",
                    "mode": "create_or_replace",
                    "requires": ["ghost"],
                    "objects": {},
                },
            },
        )
        assert r.status_code == 200, r.text
        st = client.get("/gui/step/z_bad").json()
        cfg = st["config"]
        assert cfg["type"] == "zone"
        assert "file" not in cfg
        assert "script" not in cfg
        assert "mode" not in cfg
        assert "requires" not in cfg
        # disque (zone = <id>.yaml a la racine flow ou sous-dossier)
        origin = st.get("file_origin")
        assert origin, "file_origin YAML attendu"
        disk = Path(origin)
        assert disk.is_file(), origin
        raw = yaml.safe_load(disk.read_text(encoding="utf-8"))
        body = raw["z_bad"]
        assert "file" not in body
        assert "script" not in body
        assert body.get("type") == "zone"


def test_ui_zone_hides_file_field():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    # ZoneStepType: file false
    assert 'super("zone")' in js or 'type: "zone"' in js
    assert "file: false" in js
    # A0011: purge champs masques
    assert "Aucun fichier selectionne" in js or "cfgFile.value = \"\"" in js
