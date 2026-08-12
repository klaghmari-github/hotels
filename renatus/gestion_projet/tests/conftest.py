"""
Fixtures tests de gestion projet.

Ajoute gestion_projet/src au path pour importer le package agentic
sans toucher au package produit renatus.
"""

from __future__ import annotations

import sys
from pathlib import Path

GESTION_SRC = Path(__file__).resolve().parents[1] / "src"
if str(GESTION_SRC) not in sys.path:
    sys.path.insert(0, str(GESTION_SRC))
