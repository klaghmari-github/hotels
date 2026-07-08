"""Modèles de requête / réponse pour l'API REST de prédiction."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class MonthlyPrediction:
    month: int
    ca: float
    nbr_ventes: float
    marge_nette: float
    cout: float = 0.0
    marge_produit: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConceptPrediction:
    concept: str
    source: str
    ca_annuel: float
    nbr_ventes_annuel: float
    marge_annuelle: float
    cout_annuel: float
    ca_mensuel_moyen: float
    nbr_ventes_mensuel_moyen: float
    roi_months: float | None
    monthly: List[MonthlyPrediction] = field(default_factory=list)
    costs_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k != "monthly"},
            "monthly": [m.to_dict() for m in self.monthly],
        }


@dataclass
class PredictionApiResponse:
    input: dict
    context: dict
    predictions: Dict[str, ConceptPrediction]
    recommendation: dict
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "input": self.input,
            "context": self.context,
            "predictions": {k: v.to_dict() for k, v in self.predictions.items()},
            "recommendation": self.recommendation,
            "warnings": self.warnings,
        }