from pathlib import Path
import json
from typing import Any, Dict

class ReferenceRepository:
    """Référentiel des constantes ROD.

    Les constantes viennent des Excel ou du recalcul sur ventes pivots.
    Le code métier ne doit pas cacher de chiffres non traçables.
    """
    def __init__(self, reference_path: str | Path | None = None):
        self.reference_path = Path(reference_path) if reference_path else None
        self.data: Dict[str, Any] = {}
        if self.reference_path and self.reference_path.exists():
            self.data = json.loads(self.reference_path.read_text(encoding="utf-8"))

    def get(self, key: str, default: Any = None) -> Any:
        cur: Any = self.data
        for part in key.split('.'):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def require(self, key: str) -> Any:
        val = self.get(key, None)
        if val is None:
            raise KeyError(f"Référence obligatoire manquante: {key}")
        return val
