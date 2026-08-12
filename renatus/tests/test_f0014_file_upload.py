"""
F0014 — upload fichier dataframe (picker / drag-drop cote serveur).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "main.duckdb"
    return TestClient(create_gui_app(db, pipe)), tmp_path, pipe


def test_upload_saves_under_project_input(tmp_path: Path):
    client, root, pipe = _client(tmp_path)
    with client:
        files = {
            "file": ("sales.csv", b"id,amount\n1,10\n2,20\n", "text/csv"),
        }
        r = client.post("/gui/upload?subdir=input", files=files)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["path"] == "input/sales.csv"
        dest = root / "input" / "sales.csv"
        assert dest.is_file()
        assert dest.read_bytes().startswith(b"id,amount")


def test_upload_then_dataframe_build(tmp_path: Path):
    client, root, pipe = _client(tmp_path)
    with client:
        files = {
            "file": ("people.csv", b"id,name\n1,alice\n2,bob\n", "text/csv"),
        }
        up = client.post("/gui/upload", files=files)
        assert up.status_code == 200
        rel = up.json()["path"]

        cr = client.post(
            "/gui/steps",
            json={
                "name": "df_people",
                "config": {"type": "dataframe", "file": rel},
            },
        )
        assert cr.status_code == 200, cr.text

        prev = client.get(
            "/gui/preview/df_people?limit=3&build=true"
        ).json()
        assert prev.get("ok") is True
        assert prev.get("row_count") == 2


def test_html_has_file_dropzone(tmp_path: Path):
    client, _, _ = _client(tmp_path)
    with client:
        html = client.get("/").text
        assert 'data-testid="file-dropzone"' in html
        assert 'data-testid="cfg-file-picker"' in html
        assert 'data-testid="btn-browse-file"' in html


def test_capture_referenced():
    root = Path(__file__).resolve().parents[1]
    features = (root / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0014" in features
    assert "F0014_file_field_text_only.png" in features
    cap = (
        root
        / "gestion_projet"
        / "agentic"
        / "captures"
        / "F0014_file_field_text_only.png"
    )
    assert cap.is_file()
