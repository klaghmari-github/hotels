"""
F0031 — id applicatif immutable + un YAML par composant.

- Creation: id = label initial (ex. dataframe_YYYY_MM_DD_hh_mm_ss)
- Fichier: <id>.yaml (un seul mapping)
- Label modifiable; id non modifiable
- requires reference l id
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js


def _client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    return TestClient(create_gui_app(tmp_path / "ids.duckdb", pipe)), pipe


def test_feature_f0031_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0031" in features


def test_create_writes_single_id_yaml(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        name = "dataframe_2026_08_08_10_00_00"
        r = client.post(
            "/gui/steps",
            json={
                "name": name,
                "config": {"type": "dataframe", "file": "input/a.csv"},
            },
        )
        assert r.status_code == 200, r.text
        # F0082: steps de main → flow/default/<id>.yaml
        path = pipe / "default" / f"{name}.yaml"
        assert path.is_file()
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert list(data.keys()) == [name]
        assert data[name]["type"] == "dataframe"
        assert data[name]["label"] == name
        assert data[name]["file"] == "input/a.csv"


def test_put_updates_label_keeps_id_and_filename(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        sid = "table_2026_08_08_11_00_00"
        client.post(
            "/gui/steps",
            json={
                "name": sid,
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS id",
                },
            },
        )
        r = client.put(
            f"/gui/step/{sid}",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 2 AS id",
                    "label": "Ma table",
                }
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == sid
        assert body["label"] == "Ma table"
        assert body["name"] == sid
        path = pipe / "default" / f"{sid}.yaml"
        assert path.is_file()
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert list(data.keys()) == [sid]
        assert data[sid]["label"] == "Ma table"
        assert "SELECT 2" in data[sid]["script"]


def test_put_rejects_id_change_in_config(tmp_path: Path):
    client, pipe = _client(tmp_path)
    with client:
        sid = "view_2026_08_08_12_00_00"
        client.post(
            "/gui/steps",
            json={
                "name": sid,
                "config": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS x",
                },
            },
        )
        r = client.put(
            f"/gui/step/{sid}",
            json={
                "config": {
                    "type": "view",
                    "id": "autre_id",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS x",
                }
            },
        )
        assert r.status_code == 400
        assert "id" in r.text.lower() or "modifiable" in r.text.lower()


def test_create_duplicate_id_rejected(tmp_path: Path):
    client, _ = _client(tmp_path)
    with client:
        sid = "execute_2026_08_08_13_00_00"
        cfg = {"type": "execute_sql", "requires": [], "sql": "SELECT 1"}
        assert (
            client.post(
                "/gui/steps", json={"name": sid, "config": cfg}
            ).status_code
            == 200
        )
        r2 = client.post(
            "/gui/steps", json={"name": sid, "config": cfg}
        )
        assert r2.status_code == 400


def test_get_step_exposes_id_and_label(tmp_path: Path):
    client, _ = _client(tmp_path)
    with client:
        sid = "df_x"
        client.post(
            "/gui/steps",
            json={
                "name": sid,
                "config": {
                    "type": "dataframe",
                    "file": "input/z.csv",
                    "label": "Sales",
                },
            },
        )
        g = client.get(f"/gui/step/{sid}").json()
        assert g["id"] == sid
        assert g["label"] == "Sales"
        assert g["name"] == sid


def test_graph_node_has_label(tmp_path: Path):
    client, _ = _client(tmp_path)
    with client:
        sid = "t_kpi"
        client.post(
            "/gui/steps",
            json={
                "name": sid,
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                    "label": "KPI",
                },
            },
        )
        nodes = client.get("/gui/graph?tab=main").json()["nodes"]
        by_id = {n["id"]: n for n in nodes}
        assert by_id[sid]["label"] == "KPI"


def test_legacy_multikey_extracted_on_save(tmp_path: Path):
    """Ancien YAML multi-steps: a la sauvegarde, extraction vers <id>.yaml."""
    client, pipe = _client(tmp_path)
    multi = pipe / "default" / "bundle.yaml"
    multi.write_text(
        yaml.dump(
            {
                "old_a": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS a",
                },
                "old_b": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 2 AS b",
                },
            }
        ),
        encoding="utf-8",
    )
    # reconnect to load
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    client2 = TestClient(
        create_gui_app(tmp_path / "ids2.duckdb", pipe)
    )
    with client2:
        r = client2.put(
            "/gui/step/old_a",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 9 AS a",
                    "label": "A",
                }
            },
        )
        assert r.status_code == 200, r.text
        # F0082: extraction sous flow/default/
        extracted = pipe / "default" / "old_a.yaml"
        assert extracted.is_file()
        data_a = yaml.safe_load(extracted.read_text(encoding="utf-8"))
        assert list(data_a.keys()) == ["old_a"]
        # bundle ne contient plus old_a (migre sous main/ si besoin)
        bundle = multi
        if not bundle.is_file():
            bundle = pipe / "default" / multi.name
        if bundle.is_file():
            left = yaml.safe_load(bundle.read_text(encoding="utf-8")) or {}
            assert "old_a" not in left
            assert "old_b" in left


def test_ui_has_readonly_id_field():
    html = (
        REPO / "src" / "renatus" / "gui" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert 'data-testid="cfg-id"' in html
    assert "readonly" in html
    js = read_all_js()
    assert "cfgId" in js or "cfg-id" in js
    assert "n est pas modifiable" in js or "non modifiable" in js.lower() or "immutable" in js.lower() or "label" in js
    # plus de renommage par POST create + DELETE
    assert "Step renommee" not in js


def test_yaml_store_normalize_label():
    from renatus.gui.service import YamlStepStore

    cfg = YamlStepStore.normalize_step_config(
        "df_1", {"type": "dataframe", "file": "x.csv"}
    )
    assert cfg["label"] == "df_1"
    cfg2 = YamlStepStore.normalize_step_config(
        "df_1", {"type": "dataframe", "file": "x.csv", "label": "  Sales  "}
    )
    assert cfg2["label"] == "Sales"
    assert "id" not in cfg2
