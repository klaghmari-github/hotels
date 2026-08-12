#!/usr/bin/env python3
"""
Lanceur racine du CLI renatus.

Usage:
  python renatus.py main.duckdb pipelines p_table_view v_sales
  python renatus.py main.duckdb pipelines

Compatibilite import: ce fichier porte le meme nom que le package
src/renatus/. Pour eviter d'occulter le package, il se comporte comme
un shim de package ( __path__ vers src/renatus ) lorsqu'il est importe
sous le nom renatus.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_PKG_DIR = _ROOT / "src" / "renatus"

# Fait de ce module un package pointant vers le vrai code source.
__path__ = [str(_PKG_DIR)]


def _bootstrap_package_namespace() -> None:
    """Charge le contenu de src/renatus/__init__.py dans ce module."""
    init_path = _PKG_DIR / "__init__.py"
    code = compile(
        init_path.read_text(encoding="utf-8"),
        str(init_path),
        "exec",
    )
    exec(code, globals())


if __name__ == "renatus":
    _bootstrap_package_namespace()


if __name__ == "__main__":
    from renatus.cli import main

    raise SystemExit(main())
