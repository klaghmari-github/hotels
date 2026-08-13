"""
[DEPRECATED] Ancien moteur CatBoost multi-cibles CA.

Plus branché dans la GUI ni dans `run.py`.
Utiliser `SuperModelService` (ml_tc → ml_ca).
"""

from __future__ import annotations

from typing import Any


class CatBoostService:
    """Stub — lever une erreur explicite si réutilisé par erreur."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise RuntimeError(
            "CatBoostService est abandonné. "
            "Utiliser src.ml.super_model.SuperModelService."
        )
