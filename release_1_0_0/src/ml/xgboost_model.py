"""
Modele XGBoost multi-cibles + leave-one-hotel-out.

Variants :
  - ml1 : uniquement liste de simulations sim_v2 (v_ml_training_dataset)
  - ml2 : sim_v2 + rich (proximite, weather moyennee, hotel_data) + brand
  - xgboost (legacy) : alias ml2 / rich
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from xgboost import XGBRegressor

from src.ml.common import (
    TARGETS,
    build_feature_row,
    feature_matrix,
    load_ml_dataset,
    metrics_frame,
)
from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths

logger = logging.getLogger(__name__)

Variant = Literal["ml1", "ml2", "xgboost"]


@dataclass(frozen=True)
class XGBoostConfig:
    n_estimators: int = 600
    learning_rate: float = 0.05
    max_depth: int = 5
    min_child_weight: float = 3.0
    subsample: float = 0.85
    colsample_bytree: float = 0.85
    reg_lambda: float = 2.0
    reg_alpha: float = 0.1
    early_stopping_rounds: int = 50
    random_seed: int = 42
    n_jobs: int = -1
    verbosity: int = 0


class XGBoostService:
    """
    variant=ml1  → dataset sim_v2 pre-agreg (lignes scenarios)
    variant=ml2  → rich + brand (px/wx moyen / hd / br_)
    variant=xgboost → legacy, meme que ml2, dossier models/xgboost
    """

    def __init__(
        self,
        paths: Paths | None = None,
        config: XGBoostConfig | None = None,
        factory: PipelineFactory | None = None,
        *,
        variant: Variant = "xgboost",
    ):
        self.paths = (paths or Paths()).ensure()
        self.config = config or XGBoostConfig()
        self.factory = factory or PipelineFactory(self.paths)
        self.variant: Variant = variant  # type: ignore[assignment]
        if variant == "ml1":
            self.models_dir = self.paths.models_ml1
            self.eval_name = "eval_ml1_loo.xlsx"
            self.engine_name = "ml1"
            self.dataset_mode = "sim_v2"
        elif variant == "ml2":
            self.models_dir = self.paths.models_ml2
            self.eval_name = "eval_ml2_loo.xlsx"
            self.engine_name = "ml2"
            self.dataset_mode = "ml2"
        else:
            self.models_dir = self.paths.models_xgboost
            self.eval_name = "eval_xgboost_loo.xlsx"
            self.engine_name = "xgboost"
            self.dataset_mode = "rich"
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def load_dataset(self) -> pd.DataFrame:
        return load_ml_dataset(
            self.paths,
            self.factory,
            mode=self.dataset_mode,
        )

    def feature_matrix(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        return feature_matrix(df)

    def _model_params(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "n_estimators": cfg.n_estimators,
            "learning_rate": cfg.learning_rate,
            "max_depth": cfg.max_depth,
            "min_child_weight": cfg.min_child_weight,
            "subsample": cfg.subsample,
            "colsample_bytree": cfg.colsample_bytree,
            "reg_lambda": cfg.reg_lambda,
            "reg_alpha": cfg.reg_alpha,
            "random_state": cfg.random_seed,
            "n_jobs": cfg.n_jobs,
            "verbosity": cfg.verbosity,
            "objective": "reg:squarederror",
            "tree_method": "hist",
        }

    def _fit_one(
        self,
        x_train: pd.DataFrame,
        y_train: np.ndarray,
        groups: pd.Series | None = None,
    ) -> XGBRegressor:
        params = self._model_params()
        model = XGBRegressor(**params)
        if groups is not None and groups.nunique() >= 3:
            gkf = GroupKFold(n_splits=min(3, groups.nunique()))
            tr_idx, va_idx = next(gkf.split(x_train, y_train, groups))
            model.set_params(early_stopping_rounds=self.config.early_stopping_rounds)
            model.fit(
                x_train.iloc[tr_idx],
                y_train[tr_idx],
                eval_set=[(x_train.iloc[va_idx], y_train[va_idx])],
                verbose=False,
            )
        else:
            model.fit(x_train, y_train, verbose=False)
        return model

    def train_final(self, df: pd.DataFrame | None = None) -> list[dict[str, Any]]:
        df = df if df is not None else self.load_dataset()
        features, feature_names = self.feature_matrix(df)
        results: list[dict[str, Any]] = []
        for target, label in TARGETS:
            y = df[target].to_numpy(dtype=float)
            model = self._fit_one(features, y)
            model_path = self.models_dir / f"{target}.json"
            meta_path = self.models_dir / f"{target}_metadata.json"
            model.save_model(str(model_path))
            meta = {
                "target": target,
                "target_label": label,
                "feature_names": feature_names,
                "params": self._model_params(),
                "training_rows": len(df),
                "training_hotels": int(df["hotel_code"].nunique()),
                "engine": self.engine_name,
                "variant": self.variant,
                "dataset_source": df.attrs.get("ml_source"),
                "n_features": len(feature_names),
            }
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results.append(meta)
            logger.info(
                "Modele %s sauve : %s (%s feats)",
                self.engine_name,
                model_path.name,
                len(feature_names),
            )
        return results

    def leave_one_hotel_out(
        self,
        df: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = df if df is not None else self.load_dataset()
        features, _ = self.feature_matrix(df)
        groups = df["hotel_code"].astype(str)
        observation = df["is_observation"]
        hotels = sorted(df.loc[observation, "hotel_code"].astype(str).unique())

        rows: list[dict[str, Any]] = []
        for index, hotel in enumerate(hotels, start=1):
            logger.info(
                "%s LOO %s/%s | hotel=%s",
                self.engine_name,
                index,
                len(hotels),
                hotel,
            )
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
            train_groups = groups.loc[train_mask]

            for target, _label in TARGETS:
                y_train = df.loc[train_mask, target].to_numpy(dtype=float)
                model = self._fit_one(x_train, y_train, train_groups)
                pred = float(model.predict(x_test)[0])
                actual = float(source[target])
                row[f"{target}_reel"] = actual
                row[f"{target}_predit"] = pred
                row[f"{target}_erreur"] = pred - actual
                row[f"{target}_erreur_absolue"] = abs(pred - actual)
            rows.append(row)

        predictions = pd.DataFrame(rows)
        return predictions, metrics_frame(predictions)

    def export_loo(
        self,
        predictions: pd.DataFrame | None = None,
        metrics: pd.DataFrame | None = None,
    ) -> Path:
        if predictions is None or metrics is None:
            predictions, metrics = self.leave_one_hotel_out()
        path = self.paths.out_ml(self.eval_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        resume = metrics.copy()
        resume.insert(0, "source", self.engine_name)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            predictions.to_excel(writer, sheet_name="predictions", index=False)
            metrics.to_excel(writer, sheet_name="metrics", index=False)
            resume.to_excel(writer, sheet_name="resume", index=False)
        logger.info("Export %s LOO : %s", self.engine_name, path)
        return path

    def predict_row(self, feature_row: dict[str, float], solution: str) -> dict[str, float]:
        targets = [t for t, _ in TARGETS]
        meta_path = self.models_dir / f"{targets[0]}_metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"Modeles {self.engine_name} absents. "
                f"Lancer : python run.py {self.engine_name} --rebuild"
            )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        feature_names: list[str] = meta["feature_names"]
        x = build_feature_row(feature_names, feature_row, solution)
        out: dict[str, float] = {"solution": solution, "engine": self.engine_name}
        for target in targets:
            model = XGBRegressor()
            model.load_model(str(self.models_dir / f"{target}.json"))
            out[target] = max(float(model.predict(x)[0]), 0.0)
        return out

    def hotel_enrichment_features(self, hotel_code: str | None) -> dict[str, float]:
        """Features hotel (px/wx/hd/br) pour prediction ml2 si hotel connu."""
        if not hotel_code or self.variant == "ml1":
            return {}
        cp = self.factory.open(read_only=False)
        try:
            feats: dict[str, float] = {}
            try:
                rich = cp.p_table_view("t_rich_data").df()
                sub = rich.loc[rich["hotel_code"].astype(str) == str(hotel_code)]
                if not sub.empty:
                    row = sub.iloc[0]
                    for c, v in row.items():
                        if str(c).startswith(("hd_", "px_", "wx_", "hol_")):
                            try:
                                feats[str(c)] = float(v)
                            except (TypeError, ValueError):
                                pass
            except Exception:
                pass
            # brand
            try:
                from src.ml.common import _attach_brand_features

                tiny = pd.DataFrame(
                    [{"hotel_code": str(hotel_code), "solution": "simply"}]
                )
                br = _attach_brand_features(tiny, cp)
                for c in br.columns:
                    if str(c).startswith("br_"):
                        try:
                            feats[str(c)] = float(br.iloc[0][c])
                        except (TypeError, ValueError):
                            feats[str(c)] = 0.0
            except Exception:
                pass
            return feats
        finally:
            cp.close()

    def run_full(self) -> dict[str, Any]:
        df = self.load_dataset()
        logger.info(
            "%s dataset: source=%s rows=%s hotels=%s cols=%s",
            self.engine_name,
            df.attrs.get("ml_source"),
            len(df),
            df["hotel_code"].nunique(),
            df.shape[1],
        )
        self.train_final(df)
        predictions, metrics = self.leave_one_hotel_out(df)
        path = self.export_loo(predictions, metrics)
        return {
            "predictions": predictions,
            "metrics": metrics,
            "excel": path,
            "engine": self.engine_name,
            "source": df.attrs.get("ml_source"),
        }


def ML1Service(paths: Paths | None = None, **kwargs) -> XGBoostService:
    return XGBoostService(paths, variant="ml1", **kwargs)


def ML2Service(paths: Paths | None = None, **kwargs) -> XGBoostService:
    return XGBoostService(paths, variant="ml2", **kwargs)
