"""F0143 — supprimer le staging import_flow apres import reussi."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0143_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0143" in text


def _seed_project(tmp_path: Path) -> tuple[Path, Path]:
    """project_dir = tmp; flow/ + import_flow/."""
    project = tmp_path / "proj"
    flow = project / "flow"
    flow.mkdir(parents=True)
    (flow / "default").mkdir()
    (flow / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    return project, flow


def test_import_from_staging_removes_bundle(tmp_path: Path):
    project, flow = _seed_project(tmp_path)
    # staging comme apres upload dossier
    bundle = project / "import_flow" / "pack_demo_2026"
    bundle.mkdir(parents=True)
    (bundle / "t_new.yaml").write_text(
        yaml.dump(
            {
                "t_new": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(project / "db.duckdb", flow))
    with client:
        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(bundle),
                "target_tab": "default",
                "conflict": "keep_both",
                "dry_run": False,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("count", 0) >= 1
        cleaned = body.get("staging_cleaned") or {}
        assert cleaned.get("ok") is True
        assert "pack_demo_2026" in str(cleaned.get("path") or "")
        # bundle supprime
        assert not bundle.exists()
        # composant bien dans flow
        assert any(flow.rglob("t_new.yaml"))


def test_import_outside_staging_not_deleted(tmp_path: Path):
    """Source hors import_flow (fichier utilisateur) reste intacte."""
    project, flow = _seed_project(tmp_path)
    external = tmp_path / "external_src"
    external.mkdir()
    (external / "ext.yaml").write_text(
        yaml.dump(
            {
                "ext": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 2 AS x",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(project / "db.duckdb", flow))
    with client:
        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(external),
                "target_tab": "default",
                "conflict": "keep_both",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json().get("staging_cleaned") is None
        assert external.exists()
        assert (external / "ext.yaml").is_file()


def test_dry_run_does_not_cleanup(tmp_path: Path):
    project, flow = _seed_project(tmp_path)
    bundle = project / "import_flow" / "dry_bundle"
    bundle.mkdir(parents=True)
    (bundle / "z.yaml").write_text(
        yaml.dump(
            {
                "z": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 0 AS z",
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(project / "db.duckdb", flow))
    with client:
        r = client.post(
            "/gui/import/flow",
            json={
                "source": str(bundle),
                "target_tab": "default",
                "dry_run": True,
            },
        )
        assert r.status_code == 200
        assert r.json().get("dry_run") is True
        assert bundle.exists()
