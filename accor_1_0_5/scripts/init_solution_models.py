#!/usr/bin/env python3
"""CLI wrapper — voir ``python -m accor.init_solution_models``."""

from __future__ import annotations

import sys
from pathlib import Path

# Permet l'exécution directe depuis scripts/ sans install editable
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from accor.init_solution_models import main

if __name__ == "__main__":
    raise SystemExit(main())
