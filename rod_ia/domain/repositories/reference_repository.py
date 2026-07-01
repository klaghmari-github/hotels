"""Accès aux constantes ROD extraites d'Excel ou recalculées depuis les ventes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReferenceRepository:
    """Référentiel JSON des constantes métier traçables.

    Les valeurs proviennent exclusivement des classeurs Excel ROD ou du
    recalcul sur ventes pivots — jamais de constantes inventées en code.
    """

    def __init__(self, reference_path: str | Path | None = None) -> None:
        self.reference_path = Path(reference_path) if reference_path else None
        self._data: dict[str, Any] = {}
        if self.reference_path and self.reference_path.exists():
            self._data = json.loads(self.reference_path.read_text(encoding="utf-8"))

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        current: Any = self._data
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def require(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(f"Référence obligatoire manquante: {key}")
        return value

    def reload(self) -> None:
        if self.reference_path and self.reference_path.exists():
            self._data = json.loads(self.reference_path.read_text(encoding="utf-8"))