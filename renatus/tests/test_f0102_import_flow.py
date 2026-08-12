"""F0102 — importer flux (fichier ou dossier) dans une zone."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0102_registered():
    assert "F0102" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_ui_import_flow_button_and_dialog():
    html = read_index()
    assert 'data-testid="btn-import-flow"' in html
    assert 'data-testid="import-flow-dialog"' in html
    assert 'data-testid="import-flow-source"' in html
    assert 'data-testid="import-flow-target"' in html
    assert 'data-testid="import-flow-conflict"' in html
    js = read_all_js()
    assert "openImportFlowDialog" in js
    assert "wireImportFlow" in js
    assert "/gui/import/flow" in js


def _seed_pipe(pipe: Path) -> None:
    pipe.mkdir(parents=True, exist_ok=True)
    (pipe / "default").mkdir(exist_ok=True)
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "default" / "t_exist.yaml").write_text(
        yaml.dump(
            {
                "t_exist": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                }
            }
        ),
        encoding="utf-8",
    )


def test_import_single_file(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed_pipe(pipe)
    src = tmp_path / "extra.yaml"
    src.write_text(
        yaml.dump(
            {
                "extra": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 2 AS x",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(src),
                "target_tab": "default",
                "conflict": "keep_both",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1
        assert any(i["id"] == "extra" for i in body["imported"])
        st = client.get("/gui/step/extra").json()
        assert st["config"]["type"] == "view"


def test_import_directory_tree_and_conflict_keep_both(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed_pipe(pipe)
    src = tmp_path / "d1"
    (src / "d2").mkdir(parents=True)
    (src / "d3").mkdir(parents=True)
    (src / "d2" / "t_exist.yaml").write_text(
        yaml.dump(
            {
                "t_exist": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 9 AS n",
                }
            }
        ),
        encoding="utf-8",
    )
    (src / "d3" / "v_new.yaml").write_text(
        yaml.dump(
            {
                "v_new": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": ["t_exist"],
                    "script": "SELECT n FROM t_exist",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", pipe))
    with client:
        dry = client.post(
            "/gui/import/flow",
            json={
                "source": str(src),
                "target_tab": "default",
                "conflict": "keep_both",
                "dry_run": True,
            },
        ).json()
        assert dry["count"] == 2
        # conflit existant + multi-fichiers → prefixe stem fichier (F0103)
        mapped = dry["id_map"]["t_exist"]
        assert mapped != "t_exist"
        assert mapped in {"t_exist_2", "t_exist_t_exist"} or mapped.startswith(
            "t_exist"
        )
        assert "d1/d2" in dry["zone_tabs"]
        assert "d1/d3" in dry["zone_tabs"]

        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(src),
                "target_tab": "default",
                "conflict": "keep_both",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 2
        final_t = body["id_map"]["t_exist"]
        # arborescence
        assert (pipe / "default" / "d1" / "d2" / f"{final_t}.yaml").is_file()
        assert (pipe / "default" / "d1" / "d3" / "v_new.yaml").is_file()
        # requires remappees
        raw = yaml.safe_load(
            (pipe / "default" / "d1" / "d3" / "v_new.yaml").read_text(encoding="utf-8")
        )
        assert raw["v_new"]["requires"] == [final_t]
        # existant preserve
        assert (pipe / "default" / "t_exist.yaml").is_file()


def test_import_conflict_keep_existing(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed_pipe(pipe)
    src = tmp_path / "t_exist.yaml"
    src.write_text(
        yaml.dump(
            {
                "t_exist": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 99 AS n",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "c.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(src),
                "target_tab": "default",
                "conflict": "keep_existing",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["count"] == 0
        raw = yaml.safe_load(
            (pipe / "default" / "t_exist.yaml").read_text(encoding="utf-8")
        )
        assert "SELECT 1" in raw["t_exist"]["script"]


def test_import_zones_endpoint(tmp_path: Path):
    pipe = tmp_path / "flow"
    _seed_pipe(pipe)
    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        r = client.get("/gui/import/zones")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        ids = {z["id"] for z in data["zones"]}
        assert "default" in ids


def test_import_splits_multikey_yaml_one_file_per_object(tmp_path: Path):
    """F0103: un YAML multi-cles → N fichiers monocomposants."""
    pipe = tmp_path / "flow"
    _seed_pipe(pipe)
    src = tmp_path / "bundle.yaml"
    src.write_text(
        yaml.dump(
            {
                "t_a": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS a",
                },
                "t_b": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["t_a"],
                    "script": "SELECT a FROM t_a",
                },
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "e.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(src),
                "target_tab": "default",
                "conflict": "keep_both",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 2
        assert body.get("split_objects") == 2 or body["count"] == 2
        # un fichier par objet
        assert (pipe / "default" / "t_a.yaml").is_file()
        assert (pipe / "default" / "t_b.yaml").is_file()
        raw_b = yaml.safe_load(
            (pipe / "default" / "t_b.yaml").read_text(encoding="utf-8")
        )
        assert list(raw_b.keys()) == ["t_b"]
        assert raw_b["t_b"]["requires"] == ["t_a"]


def test_import_prefix_on_cross_file_id_conflict(tmp_path: Path):
    """Plusieurs fichiers avec le meme id → prefixe stem du fichier source."""
    pipe = tmp_path / "flow"
    _seed_pipe(pipe)
    d = tmp_path / "pack"
    d.mkdir()
    (d / "alpha.yaml").write_text(
        yaml.dump(
            {
                "shared": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                }
            }
        ),
        encoding="utf-8",
    )
    (d / "beta.yaml").write_text(
        yaml.dump(
            {
                "shared": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 2 AS n",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "f.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(d),
                "target_tab": "default",
                "conflict": "keep_both",
            },
        )
        assert r.status_code == 200, r.text
        ids = {i["id"] for i in r.json()["imported"]}
        # un shared libre, l autre prefixe beta_shared ou renomme
        assert "shared" in ids or any("shared" in i for i in ids)
        assert len(ids) == 2
        # fichiers monocomposants
        yaml_files = list((pipe / "default" / "pack").rglob("*.yaml")) if (pipe / "default" / "pack").exists() else []
        # dest sous pack/... car dossier pack
        all_yaml = list(pipe.rglob("*.yaml"))
        stems = {p.stem for p in all_yaml}
        assert len(ids & stems) == 2
