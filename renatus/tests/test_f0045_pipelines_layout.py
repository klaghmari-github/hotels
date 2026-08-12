"""
F0045 — layout pipelines : zone = sous-dossier, objet = fichier YAML.

  projet/
    pipelines/           # cree avec le projet
      a.yaml             # zone main
      etl/               # zone
        b.yaml           # objet
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0045_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0045" in features


def test_ui_zone_wording():
    html = (
        REPO / "src" / "renatus" / "gui" / "static" / "index.html"
    ).read_text(encoding="utf-8")
    assert "Nouvelle zone" in html
    # F0066: dialog zone sans paragraphe pipelines/ — label + input
    assert 'data-testid="new-tab-dialog"' in html
    assert 'data-testid="new-tab-name"' in html


def test_project_create_zone_object_filesystem(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    boot = tmp_path / "boot"
    boot.mkdir()
    client = TestClient(create_gui_app(tmp_path / "b.duckdb", boot))
    root = tmp_path / "proj"
    with client:
        cr = client.post(
            "/gui/project/create",
            json={
                "path": str(root),
                "name": "proj",
                "pipeline_path": "flow",
            },
        )
        assert cr.status_code == 200, cr.text
        pipe = Path(cr.json()["pipeline_path"]).resolve()
        assert pipe == (root / "flow").resolve()
        assert pipe.is_dir()

        # objet en zone main → flow/default/<id>.yaml (F0082)
        r1 = client.post(
            "/gui/steps",
            json={
                "name": "obj_main",
                "tab": "default",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1",
                },
            },
        )
        assert r1.status_code == 200, r1.text
        main_file = pipe / "default" / "obj_main.yaml"
        assert main_file.is_file()
        assert list(yaml.safe_load(main_file.read_text(encoding="utf-8")).keys()) == [
            "obj_main"
        ]

        # zone = sous-dossier
        tz = client.post("/gui/tabs", json={"name": "etl"})
        assert tz.status_code == 200, tz.text
        zone_dir = pipe / "default" / "etl"
        assert zone_dir.is_dir()
        assert tz.json().get("path")
        assert "pipelines/etl" in tz.json()["message"] or "etl" in tz.json()["message"]

        # objet dans la zone → pipelines/etl/<id>.yaml
        r2 = client.post(
            "/gui/steps",
            json={
                "name": "obj_etl",
                "tab": "etl",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["obj_main"],
                    "sql": "SELECT 2",
                },
            },
        )
        assert r2.status_code == 200, r2.text
        etl_file = zone_dir / "obj_etl.yaml"
        assert etl_file.is_file()
        # pas de fichier a la racine pour cet objet
        assert not (pipe / "default" / "obj_etl.yaml").exists()

        tabs = client.get("/gui/tabs").json()["tabs"]
        by_id = {t["id"]: t for t in tabs}
        assert "default" in by_id and "default/etl" in by_id
        assert by_id["default"]["step_count"] >= 1
        assert by_id["default/etl"]["step_count"] >= 1
