"""
Lecture des sources JS/CSS GUI (F0053-S0).

Quand app.js monolithe est decoupe en modules sous static/app/,
les asserts "function name in source" doivent lire l ensemble
des fichiers JS, pas seulement l entry.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "src" / "renatus" / "gui" / "static"


def static_dir() -> Path:
    return STATIC


def js_source_files() -> list[Path]:
    """Tous les fichiers JS produit (hors minifies vendor si besoin)."""
    files: list[Path] = []
    # Entry historique monolithe
    app_js = STATIC / "app.js"
    if app_js.is_file():
        files.append(app_js)
    # Modules ES (F0053)
    app_dir = STATIC / "app"
    if app_dir.is_dir():
        files.extend(sorted(app_dir.rglob("*.js")))
    # Dedup par resolve
    seen: set[Path] = set()
    out: list[Path] = []
    for p in files:
        r = p.resolve()
        if r in seen:
            continue
        # ignorer vendor minifie
        if p.name.endswith(".min.js"):
            continue
        seen.add(r)
        out.append(p)
    return out


def read_all_js() -> str:
    """Concatene tous les sources JS GUI pour asserts de presence."""
    parts: list[str] = []
    for path in js_source_files():
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def read_app_js_or_modules() -> str:
    """Alias clair pour les tests UI."""
    return read_all_js()


def js_contains(snippet: str) -> bool:
    return snippet in read_all_js()


def index_html() -> Path:
    return STATIC / "index.html"


def style_css() -> Path:
    return STATIC / "style.css"


def read_index() -> str:
    return index_html().read_text(encoding="utf-8")


def read_css() -> str:
    return style_css().read_text(encoding="utf-8")
