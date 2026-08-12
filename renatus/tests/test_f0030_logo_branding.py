"""
F0030 — logo officiel renatus (PNG) + vecteurs SVG + doc renaissance/lineage.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSETS = REPO / "doc" / "assets"
README = REPO / "README.md"
DOC_HTML = REPO / "doc" / "documentation.html"
CORE = REPO / "doc" / "CORE.md"
GUI_STATIC = REPO / "src" / "renatus" / "gui" / "static"


def test_feature_f0030_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0030" in features


def test_official_logo_png_assets_exist():
    """Logo officiel fourni (PNG) present en docs et GUI."""
    logo = ASSETS / "renatus-logo.png"
    mark = ASSETS / "renatus-mark.png"
    assert logo.is_file()
    assert mark.is_file()
    # PNG signature
    assert logo.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert logo.stat().st_size > 10_000


def test_logo_svg_vector_assets_exist():
    logo = ASSETS / "renatus-logo.svg"
    mark = ASSETS / "renatus-mark.svg"
    assert logo.is_file()
    assert mark.is_file()
    svg = logo.read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "viewBox" in svg
    assert "circle" in svg
    assert "path" in svg
    assert len(svg) > 400


def test_logo_in_gui_static():
    png = GUI_STATIC / "renatus-logo.png"
    svg = GUI_STATIC / "renatus-logo.svg"
    assert png.is_file()
    assert svg.is_file()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_readme_intro_renaissance_and_logo():
    text = README.read_text(encoding="utf-8")
    assert "renatus-logo.png" in text or "renatus-logo.svg" in text
    assert "renaitre" in text.lower() or "renaissance" in text.lower()
    assert "lineage" in text.lower()
    assert "yaml" in text.lower()


def test_documentation_html_intro_and_logo():
    html = DOC_HTML.read_text(encoding="utf-8")
    assert (
        "renatus-logo.png" in html
        or "renatus-logo.svg" in html
        or "renatus-mark.png" in html
        or "renatus-mark.svg" in html
    )
    assert "renaitre" in html.lower() or "renaissance" in html.lower()
    assert "lineage" in html.lower()


def test_core_md_intro_renaissance():
    text = CORE.read_text(encoding="utf-8")
    assert "renaissance" in text.lower() or "renaitre" in text.lower()
    assert "lineage" in text.lower()


def test_gui_html_uses_official_logo_img():
    html = (GUI_STATIC / "index.html").read_text(encoding="utf-8")
    assert "renatus-logo.png" in html
    assert 'data-testid="brand-logo"' in html


def test_logo_served_by_gui(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "l.duckdb", pipe))
    with client:
        r = client.get("/gui/static/renatus-logo.png")
        assert r.status_code == 200
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        page = client.get("/").text
        assert "renatus-logo.png" in page
