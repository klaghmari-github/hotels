"""Entraînement XGBoost sur targets globales mensuelles (init.sh)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.multioutput import MultiOutputRegressor
from xgboost import XGBRegressor

from rod_ia.domain.services.ml_column_naming import MLColumnNaming


class ModelTrainer:
    """Entraîne et persiste le modèle IA consommé par run.sh."""

    def __init__(self, processed_dir: Path, artifacts_dir: Path) -> None:
        self.processed_dir = Path(processed_dir)
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _load_dataset(self) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
        meta_path = self.processed_dir / "dataset_meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"Dataset absent: {meta_path}. Exécuter le pipeline SalesTargetsPipeline."
            )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        feature_cols = meta["feature_cols"]
        all_targets = meta["target_cols"]
        global_targets = meta.get("global_target_cols") or [
            c for c in all_targets if "ca_total" in c or "ventes_total" in c
        ]
        if not global_targets:
            global_targets = all_targets[:24]

        x_path = self.processed_dir / "X_descriptive.csv"
        y_path = self.processed_dir / "y_targets.csv"
        x_frame = pd.read_csv(x_path).fillna(0.0)
        y_frame = pd.read_csv(y_path).fillna(0.0)

        for col in feature_cols:
            if col not in x_frame.columns:
                x_frame[col] = 0.0
        for col in global_targets:
            if col not in y_frame.columns:
                y_frame[col] = 0.0

        return x_frame[feature_cols], y_frame[global_targets], feature_cols, global_targets

    def train(self) -> dict:
        x_train, y_train, feature_cols, target_cols = self._load_dataset()
        if len(x_train) < 2:
            raise ValueError(
                f"Pas assez d'hôtels pour entraîner ({len(x_train)}). "
                "Compléter le registre identité et les ventes."
            )

        base = XGBRegressor(
            n_estimators=120,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
        )
        model = MultiOutputRegressor(base)
        model.fit(x_train.values, y_train.values)

        joblib.dump(model, self.artifacts_dir / "model.joblib")
        (self.artifacts_dir / "feature_cols.json").write_text(
            json.dumps(feature_cols, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (self.artifacts_dir / "target_cols.json").write_text(
            json.dumps(target_cols, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        train_pred = model.predict(x_train.values)
        mae = float(np.mean(np.abs(train_pred - y_train.values)))
        meta = {
            "n_hotels": len(x_train),
            "n_features": len(feature_cols),
            "n_targets": len(target_cols),
            "train_mae": mae,
            "model": "MultiOutputRegressor(XGBRegressor)",
        }
        (self.artifacts_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return meta