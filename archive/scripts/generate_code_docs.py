#!/usr/bin/env python3
"""Génère la documentation web du code ROD-IA."""

from __future__ import annotations

import ast
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "rod_ia" / "web" / "docs"
PACKAGE = ROOT / "rod_ia"


def module_doc(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    doc = ast.get_docstring(tree) or ""
    classes = []
    functions = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append({"name": node.name, "doc": ast.get_docstring(node) or ""})
        elif isinstance(node, ast.FunctionDef):
            functions.append({"name": node.name, "doc": ast.get_docstring(node) or ""})
    return {
        "path": str(path.relative_to(ROOT)),
        "doc": doc,
        "classes": classes,
        "functions": functions,
    }


def render_page(modules: list[dict]) -> str:
    sections = []
    for mod in sorted(modules, key=lambda m: m["path"]):
        cls_html = "".join(
            f"<li><strong>{html.escape(c['name'])}</strong>"
            f"<p>{html.escape(c['doc'])}</p></li>"
            for c in mod["classes"]
        )
        fn_html = "".join(
            f"<li><code>{html.escape(f['name'])}</code> — {html.escape(f['doc'])}</li>"
            for f in mod["functions"]
        )
        sections.append(
            f"<section id='{html.escape(mod['path'])}'>"
            f"<h2>{html.escape(mod['path'])}</h2>"
            f"<p>{html.escape(mod['doc'])}</p>"
            f"<h3>Classes</h3><ul>{cls_html or '<li>Aucune</li>'}</ul>"
            f"<h3>Fonctions</h3><ul>{fn_html or '<li>Aucune</li>'}</ul>"
            f"</section>"
        )
    nav = "".join(
        f"<a href='#{html.escape(m['path'])}'>{html.escape(m['path'])}</a>"
        for m in sorted(modules, key=lambda m: m["path"])
    )
    return f"""<!doctype html>
<html lang='fr'>
<head>
  <meta charset='utf-8'/>
  <title>ROD-IA — Documentation code</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; display: flex; background: #0f0f10; color: #e5e7eb; }}
    nav {{ width: 280px; padding: 20px; border-right: 1px solid #333; height: 100vh; overflow: auto; position: sticky; top: 0; }}
    nav a {{ display: block; font-size: 12px; color: #93c5fd; margin: 4px 0; text-decoration: none; }}
    main {{ flex: 1; padding: 28px; max-width: 900px; }}
    section {{ margin-bottom: 32px; padding-bottom: 24px; border-bottom: 1px solid #333; }}
    h1 {{ margin-top: 0; }}
    code {{ background: #1f2937; padding: 2px 6px; border-radius: 4px; }}
    li p {{ color: #a1a1aa; font-size: 14px; }}
  </style>
</head>
<body>
  <nav><h2>Modules</h2>{nav}</nav>
  <main>
    <h1>Documentation code ROD-IA</h1>
    <p>Généré automatiquement depuis les docstrings Python. Pipeline : <code>init.sh</code> construit, <code>run.sh</code> consomme.</p>
    {''.join(sections)}
  </main>
</body>
</html>"""


def main() -> None:
    modules = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "__init__.py" and path.stat().st_size < 80:
            continue
        modules.append(module_doc(path))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(render_page(modules), encoding="utf-8")
    print(f"Documentation → {OUT_DIR / 'index.html'} ({len(modules)} modules)")


if __name__ == "__main__":
    main()