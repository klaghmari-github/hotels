"""
Référentiel constantes ROD (pilotes Excel).

Source runtime : data/rod_reference.json
(extrait de l'Excel simulateur + détail des coûts).

RodReference expose :
  concept(name)       pivots, mix, base CA, cost_lines
  concept_names()     SIMPLY / LIBERTY / CONNECTED
  get('a.b.c')        accès pointé
  impact_to / raw     constantes transverses

Rechargé via reload() si le JSON est régénéré sans redémarrer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


from archive.accor_1_0_5.src.accor.data_io import DATA_DIR
REFERENCE_PATH = DATA_DIR / "rod_reference.json"


class RodReference:
    """Accès en lecture aux constantes pilote (concepts, impact TO, cost_lines)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or REFERENCE_PATH
        self._data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        if not self.path.exists():
            self._data = {"concepts": {}, "impact_to": {}}
            return
        self._data = json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def raw(self) -> dict[str, Any]:
        return self._data

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """``get('concepts.SIMPLY.pivot_m_lin')``."""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def concept(self, name: str) -> dict[str, Any]:
        concepts = self._data.get("concepts") or {}
        return dict(concepts.get(name.upper(), {}) or {})

    def concept_names(self) -> list[str]:
        return list((self._data.get("concepts") or {}).keys())
