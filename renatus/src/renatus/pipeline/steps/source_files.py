"""
F0146 — fichiers source a cote du YAML (execute_python / notebook).

- execute_python → <id>.py
- notebook → <id>.ipynb (nbformat 4)
Le champ YAML ``script`` n est plus la source de verite : il sert
d affichage / fallback legacy. Le moteur lit le sidecar en priorite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Type de step → extension sidecar
SIDECAR_EXT: dict[str, str] = {
    "execute_python": ".py",
    "notebook": ".ipynb",
}

SIDECAR_TYPES = frozenset(SIDECAR_EXT.keys())


def sidecar_ext_for(step_type: str | None) -> str | None:
    st = str(step_type or "").strip()
    return SIDECAR_EXT.get(st)


def default_ipynb(script: str = "") -> dict[str, Any]:
    """Notebook nbformat 4 minimal avec une cellule code."""
    src = str(script or "")
    if src and not src.endswith("\n"):
        src = src + "\n"
    if not src.strip():
        src = (
            "# Notebook renatus — session Python partagee\n"
            "# Ajoutez des cellules, executez, inspectez les variables.\n"
            'print("notebook ready")\n'
        )
    lines = src.splitlines(keepends=True)
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": lines,
            }
        ],
    }


def cell_source_text(cell: dict[str, Any]) -> str:
    src = cell.get("source") if isinstance(cell, dict) else ""
    if isinstance(src, list):
        return "".join(str(x) for x in src)
    return str(src or "")


def ipynb_to_script(nb: dict[str, Any] | None) -> str:
    """Concatene les cellules code pour execution moteur / apercu."""
    if not isinstance(nb, dict):
        return ""
    parts: list[str] = []
    for cell in nb.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        if str(cell.get("cell_type") or "") != "code":
            continue
        text = cell_source_text(cell).rstrip()
        if text:
            parts.append(text)
    return "\n\n".join(parts) + ("\n" if parts else "")


def parse_ipynb(raw: str | bytes | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        nb = raw
    elif raw is None or raw == "":
        return default_ipynb("")
    else:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            nb = json.loads(str(raw))
        except json.JSONDecodeError:
            # texte brut → notebook 1 cellule
            return default_ipynb(str(raw))
    if not isinstance(nb, dict):
        return default_ipynb("")
    if "cells" not in nb:
        return default_ipynb("")
    nb.setdefault("nbformat", 4)
    nb.setdefault("nbformat_minor", 5)
    nb.setdefault("metadata", {})
    return nb


def script_from_sidecar_path(path: Path) -> str:
    """Lit un .py ou .ipynb et renvoie le code executable."""
    p = Path(path)
    if not p.exists():
        return ""
    if p.suffix.lower() == ".ipynb":
        try:
            nb = parse_ipynb(p.read_text(encoding="utf-8"))
            return ipynb_to_script(nb)
        except OSError:
            return ""
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def write_sidecar_content(
    path: Path,
    *,
    step_type: str,
    script: str | None = None,
    notebook: dict[str, Any] | None = None,
) -> Path:
    """
    Ecrit le fichier source a cote du YAML.

    - execute_python: texte .py
    - notebook: JSON .ipynb (notebook fourni, sinon derive de script)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    st = str(step_type or "").strip()
    if st == "notebook":
        nb = notebook if isinstance(notebook, dict) else None
        if nb is None:
            nb = default_ipynb(script or "")
        else:
            nb = parse_ipynb(nb)
        path.write_text(
            json.dumps(nb, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        return path
    # .py
    text = "" if script is None else str(script)
    if text and not text.endswith("\n"):
        text = text + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def companion_files(yaml_path: Path) -> list[Path]:
    """
    F0146: fichiers du meme stem (sans extension) dans le meme dossier.

    Non recursif. Inclut .py, .ipynb, etc. Exclut le yaml lui-meme.
    """
    yp = Path(yaml_path)
    parent = yp.parent
    if not parent.is_dir():
        return []
    stem = yp.stem
    out: list[Path] = []
    try:
        for p in parent.iterdir():
            if p.name.startswith("."):
                continue
            if p == yp:
                continue
            # meme id = meme stem (obj1.yaml + obj1.py + obj1.ipynb)
            if p.stem == stem and (p.is_file() or p.is_symlink()):
                out.append(p)
    except OSError:
        return []
    return sorted(out, key=lambda x: x.name.lower())
