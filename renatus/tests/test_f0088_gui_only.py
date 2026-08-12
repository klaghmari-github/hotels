"""F0088 — package routes CLI uniquement gui (pas de surface studio)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0088_registered():
    assert "F0088" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_no_studio_token_in_src_and_pyproject():
    """Produit (src + pyproject + README) sans le token 'studio'."""
    roots = [
        REPO / "src" / "renatus",
        REPO / "pyproject.toml",
        REPO / "README.md",
    ]
    text_ext = {".py", ".js", ".html", ".css", ".md", ".toml", ".txt"}
    hits = []
    for root in roots:
        paths = [root] if root.is_file() else root.rglob("*")
        for p in paths:
            if not p.is_file() or p.suffix.lower() not in text_ext:
                continue
            if "__pycache__" in p.parts:
                continue
            raw = p.read_text(encoding="utf-8", errors="ignore")
            if "studio" in raw.lower():
                for i, line in enumerate(raw.splitlines(), 1):
                    if "studio" in line.lower():
                        hits.append(
                            f"{p.relative_to(REPO)}:{i}:{line.strip()[:100]}"
                        )
    assert hits == [], "token studio restant:\n" + "\n".join(hits[:30])


def test_package_is_renatus_gui():
    import renatus.gui as gui

    assert hasattr(gui, "create_gui_app")
    assert hasattr(gui, "GuiService")
    from renatus.gui.server import build_parser

    assert build_parser().prog == "renatus-gui"


def test_routes_use_gui_prefix(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "g.duckdb", pipe))
    with client:
        r = client.get("/gui/")
        assert r.status_code == 200
        assert "Renatus GUI" in r.text
        # ancienne route absente
        r2 = client.get("/studio/")
        assert r2.status_code == 404
        tools = client.get("/gui/tools")
        assert tools.status_code == 200
