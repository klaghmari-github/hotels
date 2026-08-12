"""F0109 — lien Documentation dans renatus-gui + service /gui/docs."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app, _doc_dir
from tests.helpers.static_sources import read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0109_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0109" in text


def test_ui_docs_link_in_topbar():
    html = read_index()
    assert 'data-testid="btn-docs"' in html
    assert 'href="/gui/docs/documentation.html"' in html
    assert 'id="btn-docs"' in html


def test_doc_dir_resolves():
    d = _doc_dir()
    assert d is not None
    assert (d / "documentation.html").is_file()


def test_gui_serves_documentation_html(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "t.duckdb", pipe))
    with client:
        r = client.get("/gui/docs/documentation.html")
        assert r.status_code == 200, r.text[:200]
        assert "renatus" in r.text.lower()
        assert "uml" in r.text.lower() or "classDiagram" in r.text

        # raccourci redirect
        r2 = client.get("/gui/documentation", follow_redirects=False)
        assert r2.status_code in (307, 302, 301)
        assert "documentation.html" in (r2.headers.get("location") or "")

        # index GUI contient le lien
        home = client.get("/gui")
        assert home.status_code == 200
        assert 'data-testid="btn-docs"' in home.text
