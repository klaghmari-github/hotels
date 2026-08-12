"""F0124 — View: controler lignes/page; une page chargee a la fois."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0124_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0124" in text


def test_ui_page_size_select():
    html = read_index()
    assert 'data-testid="dataview-page-size"' in html
    assert 'id="dataview-page-size"' in html
    # options usuelles
    for n in ("3", "10", "25", "50", "100"):
        assert f'value="{n}"' in html
    js = read_all_js()
    assert "setDataViewPageSize" in js
    assert "clampDataViewPageSize" in js
    assert "DATAVIEW_MAX_PAGE_SIZE" in js
    assert "DATAVIEW_PAGE_SIZE_OPTIONS" in js
    assert "syncDataViewPageSizeSelect" in js
    css = read_css()
    assert "dataview-page-size" in css


def test_preview_respects_limit_not_full_table(tmp_path: Path):
    """Seule la page demandee est renvoyee (pas N millions de lignes)."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    # 50 lignes
    (pipe / "default" / "t_big.yaml").write_text(
        yaml.dump(
            {
                "t_big": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "script": "SELECT i AS n FROM range(50) t(i)",
                    "requires": [],
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "big.duckdb", pipe))
    with client:
        assert client.post("/gui/build/t_big?limit=3").status_code == 200

        r3 = client.get("/gui/preview/t_big?limit=3&page=1").json()
        assert len(r3.get("rows") or []) == 3
        assert r3.get("total_rows") == 50
        assert r3.get("page_size") == 3 or r3.get("limit") == 3

        r10 = client.get("/gui/preview/t_big?limit=10&page=2").json()
        assert len(r10.get("rows") or []) == 10
        # page 2 offset 10 → 10..19
        assert [row[0] for row in r10["rows"]] == list(range(10, 20))
        assert r10.get("total_rows") == 50
        # jamais la table entiere dans la reponse
        assert len(r10["rows"]) < 50

        r100 = client.get("/gui/preview/t_big?limit=100&page=1").json()
        assert len(r100.get("rows") or []) == 50  # table < pageSize
        assert r100.get("has_next") is False
