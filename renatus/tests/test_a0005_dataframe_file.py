"""
A0005 — build dataframe: file vide / xlsx / message clair.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _open(tmp_path: Path, steps: dict):
    from renatus.pipeline import ConnectionPipeline

    pipe = tmp_path / "flow"
    pipe.mkdir(parents=True, exist_ok=True)
    # F0101: un fichier <id>.yaml par step (id = stem)
    for sid, cfg in steps.items():
        (pipe / f"{sid}.yaml").write_text(
            yaml.dump({sid: cfg}, default_flow_style=False),
            encoding="utf-8",
        )
    return ConnectionPipeline(tmp_path / "t.duckdb", pipe, read_only=False)


def test_empty_file_clear_error(tmp_path: Path):
    cp = _open(
        tmp_path,
        {
            "df_x": {"type": "dataframe", "file": ""},
        },
    )
    try:
        with pytest.raises(ValueError, match="Fichier source non renseigne"):
            cp.process("df_x")
    finally:
        cp.close()


def test_missing_file_clear_error(tmp_path: Path):
    cp = _open(
        tmp_path,
        {
            "df_x": {
                "type": "dataframe",
                "file": "input/no_such.csv",
            },
        },
    )
    try:
        with pytest.raises(FileNotFoundError, match="introuvable"):
            cp.process("df_x")
    finally:
        cp.close()


def test_csv_build_ok(tmp_path: Path):
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "a.csv").write_text("id,n\n1,alice\n", encoding="utf-8")
    cp = _open(
        tmp_path,
        {
            "df_a": {
                "type": "dataframe",
                "file": "input/a.csv",
            },
        },
    )
    try:
        rel = cp.p_table_view("df_a")
        assert rel.fetchall() == [(1, "alice")]
    finally:
        cp.close()


def test_xlsx_build_ok(tmp_path: Path):
    pytest.importorskip("openpyxl")
    import pandas as pd

    inp = tmp_path / "input"
    inp.mkdir()
    xlsx = inp / "hotel_clients.xlsx"
    pd.DataFrame({"id": [1, 2], "name": ["a", "b"]}).to_excel(
        xlsx, index=False
    )
    cp = _open(
        tmp_path,
        {
            "df_x": {
                "type": "dataframe",
                "file": "input/hotel_clients.xlsx",
            },
        },
    )
    try:
        rows = cp.p_table_view("df_x").fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 1
    finally:
        cp.close()


def test_gui_build_after_save_with_file(tmp_path: Path):
    """Simule: create step file vide, puis PUT file, puis build."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "sales.csv").write_text("id,v\n1,10\n2,20\n", encoding="utf-8")

    client = TestClient(create_gui_app(tmp_path / "m.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "df_sales",
                    "config": {"type": "dataframe", "file": ""},
                },
            ).status_code
            == 200
        )
        # build sans file → erreur claire
        bad = client.post("/gui/build/df_sales")
        assert bad.status_code >= 400

        assert (
            client.put(
                "/gui/step/df_sales",
                json={
                    "config": {
                        "type": "dataframe",
                        "file": "input/sales.csv",
                    }
                },
            ).status_code
            == 200
        )
        ok = client.post("/gui/build/df_sales?limit=3")
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body.get("ok") is True
        assert body.get("row_count") == 2


def test_capture_ref():
    root = Path(__file__).resolve().parents[1]
    an = (root / "gestion_projet" / "anomalies.csv").read_text(encoding="utf-8")
    assert "A0005" in an
    cap = (
        root
        / "gestion_projet"
        / "agentic"
        / "captures"
        / "A0005_build_extension_non_supportee.png"
    )
    assert cap.is_file()
