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
    """Charge le modèle joblib et prédit les targets ``t_*`` (CA mensuel global)."""

    MONTHLY_CA_RE = re.compile(r"(?:t_)?m(\d{2}).*(?:ca_total|montant)", re.I)
    MONTHLY_VENTES_RE = re.compile(r"(?:t_)?m(\d{2}).*(?:ventes_total|nbr_ventes)", re.I)

    def __init__(
        self,
        artifacts_dir: str | Path,
        hotel_feature_loader=None,
    ) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self._hotel_features = hotel_feature_loader
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
                    f"Impossible de charger model.joblib ({exc.name} manquant)."
                )
            except Exception as exc:
                self.load_warnings.append(f"Erreur chargement model.joblib: {exc}")
        else:
            self.load_warnings.append(
                "model.joblib absent — exécuter ./init.sh pour entraîner le modèle."
            )
        feature_path = self.artifacts_dir / "feature_cols.json"
        if feature_path.exists():
            self.feature_cols = json.loads(feature_path.read_text(encoding="utf-8"))
        target_path = self.artifacts_dir / "target_cols.json"
        if target_path.exists():
            self.target_cols = json.loads(target_path.read_text(encoding="utf-8"))

    def request_to_features(self, request: RodSimulationRequest) -> pd.DataFrame:
        store = request.store
        m_lin = store.m_lin if store else 0.0
        fb = store.mix.fb_share if store else 0.7
        non_fb = store.mix.non_fb_share if store else 0.3
        data = {
            MLColumnNaming.descriptive("nb_chambres"): request.operating.nb_chambres,
            MLColumnNaming.descriptive("taux_occupation"): request.operating.taux_occupation,
            MLColumnNaming.descriptive("guests_per_chambre"): request.operating.guests_per_chambre,
            MLColumnNaming.descriptive("m_lin"): m_lin,
            MLColumnNaming.descriptive("fb_share"): fb,
            MLColumnNaming.descriptive("non_fb_share"): non_fb,
        }
        for key, value in request.enriched.poi.items():
            data[key if key.startswith("d_") else MLColumnNaming.descriptive(key)] = value
        for key, value in request.enriched.weather_monthly.items():
            data[key if key.startswith("d_") else MLColumnNaming.descriptive(key)] = value

        if self._hotel_features and request.identity.hotel_id:
            data.update(self._hotel_features.features_for_hotel(request.identity.hotel_id))

        frame = pd.DataFrame([data])
        if self.feature_cols:
            for col in self.feature_cols:
                if col not in frame.columns:
                    frame[col] = 0.0
            frame = frame[self.feature_cols]
        MLColumnNaming.assert_no_target_leakage(frame.columns)
        return frame

    def _aggregate_monthly_from_predictions(self, values: list[float]) -> tuple[list[float], list[float]]:
        """Agrège les targets prédites en CA et ventes mensuels globaux."""
        ca_monthly = [0.0] * 12
        ventes_monthly = [0.0] * 12
        has_global_ca = False
        has_global_ventes = False

        for col, val in zip(self.target_cols, values):
            v = max(float(val), 0.0)
            col_lower = col.lower()

            match_ca = self.MONTHLY_CA_RE.search(col)
            if match_ca and ("ca_total" in col_lower or col_lower.endswith("montant")):
                month = int(match_ca.group(1))
                if 1 <= month <= 12:
                    if "ca_total" in col_lower:
                        ca_monthly[month - 1] = v
                        has_global_ca = True
                    elif not has_global_ca:
                        ca_monthly[month - 1] += v

            match_v = self.MONTHLY_VENTES_RE.search(col)
            if match_v:
                month = int(match_v.group(1))
                if 1 <= month <= 12:
                    if "ventes_total" in col_lower:
                        ventes_monthly[month - 1] = v
                        has_global_ventes = True
                    elif "nbr_ventes" in col_lower and not has_global_ventes:
                        ventes_monthly[month - 1] += v

        return ca_monthly, ventes_monthly

    def predict_raw(self, request: RodSimulationRequest) -> dict:
        """Prédiction brute CA / ventes par mois (échelle mensuelle cohérente)."""
        ca_monthly = [0.0] * 12
        ventes_monthly = [0.0] * 12

        if self.model is None or not request.store:
            return {
                "model_available": False,
                "ca_monthly": ca_monthly,
                "ventes_monthly": ventes_monthly,
            }

        features = self.request_to_features(request)
        prediction = self.model.predict(features)
        values = prediction[0] if hasattr(prediction, "__len__") else [float(prediction)]
        ca_monthly, ventes_monthly = self._aggregate_monthly_from_predictions(list(values))

        return {
            "model_available": True,
            "ca_monthly": ca_monthly,
            "ventes_monthly": ventes_monthly,
        }

    def predict(self, request: RodSimulationRequest) -> SimulationResult:
        raw = self.predict_raw(request)
        store = request.store
        concept = store.concept if store else "SIMPLY"
        m_lin = store.m_lin if store else 0.0
        ca_annuel = sum(raw["ca_monthly"])
        ca_mensuel = ca_annuel / 12 if ca_annuel else 0.0
        ventes_annuel = sum(raw["ventes_monthly"])
        ventes_mensuel = ventes_annuel / 12 if ventes_annuel else 0.0
        monthly = [
            MonthlyProjection(
                month=month,
                ca=raw["ca_monthly"][month - 1],
                nbr_ventes=raw["ventes_monthly"][month - 1],
            )
            for month in range(1, 13)
        ]
        return SimulationResult(
            source="AI_MODEL",
            concept=concept,
            m_lin=m_lin,
            ca_annuel=ca_annuel,
            nbr_ventes_annuel=ventes_annuel,
            ca_mensuel_moyen=ca_mensuel,
            nbr_ventes_mensuel_moyen=ventes_mensuel,
            marge_annuelle=0.0,
            cout_annuel=0.0,
            roi_months=None,
            monthly=monthly,
            warnings=list(self.load_warnings),
        )