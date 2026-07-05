"""Interprétation du modèle IA — importance globale, par hôtel, règles et config."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.rules.recommendation_rules import RodRecommendationRules
from rod_ia.domain.services.ai_pnl_service import AIPnlService
from rod_ia.domain.services.ai_predictor import AIRodRevenuePredictor
from rod_ia.domain.services.simulation_orchestrator import SimulationOrchestrator


class ModelInterpretationService:
    """Expose config modèle, importances et règles globales / par hôtel."""

    XGB_PARAMS = {
        "n_estimators": 120,
        "max_depth": 4,
        "learning_rate": 0.08,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "random_state": 42,
    }

    def __init__(
        self,
        predictor: AIRodRevenuePredictor,
        ai_pnl: AIPnlService,
        orchestrator: SimulationOrchestrator,
        recommendation_rules: RodRecommendationRules,
        processed_dir: Path,
        artifacts_dir: Path,
    ) -> None:
        self._predictor = predictor
        self._ai_pnl = ai_pnl
        self._orchestrator = orchestrator
        self._reco = recommendation_rules
        self._processed_dir = Path(processed_dir)
        self._artifacts_dir = Path(artifacts_dir)

    @staticmethod
    def _prettify_feature(name: str) -> str:
        label = re.sub(r"^d_", "", name)
        label = re.sub(r"^t_", "", label)
        label = label.replace("_", " ")
        return label[:80]

    def _load_json(self, path: Path) -> dict | list | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _training_stats(self, feature_cols: list[str]) -> tuple[pd.Series, pd.Series]:
        x_path = self._processed_dir / "X_descriptive.csv"
        if not x_path.exists():
            zeros = pd.Series(0.0, index=feature_cols)
            ones = pd.Series(1.0, index=feature_cols)
            return zeros, ones
        frame = pd.read_csv(x_path).fillna(0.0)
        for col in feature_cols:
            if col not in frame.columns:
                frame[col] = 0.0
        means = frame[feature_cols].mean()
        stds = frame[feature_cols].std().replace(0.0, 1.0)
        return means, stds

    def _global_importance_scores(self) -> np.ndarray | None:
        model = self._predictor.model
        if model is None:
            return None
        estimators = getattr(model, "estimators_", None)
        if not estimators:
            return None
        matrix = np.array([est.feature_importances_ for est in estimators], dtype=float)
        return matrix.mean(axis=0)

    def _rank_features(
        self,
        scores: np.ndarray,
        feature_cols: list[str],
        values: np.ndarray | None = None,
        means: pd.Series | None = None,
        stds: pd.Series | None = None,
        *,
        top_n: int = 12,
    ) -> list[dict]:
        if values is not None and means is not None and stds is not None:
            z = np.array(
                [
                    abs((values[i] - float(means.iloc[i])) / float(stds.iloc[i]))
                    if i < len(values)
                    else 0.0
                    for i in range(len(feature_cols))
                ],
                dtype=float,
            )
            ranked_scores = scores * z
            mode = "prediction"
        else:
            ranked_scores = scores
            mode = "global"

        order = np.argsort(ranked_scores)[::-1]
        rows: list[dict] = []
        for idx in order[:top_n]:
            if ranked_scores[idx] <= 0:
                continue
            col = feature_cols[idx]
            row = {
                "feature": col,
                "label": self._prettify_feature(col),
                "score": float(ranked_scores[idx]),
                "importance": float(scores[idx]),
                "mode": mode,
            }
            if values is not None:
                row["value"] = float(values[idx])
                if means is not None:
                    row["train_mean"] = float(means.iloc[idx])
            rows.append(row)
        return rows

    def _model_config(self) -> dict:
        meta = self._load_json(self._artifacts_dir / "meta.json") or {}
        return {
            "algorithm": meta.get("model", "MultiOutputRegressor(XGBRegressor)"),
            "n_hotels_train": meta.get("n_hotels"),
            "n_features": meta.get("n_features", len(self._predictor.feature_cols)),
            "n_targets": meta.get("n_targets", len(self._predictor.target_cols)),
            "train_mae": meta.get("train_mae"),
            "xgboost_params": self.XGB_PARAMS,
            "target_cols_sample": self._predictor.target_cols[:6],
            "model_available": self._predictor.model is not None,
            "warnings": list(self._predictor.load_warnings),
        }

    def _global_rules(self) -> list[dict]:
        rules: list[dict] = []
        selection = self._load_json(self._processed_dir / "feature_selection_report.json") or {}
        if selection:
            rules.append(
                {
                    "rule_id": "FEATURE_SELECTION",
                    "scope": "global",
                    "description": (
                        f"{selection.get('n_removed_constant', 0)} variables constantes exclues, "
                        f"{selection.get('n_removed_duplicate', 0)} doublons exclus, "
                        f"{selection.get('n_kept', 0)} conservées pour l'entraînement."
                    ),
                    "source": "feature_selection_report.json",
                }
            )
            for item in (selection.get("removed_constant") or [])[:3]:
                rules.append(
                    {
                        "rule_id": "FEATURE_CONSTANT",
                        "scope": "global",
                        "description": f"{item.get('column')} — {item.get('justification')}",
                        "source": "FeatureSelector",
                    }
                )

        rules.append(
            {
                "rule_id": "MODEL_TRAINING",
                "scope": "global",
                "description": (
                    "Entraînement XGBoost multi-sorties sur targets mensuelles globales "
                    "(t_m{mm}_ca_total, t_m{mm}_ventes_total) avec features d_*."
                ),
                "source": "model_trainer.py",
            }
        )
        rules.append(
            {
                "rule_id": "IMPUTATION_STRATEGIES",
                "scope": "global",
                "description": (
                    "Booléens → 0 ; TO/guests → pilote marque ; panier → CA/ventes train ; "
                    "taux acheteur → ventes/clients (C21) ; autres numériques → médiane globale."
                ),
                "source": "feature_imputer.py",
            }
        )
        _, reco_trace, _ = self._reco.allowed_concepts(
            RodSimulationRequest.from_dict({"operating": {"nb_chambres": 129}})
        )
        for trace in reco_trace:
            rules.append({**trace.to_dict(), "scope": "global"})
        return rules

    def _hotel_rules(self, request: RodSimulationRequest, concept: str) -> list[dict]:
        rules: list[dict] = []
        hotel_id = request.identity.hotel_id

        imputation = self._load_json(self._processed_dir / "imputation_report.json") or {}
        entries = [
            e
            for e in (imputation.get("entries") or [])
            if not hotel_id or e.get("hotel_id") == hotel_id
        ]
        strategies: dict[str, list[str]] = {}
        for entry in entries:
            strategies.setdefault(entry.get("strategy", "unknown"), []).append(entry.get("column", ""))
        for strategy, cols in strategies.items():
            sample = ", ".join(self._prettify_feature(c) for c in cols[:3])
            suffix = f" (+{len(cols) - 3})" if len(cols) > 3 else ""
            rules.append(
                {
                    "rule_id": f"IMPUTATION_{strategy.upper()}",
                    "scope": "hotel",
                    "hotel_id": hotel_id,
                    "description": f"{len(cols)} variables imputées ({strategy}) — ex. {sample}{suffix}",
                    "source": "imputation_report.json",
                }
            )

        allowed, reco_trace, reco_warnings = self._reco.allowed_concepts(request)
        for trace in reco_trace:
            rules.append({**trace.to_dict(), "scope": "hotel", "hotel_id": hotel_id})
        for warning in reco_warnings:
            rules.append(
                {
                    "rule_id": "RECO_WARNING",
                    "scope": "hotel",
                    "hotel_id": hotel_id,
                    "description": warning,
                    "source": "RodRecommendationRules",
                }
            )

        req = self._orchestrator.request_for_concept(request, concept)
        ai = self._ai_pnl.predict_pnl(req, concept)
        for trace_entry in ai.trace or []:
            rules.append({**trace_entry, "scope": "hotel", "hotel_id": hotel_id, "concept": concept})

        if concept not in allowed:
            rules.append(
                {
                    "rule_id": "CONCEPT_NOT_ALLOWED",
                    "scope": "hotel",
                    "hotel_id": hotel_id,
                    "description": f"Concept {concept} hors périmètre autorisé ({', '.join(allowed)}).",
                    "source": "RodRecommendationRules",
                }
            )
        return rules

    def interpret(self, request: RodSimulationRequest, concept: str | None = None) -> dict:
        full = self._orchestrator.simulate_all(request)
        concept = concept or full.recommended_concept
        feature_cols = self._predictor.feature_cols or []
        scores = self._global_importance_scores()

        global_top: list[dict] = []
        hotel_top: list[dict] = []
        prediction_top: dict | None = None

        if scores is not None and feature_cols:
            global_top = self._rank_features(scores, feature_cols, top_n=12)
            features = self._predictor.request_to_features(
                self._orchestrator.request_for_concept(request, concept)
            )
            values = features.iloc[0].values.astype(float)
            means, stds = self._training_stats(feature_cols)
            hotel_top = self._rank_features(
                scores, feature_cols, values, means, stds, top_n=12
            )
            if hotel_top:
                prediction_top = hotel_top[0]

        return {
            "hotel_id": request.identity.hotel_id,
            "hotel_name": request.identity.hotel_name,
            "concept": concept,
            "recommended_concept": full.recommended_concept,
            "model_config": self._model_config(),
            "global_top_feature": global_top[0] if global_top else None,
            "prediction_top_feature": prediction_top,
            "global_feature_importance": global_top,
            "hotel_feature_importance": hotel_top,
            "global_rules": self._global_rules(),
            "hotel_rules": self._hotel_rules(request, concept),
        }