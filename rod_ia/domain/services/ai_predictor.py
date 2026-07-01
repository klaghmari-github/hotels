"""Prédicteur IA (XGBoost) avec colonnes ``d_`` / ``t_``."""

from __future__ import annotations

import json
import re
from pathlib import Path

import joblib
import pandas as pd

from rod_ia.domain.models.simulation import MonthlyProjection, RodSimulationRequest, SimulationResult
from rod_ia.domain.services.ml_column_naming import MLColumnNaming


class AIRodRevenuePredictor:
    """Charge le modèle joblib et prédit les targets ``t_*``."""

    def __init__(self, artifacts_dir: str | Path) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.model = None
        self.feature_cols: list[str] = []
        self.target_cols: list[str] = []
        self.load_warnings: list[str] = []
        self._load()

    def _load(self) -> None:
        model_path = self.artifacts_dir / "model.joblib"
        if model_path.exists():
            try:
                self.model = joblib.load(model_path)
            except ModuleNotFoundError as exc:
                self.load_warnings.append(
                    f"Impossible de charger model.joblib ({exc.name} manquant). "
                    "Installer xgboost ou réentraîner le modèle."
                )
            except Exception as exc:
                self.load_warnings.append(f"Erreur chargement model.joblib: {exc}")
        else:
            self.load_warnings.append(
                "model.joblib absent — copier les artefacts depuis old/artifacts/ "
                "ou entraîner via pipelines/train_models.py."
            )
        feature_path = self.artifacts_dir / "feature_cols.json"
        if feature_path.exists():
            self.feature_cols = json.loads(feature_path.read_text(encoding="utf-8"))
        target_path = self.artifacts_dir / "target_cols.json"
        if target_path.exists():
            self.target_cols = json.loads(target_path.read_text(encoding="utf-8"))

    def request_to_features(self, request: RodSimulationRequest) -> pd.DataFrame:
        data = {
            MLColumnNaming.descriptive("nb_chambres"): request.operating.nb_chambres,
            MLColumnNaming.descriptive("taux_occupation"): request.operating.taux_occupation,
            MLColumnNaming.descriptive("guests_per_chambre"): request.operating.guests_per_chambre,
            MLColumnNaming.descriptive("m_lin"): request.store.m_lin,
            MLColumnNaming.descriptive("fb_share"): request.store.mix.fb_share,
            MLColumnNaming.descriptive("non_fb_share"): request.store.mix.non_fb_share,
        }
        for key, value in request.enriched.poi.items():
            data[key if key.startswith("d_") else MLColumnNaming.descriptive(key)] = value
        for key, value in request.enriched.weather_monthly.items():
            data[key if key.startswith("d_") else MLColumnNaming.descriptive(key)] = value

        frame = pd.DataFrame([data])
        if self.feature_cols:
            for col in self.feature_cols:
                if col not in frame.columns:
                    frame[col] = 0.0
            frame = frame[self.feature_cols]
        MLColumnNaming.assert_no_target_leakage(frame.columns)
        return frame

    def predict(self, request: RodSimulationRequest) -> SimulationResult:
        warnings = list(self.load_warnings)
        if self.model is None:
            monthly = [
                MonthlyProjection(month=month, ca=0.0, nbr_ventes=0.0)
                for month in range(1, 13)
            ]
            return SimulationResult(
                "AI_MODEL",
                request.store.concept,
                request.store.m_lin,
                0,
                0,
                0,
                0,
                None,
                monthly,
                warnings=warnings,
            )

        features = self.request_to_features(request)
        prediction = self.model.predict(features)
        values = prediction[0] if hasattr(prediction, "__len__") else [float(prediction)]
        monthly_map = {month: {"ca": 0.0, "nbr_ventes": 0.0} for month in range(1, 13)}

        for col, val in zip(self.target_cols, values):
            match = re.search(r"m(\d{2})", col)
            if not match:
                continue
            month = int(match.group(1))
            if "montant" in col or "ca" in col.lower():
                monthly_map[month]["ca"] += max(float(val), 0.0)
            if "nbr_ventes" in col or "ventes" in col.lower():
                monthly_map[month]["nbr_ventes"] += max(float(val), 0.0)

        monthly = [
            MonthlyProjection(
                month=month,
                ca=monthly_map[month]["ca"],
                nbr_ventes=monthly_map[month]["nbr_ventes"],
            )
            for month in range(1, 13)
        ]
        ca_annuel = sum(row.ca for row in monthly)
        ventes_annuel = sum(row.nbr_ventes for row in monthly)
        return SimulationResult(
            "AI_MODEL",
            request.store.concept,
            request.store.m_lin,
            ca_annuel,
            ventes_annuel,
            ca_annuel,
            0,
            None,
            monthly,
            warnings=warnings,
        )