"""
F0025 — documentation separee core / cli / api / gui + HTML.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "doc"


def test_feature_f0025_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0025" in features


def test_markdown_docs_exist():
    for name in ("CORE.md", "CLI.md", "API.md", "GUI.md"):
        path = DOC / name
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert len(text) > 500
        assert "Obligatoire" in text or "obligatoire" in text
        assert "Exemple" in text or "exemple" in text or "```" in text


def test_core_covers_five_types():
    text = (DOC / "CORE.md").read_text(encoding="utf-8")
    for t in ("dataframe", "table", "view", "execute_sql", "iterate"):
        assert t in text
    assert "requires" in text
    assert "step_view" in text
    assert "create_or_replace" in text


def test_cli_covers_commands():
    text = (DOC / "CLI.md").read_text(encoding="utf-8")
    for cmd in (
        "p_table_view",
        "table_view",
        "process",
        "process_with_requires",
        "p_iteration",
        "help",
    ):
        assert cmd in text
    assert "REPL" in text or "repl" in text.lower()


def test_api_covers_endpoints():
    text = (DOC / "API.md").read_text(encoding="utf-8")
    for path in (
        "/health",
        "/pipeline",
        "/p_table_view",
        "/table_view",
        "/process_with_requires",
        "/p_iteration",
    ):
        assert path in text
    assert "curl" in text


def test_gui_covers_gui():
    text = (DOC / "GUI.md").read_text(encoding="utf-8")
    assert "GUI" in text or "gui" in text
    assert "/gui/graph" in text
    assert "DataView" in text or "dataview" in text.lower()
    assert "Requires" in text or "requires" in text


def test_html_doc_styled_and_sections():
    html = (DOC / "documentation.html").read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()
    assert "id=\"core\"" in html or 'id="core"' in html
    assert "id=\"cli\"" in html or 'id="cli"' in html
    assert "id=\"api\"" in html or 'id="api"' in html
    assert "id=\"gui\"" in html or 'id="gui"' in html
    assert "sidebar" in html
    assert len(html) > 3000
    # pas d emojis / marqueurs IA courants
    for bad in ("🚀", "✨", "TODO IA", "As an AI", "ChatGPT"):
        assert bad not in html


def test_readme_points_to_docs():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "doc/CORE.md" in readme
    assert "doc/CLI.md" in readme
    assert "doc/API.md" in readme
    assert "doc/GUI.md" in readme
    assert "documentation.html" in readme
