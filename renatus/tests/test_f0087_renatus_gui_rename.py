"""F0087 / F0088 — surfaces renatus-cli / renatus-api / renatus-gui."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"


def test_feature_f0087_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0087" in text


def test_pyproject_product_entrypoints():
    text = PYPROJECT.read_text(encoding="utf-8")
    assert 'renatus-gui = "renatus.gui.server:main"' in text
    assert 'renatus-cli = "renatus.cli:main"' in text
    assert 'renatus-api = "renatus.api.server:main"' in text
    # plus d alias historique
    assert "renatus-studio" not in text
    assert "renatus.studio" not in text


def test_cli_prog_is_renatus_gui():
    from renatus.gui.server import build_parser

    p = build_parser()
    assert p.prog == "renatus-gui"
    help_text = p.format_help()
    assert "renatus-gui" in help_text


def test_ui_title_renatus_gui():
    from tests.helpers.static_sources import read_index

    html = read_index()
    assert "Renatus GUI" in html
    assert "<title>Renatus GUI</title>" in html


def test_docs_mention_gui_surfaces():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "renatus-gui" in readme
    assert "renatus-cli" in readme
    gui = (REPO / "doc" / "GUI.md").read_text(encoding="utf-8")
    assert "renatus-gui" in gui
