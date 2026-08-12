"""
F0013 — testabilite GUI GUI (data-testid + specs).

Niveau unit/integration : pas de navigateur.
Les E2E Playwright sont marques @pytest.mark.e2e (extra [e2e]).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
SPEC = (
    REPO
    / "gestion_projet"
    / "agentic"
    / "specs"
    / "F0013_gui_testing_strategy.md"
)


REQUIRED_TESTIDS = [
    "gui-palette",
    "gui-canvas",
    "gui-config",
    "gui-dataview",
    # F0086: btn-save / btn-build / btn-delete retires de Config
    "btn-dv-build",
    "chip-db",
    "chip-pipe",
    "new-step-dialog",
    "new-step-name",
]


def test_spec_f0013_saved_and_referenced():
    assert SPEC.is_file()
    text = SPEC.read_text(encoding="utf-8")
    assert "Playwright" in text
    assert "data-testid" in text
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0013" in features
    assert "F0013_gui_testing_strategy.md" in features


def test_gui_html_has_stable_testids():
    html = INDEX.read_text(encoding="utf-8")
    for tid in REQUIRED_TESTIDS:
        assert f'data-testid="{tid}"' in html, f"missing testid {tid}"


def test_gui_js_assigns_palette_and_node_testids():
    js = read_all_js()
    assert 'data-testid", "palette-"' in js or "palette-" in js
    assert 'data-testid="node-' in js


def test_doc_testing_gui_exists():
    doc = REPO / "doc" / "TESTING_GUI.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "Playwright" in text
    assert "data-testid" in text
    assert "Acceptance" in text or "acceptation" in text.lower() or "AC" in text


def test_tools_visible_in_live_html(tmp_path: Path):
    """Integration: page servie contient palette + canvas testids."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    app = create_gui_app(tmp_path / "x.duckdb", pipe)
    with TestClient(app) as client:
        html = client.get("/").text
        assert 'data-testid="gui-canvas"' in html
        assert 'data-testid="gui-palette"' in html


@pytest.mark.e2e
def test_e2e_gui_palette_and_create_step(tmp_path: Path):
    """
    E2E Playwright (skip si playwright non installe).

    AC: palette presente ; creation step table via UI ; nœud visible.
    """
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    import threading
    import time

    import uvicorn

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "main.duckdb"
    app = create_gui_app(db, pipe)

    # port libre
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # wait ready
    for _ in range(50):
        try:
            import urllib.request

            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.2)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.fail("server not ready")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.get_by_test_id("gui-palette").wait_for()
            page.get_by_test_id("palette-table").click()
            page.get_by_test_id("new-step-name").fill("t_demo")
            # submit create
            page.locator('#new-step-form button[value="create"]').click()
            page.get_by_test_id("node-t_demo").wait_for(timeout=5000)
            browser.close()
    finally:
        server.should_exit = True
