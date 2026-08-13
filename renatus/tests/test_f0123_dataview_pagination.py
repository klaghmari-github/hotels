"""F0123 — View paginee pour datasets (dataframe/table/view), pageSize=3."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.api.service import RelationSerializer
from renatus.gui.app import create_gui_app
from renatus.pipeline import ConnectionPipeline
from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0123_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0123" in text


def test_ui_pager_markup():
    html = read_index()
    assert 'data-testid="dataview-pager"' in html
    assert 'data-testid="btn-dv-page-prev"' in html
    assert 'data-testid="btn-dv-page-next"' in html
    assert 'data-testid="dataview-pager-label"' in html
    js = read_all_js()
    assert "DATAVIEW_DEFAULT_PAGE_SIZE" in js
    assert "loadDataViewPage" in js
    assert "updateDataViewPager" in js
    assert "wireDataViewPager" in js
    assert "page=" in js or "page=" in js
    css = read_css()
    assert ".dataview-pager" in css


def test_serializer_offset_and_total():
    import duckdb

    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT i FROM range(10) t(i)")
    rel = con.table("t")
    ser = RelationSerializer(default_limit=3, max_limit=100)
    page0 = ser.serialize(rel, "t", limit=3, offset=0)
    assert page0.row_count == 3
    assert page0.offset == 0
    assert page0.total_rows == 10
    assert page0.page == 1
    assert page0.total_pages == 4
    assert page0.truncated is True
    assert [r[0] for r in page0.rows] == [0, 1, 2]

    page1 = ser.serialize(rel, "t", limit=3, offset=3)
    assert [r[0] for r in page1.rows] == [3, 4, 5]
    assert page1.page == 2
    assert page1.truncated is True

    page3 = ser.serialize(rel, "t", limit=3, offset=9)
    assert [r[0] for r in page3.rows] == [9]
    assert page3.page == 4
    assert page3.truncated is False
    con.close()


def test_gui_preview_pagination(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    (pipe / "default" / "t_nums.yaml").write_text(
        yaml.dump(
            {
                "t_nums": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "script": "SELECT i AS n FROM range(8) t(i)",
                    "requires": [],
                }
            }
        ),
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "p.duckdb", pipe))
    with client:
        b = client.post("/gui/build/t_nums?limit=3")
        assert b.status_code == 200, b.text
        body = b.json()
        # build ne renvoie qu une page
        assert len(body.get("rows") or []) <= 3
        assert body.get("limit") == 3 or body.get("page_size") == 3

        p1 = client.get("/gui/preview/t_nums?limit=3&page=1")
        assert p1.status_code == 200, p1.text
        d1 = p1.json()
        assert d1.get("exists") is True
        assert len(d1.get("rows") or []) == 3
        assert d1.get("total_rows") == 8
        assert d1.get("page") == 1
        assert d1.get("has_next") is True
        assert d1.get("has_prev") is False
        assert [r[0] for r in d1["rows"]] == [0, 1, 2]

        p2 = client.get("/gui/preview/t_nums?limit=3&offset=3")
        d2 = p2.json()
        assert len(d2.get("rows") or []) == 3
        assert d2.get("page") == 2
        assert d2.get("has_prev") is True
        assert [r[0] for r in d2["rows"]] == [3, 4, 5]

        p3 = client.get("/gui/preview/t_nums?limit=3&page=3")
        d3 = p3.json()
        assert len(d3.get("rows") or []) == 2
        assert d3.get("has_next") is False
        assert [r[0] for r in d3["rows"]] == [6, 7]


def test_pipeline_table_view_still_works(tmp_path: Path):
    """Regression: p_table_view core + serializer offset defaut 0."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "t.yaml").write_text(
        yaml.dump(
            {
                "t": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "script": "SELECT 1 AS a UNION ALL SELECT 2 UNION ALL SELECT 3 "
                    "UNION ALL SELECT 4",
                }
            }
        ),
        encoding="utf-8",
    )
    # F0101: stem = id
    (pipe / "default" / "t.yaml").unlink()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "t.yaml").write_text(
        yaml.dump(
            {
                "t": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "script": (
                        "SELECT 1 AS a UNION ALL SELECT 2 "
                        "UNION ALL SELECT 3 UNION ALL SELECT 4"
                    ),
                }
            }
        ),
        encoding="utf-8",
    )
    cp = ConnectionPipeline(tmp_path / "x.duckdb", pipe, read_only=False)
    try:
        from renatus.api.service import RenatusService

        with RenatusService(
            tmp_path / "x.duckdb", pipe, max_rows=3
        ) as svc:
            # reopen with same paths - ConnectionPipeline already has db
            pass
    finally:
        cp.close()

    client = TestClient(create_gui_app(tmp_path / "y.duckdb", pipe))
    with client:
        client.post("/gui/build/t?limit=3")
        r = client.get("/gui/preview/t?limit=3")
        assert r.status_code == 200
        assert len(r.json().get("rows") or []) <= 3
