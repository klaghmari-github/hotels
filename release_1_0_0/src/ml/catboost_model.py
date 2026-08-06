"""
Modele CatBoost multi-cibles + leave-one-hotel-out.

Dataset : t_rich_data (sim_v2 + hotel_data/proximity/weather/holidays)
          fallback v_ml_training_dataset.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold

from src.ml.common import (
    CONTEXT_FEATURES,
    TARGETS,
    feature_matrix as common_feature_matrix,
    load_ml_dataset,
    metrics_frame as common_metrics_frame,
    mix_columns,
)
from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths
from src.pipeline.scope import is_excluded

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatBoostConfig:
    """
    Hyperparametres choisis pour un petit volume hotelier (quelques hotels,
    beaucoup de scenarios d'assortiment).
    """

    iterations: int = 800
    learning_rate: float = 0.05
    depth: int = 6
    l2_leaf_reg: float = 6.0
    random_strength: float = 1.0
    bagging_temperature: float = 0.5
    subsample: float = 0.85
    min_data_in_leaf: int = 8
    early_stopping_rounds: int = 60
    random_seed: int = 42
    # leave-one-out : un modele par hotel exclus
    thread_count: int = -1
    verbose: bool = False


class CatBoostService:
    def __init__(
        self,
        paths: Paths | None = None,
        config: CatBoostConfig | None = None,
        factory: PipelineFactory | None = None,
    ):
        self.paths = (paths or Paths()).ensure()
        self.config = config or CatBoostConfig()
        self.factory = factory or PipelineFactory(self.paths)
        self.models_dir = self.paths.models_catboost
        self.models_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ data
    def load_dataset(self) -> pd.DataFrame:
        """t_rich_data si dispo (features hotel enrichies), sinon v_ml_training_dataset."""
        return load_ml_dataset(self.paths, self.factory, prefer_rich=True)

    @staticmethod
    def mix_columns(df: pd.DataFrame) -> list[str]:
        return mix_columns(df)

    def feature_matrix(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        return common_feature_matrix(df)

    def _model_params(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "loss_function": "RMSE",
            "eval_metric": "MAE",
            "iterations": cfg.iterations,
            "learning_rate": cfg.learning_rate,
            "depth": cfg.depth,
            "l2_leaf_reg": cfg.l2_leaf_reg,
            "random_strength": cfg.random_strength,
            "bagging_temperature": cfg.bagging_temperature,
            "subsample": cfg.subsample,
            "min_data_in_leaf": cfg.min_data_in_leaf,
            "random_seed": cfg.random_seed,
            "thread_count": cfg.thread_count,
            "verbose": cfg.verbose,
            "allow_writing_files": False,
        }

    # ------------------------------------------------------------------ train final
    def train_final(self, df: pd.DataFrame | None = None) -> list[dict[str, Any]]:
        """Entrainement final sur tout le dataset (modeles de production)."""
        df = df if df is not None else self.load_dataset()
        features, feature_names = self.feature_matrix(df)
        results: list[dict[str, Any]] = []

        for target, label in TARGETS:
            y = df[target].to_numpy(dtype=float)
            model = CatBoostRegressor(**self._model_params())
            model.fit(Pool(features, y))
            model_path = self.models_dir / f"{target}.cbm"
            meta_path = self.models_dir / f"{target}_metadata.json"
            model.save_model(str(model_path))
            meta = {
                "target": target,
                "target_label": label,
                "feature_names": feature_names,
                "params": self._model_params(),
                "training_rows": len(df),
                "training_hotels": int(df["hotel_code"].nunique()),
            }
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results.append(meta)
            logger.info("Modele CatBoost sauve : %s", model_path.name)

        return results

    # ------------------------------------------------------------------ LOO
    def leave_one_hotel_out(
        self,
        df: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Pour chaque hotel : train sur les autres, predire l'observation reelle.
        """
        df = df if df is not None else self.load_dataset()
        df = df.copy()
        df["hotel_code"] = df["hotel_code"].astype(str)
        # Perimetre 6 hotels (exclure H5586 etc.) — load_ml_dataset filtre deja
        df = df.loc[~df["hotel_code"].map(is_excluded)].reset_index(drop=True)
        features, _ = self.feature_matrix(df)
        groups = df["hotel_code"].astype(str)
        observation = df["is_observation"]
        hotels = sorted(df.loc[observation, "hotel_code"].astype(str).unique())

        rows: list[dict[str, Any]] = []
        for index, hotel in enumerate(hotels, start=1):
            logger.info("CatBoost LOO %s/%s | hotel=%s", index, len(hotels), hotel)
            train_mask = groups != hotel
            test_mask = observation & (groups == hotel)
            if int(test_mask.sum()) != 1:
                raise ValueError(
                    f"Observation unique attendue pour {hotel}, "
                    f"trouve {int(test_mask.sum())}"
                )

            source = df.loc[test_mask].iloc[0]
            row: dict[str, Any] = {
                "hotel_code": hotel,
                "solution": source["solution"],
            }
            x_train = features.loc[train_mask]
            x_test = features.loc[test_mask]

            for target, _label in TARGETS:
                y_train = df.loc[train_mask, target].to_numpy(dtype=float)
                model = CatBoostRegressor(**self._model_params())
                # early stopping sur un split interne hotel-aware si assez d'hotels
                train_groups = groups.loc[train_mask]
                if train_groups.nunique() >= 3:
                    gkf = GroupKFold(n_splits=min(3, train_groups.nunique()))
                    tr_idx, va_idx = next(
                        gkf.split(x_train, y_train, train_groups)
                    )
                    model.fit(
                        Pool(x_train.iloc[tr_idx], y_train[tr_idx]),
                        eval_set=Pool(x_train.iloc[va_idx], y_train[va_idx]),
                        early_stopping_rounds=self.config.early_stopping_rounds,
                        use_best_model=True,
                    )
                else:
                    model.fit(Pool(x_train, y_train))

                pred = float(model.predict(x_test)[0])
                actual = float(source[target])
                row[f"{target}_reel"] = actual
                row[f"{target}_predit"] = pred
                row[f"{target}_erreur"] = pred - actual
                row[f"{target}_erreur_absolue"] = abs(pred - actual)

            rows.append(row)

        predictions = pd.DataFrame(rows)
        metrics = common_metrics_frame(predictions)
        return predictions, metrics

    def _metrics_frame(self, predictions: pd.DataFrame) -> pd.DataFrame:
        return common_metrics_frame(predictions)

    def export_loo(
        self,
        predictions: pd.DataFrame | None = None,
        metrics: pd.DataFrame | None = None,
    ) -> Path:
        if predictions is None or metrics is None:
            predictions, metrics = self.leave_one_hotel_out()
        path = self.paths.out_ml("eval_catboost_loo.xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        resume = metrics.copy()
        resume.insert(0, "source", "catboost")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            predictions.to_excel(writer, sheet_name="predictions", index=False)
            metrics.to_excel(writer, sheet_name="metrics", index=False)
            resume.to_excel(writer, sheet_name="resume", index=False)
        # copie rapport interne
        report = self.paths.output_ml / "catboost_leave_one_hotel_out.xlsx"
        with pd.ExcelWriter(report, engine="openpyxl") as writer:
            predictions.to_excel(writer, sheet_name="predictions", index=False)
            metrics.to_excel(writer, sheet_name="metrics", index=False)
        logger.info("Export CatBoost LOO : %s", path)
        return path

    def predict_row(self, feature_row: dict[str, float], solution: str) -> dict[str, float]:
        """Prediction production a partir d'un vecteur features."""
        targets = [t for t, _ in TARGETS]
        meta_path = self.models_dir / f"{targets[0]}_metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                "Modeles CatBoost absents. Lancer : python run.py ml --rebuild"
            )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        feature_names: list[str] = meta["feature_names"]
        row = {name: 0.0 for name in feature_names}
        for k, v in feature_row.items():
            if k in row:
                row[k] = float(v)
        sol_col = f"solution_{solution.lower()}"
        for name in feature_names:
            if name.startswith("solution_"):
                row[name] = 1.0 if name == sol_col or name.endswith(solution.lower()) else 0.0

        x = pd.DataFrame([row])[feature_names].astype(float)
        out: dict[str, float] = {"solution": solution}
        for target in targets:
            model = CatBoostRegressor()
            model.load_model(str(self.models_dir / f"{target}.cbm"))
            out[target] = max(float(model.predict(x)[0]), 0.0)
        return out

    def run_full(self) -> dict[str, Any]:
        df = self.load_dataset()
        self.train_final(df)
        predictions, metrics = self.leave_one_hotel_out(df)
        path = self.export_loo(predictions, metrics)
        return {
            "predictions": predictions,
            "metrics": metrics,
            "excel": path,
        }
