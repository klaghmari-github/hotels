"""
Chemins du dossier agentic sous gestion_projet.

Par defaut : <gestion_projet>/agentic/
Aucun import du package produit renatus (separation stricte).
"""

from __future__ import annotations

from pathlib import Path
from typing import Self


class AgenticPaths:
    """Arborescence agentic relative a gestion_projet."""

    def __init__(self, gestion_dir: str | Path | None = None):
        if gestion_dir is not None:
            self._gestion_dir = Path(gestion_dir).expanduser().resolve()
        else:
            self._gestion_dir = None

    @property
    def gestion_dir(self) -> Path:
        """
        Dossier gestion_projet (lazy si non fourni).

        Code sous gestion_projet/src/agentic/ -> parents[2] = gestion_projet.
        """
        if self._gestion_dir is None:
            # .../gestion_projet/src/agentic/paths.py
            self._gestion_dir = Path(__file__).resolve().parents[2]
        return self._gestion_dir

    @property
    def agentic_dir(self) -> Path:
        return self.gestion_dir / "agentic"

    @property
    def etat_path(self) -> Path:
        return self.agentic_dir / "etat.json"

    @property
    def session_path(self) -> Path:
        return self.agentic_dir / "session.md"

    @property
    def templates_dir(self) -> Path:
        return self.agentic_dir / "templates"

    @property
    def logs_dir(self) -> Path:
        return self.gestion_dir / "logs"

    @property
    def src_dir(self) -> Path:
        return self.gestion_dir / "src"

    def plan_path(self, item_id: str) -> Path:
        """Chemin du plan de resolution pour une feature (Fxxxx) ou anomalie (Axxxx)."""
        return self.agentic_dir / f"plan_{item_id}.md"

    def notes_dev_path(self, item_id: str) -> Path:
        return self.agentic_dir / f"notes_dev_{item_id}.md"

    def notes_test_path(self, item_id: str) -> Path:
        return self.agentic_dir / f"notes_test_{item_id}.md"

    def ensure(self) -> Self:
        """Cree agentic/, templates/, logs/ s'ils n'existent pas."""
        self.agentic_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        return self
