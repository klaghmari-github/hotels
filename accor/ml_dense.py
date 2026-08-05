from __future__ import annotations

import copy
import json
import logging
import math
import os
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import optuna
import pandas as pd
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from main import ConnectionPipeline
from ml_xgboost import MLDatasetBuilder, MLTarget, PreparedDataset


@dataclass(frozen=True)
class DenseConfig:
    dataset_name: str = "v_ml_training_dataset"
    random_state: int = 42
    optuna_trials: int = 50
    optuna_timeout_seconds: int | None = None
    cv_splits: int = 5
    max_epochs: int = 500
    early_stopping_patience: int = 35
    min_delta: float = 1e-5
    reserved_cpus: int = 2
    models_dir: str = "models/dense"
    reports_dir: str = "reports/dense"
    optuna_dir: str = "reports/dense/optuna"

    @property
    def targets(self) -> tuple[MLTarget, ...]:
        return (
            MLTarget(
                "montant_ventes_par_mois",
                "Montant des ventes mensuel",
            ),
            MLTarget(
                "montant_marge_par_mois",
                "Marge mensuelle selon prix marche",
            ),
            MLTarget(
                "montant_marge_selon_coef_par_mois",
                "Marge mensuelle selon coefficient fixe",
            ),
        )


@dataclass(frozen=True)
class DenseHyperParameters:
    hidden_width: int = 64
    residual_blocks: int = 2
    dropout: float = 0.15
    learning_rate: float = 1e-3
    weight_decay: float = 1e-3
    batch_size: int = 64


@dataclass(frozen=True)
class DenseTrainingResult:
    target: str
    best_params: dict[str, Any]
    best_score: float
    recommended_epochs: int
    model_path: str
    metadata_path: str


@dataclass(frozen=True)
class FittedDenseArtifacts:
    model: nn.Module
    feature_scaler: StandardScaler
    target_scaler: StandardScaler
    best_epoch: int
    best_score: float


class ResidualDenseBlock(nn.Module):
    def __init__(
        self,
        width: int,
        dropout: float,
    ):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(width, width),
            nn.LayerNorm(width),
            nn.SiLU(),
            nn.Dropout(dropout),
            nn.Linear(width, width),
            nn.LayerNorm(width),
            nn.Dropout(dropout),
        )
        self.activation = nn.SiLU()

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return self.activation(inputs + self.layers(inputs))


class DenseRegressor(nn.Module):
    def __init__(
        self,
        input_size: int,
        hidden_width: int,
        residual_blocks: int,
        dropout: float,
    ):
        super().__init__()
        self.input_projection = nn.Sequential(
            nn.Linear(input_size, hidden_width),
            nn.LayerNorm(hidden_width),
            nn.SiLU(),
            nn.Dropout(dropout),
        )
        self.blocks = nn.Sequential(
            *[
                ResidualDenseBlock(
                    hidden_width,
                    dropout,
                )
                for _ in range(residual_blocks)
            ]
        )
        self.output_layer = nn.Linear(hidden_width, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        hidden = self.input_projection(inputs)
        hidden = self.blocks(hidden)
        return self.output_layer(hidden).squeeze(-1)


class DenseUtilities:
    @staticmethod
    def set_seed(seed: int) -> None:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    @staticmethod
    def device() -> torch.device:
        return torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

    @staticmethod
    def available_cpus(reserved_cpus: int) -> int:
        return max(1, (os.cpu_count() or 1) - reserved_cpus)

    @staticmethod
    def sample_weights(groups: pd.Series) -> np.ndarray:
        counts = groups.value_counts()
        weights = groups.map(
            lambda group: 1.0 / counts[group]
        ).to_numpy(dtype=np.float32)
        return weights / weights.mean()

    @staticmethod
    def normalized_score(
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> float:
        scale = max(float(np.mean(np.abs(y_true))), 1e-9)
        nmae = mean_absolute_error(y_true, y_pred) / scale
        nrmse = math.sqrt(
            mean_squared_error(y_true, y_pred)
        ) / scale
        return 0.5 * nmae + 0.5 * nrmse

    @staticmethod
    def metrics(
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> dict[str, float]:
        error = y_pred - y_true
        non_zero = np.abs(y_true) > 1e-9
        return {
            "mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": float(
                math.sqrt(mean_squared_error(y_true, y_pred))
            ),
            "mape": (
                float(
                    np.mean(np.abs(error[non_zero] / y_true[non_zero]))
                    * 100.0
                )
                if non_zero.any()
                else np.nan
            ),
            "biais": float(np.mean(error)),
        }


class DenseModelTrainer:
    def __init__(self, config: DenseConfig):
        self.config = config
        torch.set_num_threads(
            DenseUtilities.available_cpus(config.reserved_cpus)
        )

    @staticmethod
    def weighted_mse(
        predictions: torch.Tensor,
        targets: torch.Tensor,
        weights: torch.Tensor,
    ) -> torch.Tensor:
        squared_error = (predictions - targets) ** 2
        return torch.sum(squared_error * weights) / torch.sum(weights)

    def create_model(
        self,
        input_size: int,
        params: dict[str, Any],
    ) -> DenseRegressor:
        return DenseRegressor(
            input_size=input_size,
            hidden_width=int(params["hidden_width"]),
            residual_blocks=int(params["residual_blocks"]),
            dropout=float(params["dropout"]),
        )

    def fit(
        self,
        features_train: pd.DataFrame,
        target_train: np.ndarray,
        groups_train: pd.Series,
        params: dict[str, Any],
        features_validation: pd.DataFrame | None = None,
        target_validation: np.ndarray | None = None,
        epochs: int | None = None,
    ) -> FittedDenseArtifacts:
        DenseUtilities.set_seed(self.config.random_state)
        device = DenseUtilities.device()

        feature_scaler = StandardScaler()
        x_train = feature_scaler.fit_transform(
            features_train.to_numpy(dtype=np.float32)
        ).astype(np.float32)

        target_scaler = StandardScaler()
        y_train = target_scaler.fit_transform(
            target_train.reshape(-1, 1)
        ).ravel().astype(np.float32)

        weights = DenseUtilities.sample_weights(groups_train)
        train_dataset = TensorDataset(
            torch.from_numpy(x_train),
            torch.from_numpy(y_train),
            torch.from_numpy(weights),
        )
        generator = torch.Generator()
        generator.manual_seed(self.config.random_state)
        train_loader = DataLoader(
            train_dataset,
            batch_size=min(int(params["batch_size"]), len(train_dataset)),
            shuffle=True,
            generator=generator,
            num_workers=0,
        )

        model = self.create_model(
            input_size=x_train.shape[1],
            params=params,
        ).to(device)

        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=float(params["learning_rate"]),
            weight_decay=float(params["weight_decay"]),
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="min",
            factor=0.5,
            patience=10,
            min_lr=1e-6,
        )

        validation_available = (
            features_validation is not None
            and target_validation is not None
            and len(features_validation) > 0
        )

        if validation_available:
            x_validation = feature_scaler.transform(
                features_validation.to_numpy(dtype=np.float32)
            ).astype(np.float32)
            validation_tensor = torch.from_numpy(x_validation).to(device)
        else:
            validation_tensor = None

        maximum_epochs = epochs or self.config.max_epochs
        best_state = copy.deepcopy(model.state_dict())
        best_score = float("inf")
        best_epoch = 1
        stale_epochs = 0

        for epoch in range(1, maximum_epochs + 1):
            model.train()
            epoch_loss = 0.0
            epoch_weight = 0.0

            for batch_x, batch_y, batch_weights in train_loader:
                batch_x = batch_x.to(device)
                batch_y = batch_y.to(device)
                batch_weights = batch_weights.to(device)

                optimizer.zero_grad(set_to_none=True)
                predictions = model(batch_x)
                loss = self.weighted_mse(
                    predictions,
                    batch_y,
                    batch_weights,
                )
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(),
                    max_norm=5.0,
                )
                optimizer.step()

                epoch_loss += float(loss.detach().cpu()) * len(batch_x)
                epoch_weight += len(batch_x)

            training_loss = epoch_loss / max(epoch_weight, 1.0)

            if validation_available and validation_tensor is not None:
                model.eval()
                with torch.no_grad():
                    validation_scaled = (
                        model(validation_tensor)
                        .detach()
                        .cpu()
                        .numpy()
                    )
                validation_prediction = target_scaler.inverse_transform(
                    validation_scaled.reshape(-1, 1)
                ).ravel()
                validation_prediction = np.maximum(
                    validation_prediction,
                    0.0,
                )
                current_score = DenseUtilities.normalized_score(
                    target_validation,
                    validation_prediction,
                )
            else:
                current_score = training_loss

            scheduler.step(current_score)

            if current_score < best_score - self.config.min_delta:
                best_score = float(current_score)
                best_epoch = epoch
                best_state = copy.deepcopy(model.state_dict())
                stale_epochs = 0
            else:
                stale_epochs += 1

            if (
                validation_available
                and stale_epochs >= self.config.early_stopping_patience
            ):
                break

        model.load_state_dict(best_state)
        model.eval()

        return FittedDenseArtifacts(
            model=model,
            feature_scaler=feature_scaler,
            target_scaler=target_scaler,
            best_epoch=best_epoch,
            best_score=best_score,
        )

    @staticmethod
    def predict(
        artifacts: FittedDenseArtifacts,
        features: pd.DataFrame,
    ) -> np.ndarray:
        device = DenseUtilities.device()
        x = artifacts.feature_scaler.transform(
            features.to_numpy(dtype=np.float32)
        ).astype(np.float32)
        tensor = torch.from_numpy(x).to(device)
        artifacts.model.eval()
        with torch.no_grad():
            scaled = artifacts.model(tensor).cpu().numpy()
        prediction = artifacts.target_scaler.inverse_transform(
            scaled.reshape(-1, 1)
        ).ravel()
        return np.maximum(prediction, 0.0)


class DenseParameterOptimizer:
    def __init__(
        self,
        config: DenseConfig,
        project_dir: str | Path,
    ):
        self.config = config
        self.project_dir = Path(project_dir).resolve()
        self.optuna_dir = self.project_dir / config.optuna_dir
        self.optuna_dir.mkdir(parents=True, exist_ok=True)
        self.trainer = DenseModelTrainer(config)

    @staticmethod
    def suggested_params(trial: optuna.Trial) -> dict[str, Any]:
        return {
            "hidden_width": trial.suggest_categorical(
                "hidden_width",
                [16, 32, 48, 64, 96],
            ),
            "residual_blocks": trial.suggest_int(
                "residual_blocks",
                1,
                3,
            ),
            "dropout": trial.suggest_float(
                "dropout",
                0.05,
                0.35,
            ),
            "learning_rate": trial.suggest_float(
                "learning_rate",
                2e-4,
                5e-3,
                log=True,
            ),
            "weight_decay": trial.suggest_float(
                "weight_decay",
                1e-6,
                5e-2,
                log=True,
            ),
            "batch_size": trial.suggest_categorical(
                "batch_size",
                [16, 32, 64, 128],
            ),
        }

    def optimize(
        self,
        prepared: PreparedDataset,
        target: str,
    ) -> tuple[dict[str, Any], float, int, pd.DataFrame]:
        distinct_groups = prepared.groups.nunique()
        n_splits = min(self.config.cv_splits, distinct_groups)
        if n_splits < 2:
            raise ValueError(
                "Au moins deux hotels sont necessaires pour optimiser le reseau."
            )

        splitter = GroupKFold(n_splits=n_splits)
        target_values = prepared.source[target].to_numpy(dtype=float)
        storage_path = self.optuna_dir / f"{target}.sqlite3"
        study = optuna.create_study(
            study_name=f"dense_{target}",
            storage=f"sqlite:///{storage_path}",
            load_if_exists=True,
            direction="minimize",
            sampler=optuna.samplers.TPESampler(
                seed=self.config.random_state
            ),
            pruner=optuna.pruners.MedianPruner(
                n_startup_trials=8,
                n_warmup_steps=1,
            ),
        )

        def objective(trial: optuna.Trial) -> float:
            params = self.suggested_params(trial)
            scores: list[float] = []
            best_epochs: list[int] = []

            for fold_index, (train_index, validation_index) in enumerate(
                splitter.split(
                    prepared.features,
                    target_values,
                    prepared.groups,
                ),
                start=1,
            ):
                validation_observation_mask = (
                    prepared.observation_mask.iloc[validation_index]
                    .to_numpy(dtype=bool)
                )
                evaluation_index = validation_index[
                    validation_observation_mask
                ]
                if len(evaluation_index) == 0:
                    raise ValueError(
                        "Aucune observation reelle dans le fold de validation."
                    )

                artifacts = self.trainer.fit(
                    features_train=prepared.features.iloc[train_index],
                    target_train=target_values[train_index],
                    groups_train=prepared.groups.iloc[train_index],
                    params=params,
                    features_validation=prepared.features.iloc[evaluation_index],
                    target_validation=target_values[evaluation_index],
                )
                prediction = self.trainer.predict(
                    artifacts,
                    prepared.features.iloc[evaluation_index],
                )
                score = DenseUtilities.normalized_score(
                    target_values[evaluation_index],
                    prediction,
                )
                scores.append(score)
                best_epochs.append(artifacts.best_epoch)

                trial.report(float(np.mean(scores)), step=fold_index)
                if trial.should_prune():
                    raise optuna.TrialPruned()

            trial.set_user_attr(
                "recommended_epochs",
                int(np.median(best_epochs)),
            )
            return float(np.mean(scores))

        completed = sum(
            trial.state == optuna.trial.TrialState.COMPLETE
            for trial in study.trials
        )
        remaining = max(0, self.config.optuna_trials - completed)
        if remaining > 0:
            logging.info(
                "Optimisation dense %s : %s nouveaux essais",
                target,
                remaining,
            )
            study.optimize(
                objective,
                n_trials=remaining,
                timeout=self.config.optuna_timeout_seconds,
                n_jobs=1,
                show_progress_bar=False,
            )

        trials = study.trials_dataframe()
        trials.to_csv(
            self.optuna_dir / f"{target}_trials.csv",
            index=False,
        )
        recommended_epochs = int(
            study.best_trial.user_attrs.get(
                "recommended_epochs",
                100,
            )
        )
        return (
            study.best_params,
            float(study.best_value),
            max(1, recommended_epochs),
            trials,
        )


class DenseFinalModelTrainer:
    def __init__(
        self,
        config: DenseConfig,
        project_dir: str | Path,
    ):
        self.config = config
        self.project_dir = Path(project_dir).resolve()
        self.models_dir = self.project_dir / config.models_dir
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.trainer = DenseModelTrainer(config)

    def train(
        self,
        prepared: PreparedDataset,
        target: MLTarget,
        params: dict[str, Any],
        best_score: float,
        epochs: int,
    ) -> DenseTrainingResult:
        artifacts = self.trainer.fit(
            features_train=prepared.features,
            target_train=prepared.source[target.name].to_numpy(dtype=float),
            groups_train=prepared.groups,
            params=params,
            epochs=epochs,
        )

        model_path = self.models_dir / f"{target.name}.pt"
        metadata_path = self.models_dir / f"{target.name}_metadata.json"
        scaler_path = self.models_dir / f"{target.name}_scalers.joblib"

        torch.save(
            {
                "state_dict": artifacts.model.state_dict(),
                "input_size": len(prepared.feature_names),
                "params": params,
                "feature_names": prepared.feature_names,
            },
            model_path,
        )
        joblib.dump(
            {
                "feature_scaler": artifacts.feature_scaler,
                "target_scaler": artifacts.target_scaler,
            },
            scaler_path,
        )
        metadata = {
            "target": target.name,
            "target_label": target.label,
            "feature_names": prepared.feature_names,
            "params": params,
            "recommended_epochs": epochs,
            "best_cv_score": best_score,
            "training_rows": len(prepared.source),
            "training_hotels": int(prepared.groups.nunique()),
            "device": str(DenseUtilities.device()),
            "scaler_path": str(scaler_path),
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return DenseTrainingResult(
            target=target.name,
            best_params=params,
            best_score=best_score,
            recommended_epochs=epochs,
            model_path=str(model_path),
            metadata_path=str(metadata_path),
        )


class DenseLeaveOneHotelOutEvaluator:
    def __init__(
        self,
        config: DenseConfig,
        project_dir: str | Path,
    ):
        self.config = config
        self.project_dir = Path(project_dir).resolve()
        self.reports_dir = self.project_dir / config.reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.trainer = DenseModelTrainer(config)

    def evaluate(
        self,
        prepared: PreparedDataset,
        params_by_target: dict[str, dict[str, Any]],
        epochs_by_target: dict[str, int],
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        observations = prepared.source[prepared.observation_mask]
        hotel_codes = sorted(observations["hotel_code"].astype(str).unique())
        rows: list[dict[str, Any]] = []

        for index, hotel_code in enumerate(hotel_codes, start=1):
            logging.info(
                "Evaluation dense LOO %s/%s | hotel=%s",
                index,
                len(hotel_codes),
                hotel_code,
            )
            train_mask = prepared.groups.astype(str) != hotel_code
            test_mask = (
                prepared.observation_mask
                & (prepared.groups.astype(str) == hotel_code)
            )
            if int(test_mask.sum()) != 1:
                raise ValueError(
                    f"Observation unique introuvable pour {hotel_code}"
                )

            source_row = prepared.source.loc[test_mask].iloc[0]
            row: dict[str, Any] = {
                "hotel_code": hotel_code,
                "solution": source_row["solution"],
                "solution_vue_en_apprentissage": bool(
                    (
                        prepared.source.loc[train_mask, "solution"]
                        == source_row["solution"]
                    ).any()
                ),
            }

            for target in self.config.targets:
                artifacts = self.trainer.fit(
                    features_train=prepared.features.loc[train_mask],
                    target_train=prepared.source.loc[
                        train_mask,
                        target.name,
                    ].to_numpy(dtype=float),
                    groups_train=prepared.groups.loc[train_mask],
                    params=params_by_target[target.name],
                    epochs=epochs_by_target[target.name],
                )
                prediction = float(
                    self.trainer.predict(
                        artifacts,
                        prepared.features.loc[test_mask],
                    )[0]
                )
                actual = float(source_row[target.name])
                row[f"{target.name}_reel"] = actual
                row[f"{target.name}_predit"] = prediction
                row[f"{target.name}_erreur"] = prediction - actual
                row[f"{target.name}_erreur_absolue"] = abs(
                    prediction - actual
                )

            rows.append(row)

        predictions = pd.DataFrame(rows)
        metric_rows: list[dict[str, Any]] = []
        for target in self.config.targets:
            y_true = predictions[f"{target.name}_reel"].to_numpy(dtype=float)
            y_pred = predictions[f"{target.name}_predit"].to_numpy(dtype=float)
            metric_rows.append(
                {
                    "target": target.name,
                    "target_label": target.label,
                    "nombre_hotels": len(predictions),
                    **DenseUtilities.metrics(y_true, y_pred),
                }
            )
        metrics = pd.DataFrame(metric_rows)

        report_path = self.reports_dir / "leave_one_hotel_out.xlsx"
        with pd.ExcelWriter(report_path) as writer:
            predictions.to_excel(writer, sheet_name="predictions", index=False)
            metrics.to_excel(writer, sheet_name="metrics", index=False)

        return predictions, metrics


class DenseWorkflow:
    def __init__(
        self,
        cp: ConnectionPipeline,
        config: DenseConfig | None = None,
    ):
        self.cp = cp
        self.config = config or DenseConfig()
        self.project_dir = cp.project_dir
        self.dataset_builder = MLDatasetBuilder(
            cp,
            self._dataset_config(),
        )
        self.optimizer = DenseParameterOptimizer(
            self.config,
            self.project_dir,
        )
        self.final_trainer = DenseFinalModelTrainer(
            self.config,
            self.project_dir,
        )
        self.evaluator = DenseLeaveOneHotelOutEvaluator(
            self.config,
            self.project_dir,
        )

    def _dataset_config(self):
        class DatasetConfigAdapter:
            dataset_name = self.config.dataset_name
            targets = self.config.targets
        return DatasetConfigAdapter()

    def run(self) -> dict[str, Any]:
        prepared = self.dataset_builder.prepare()
        params_by_target: dict[str, dict[str, Any]] = {}
        epochs_by_target: dict[str, int] = {}
        training_results: list[DenseTrainingResult] = []
        optuna_trials: dict[str, pd.DataFrame] = {}

        for target in self.config.targets:
            params, score, epochs, trials = self.optimizer.optimize(
                prepared,
                target.name,
            )
            params_by_target[target.name] = params
            epochs_by_target[target.name] = epochs
            optuna_trials[target.name] = trials
            training_results.append(
                self.final_trainer.train(
                    prepared,
                    target,
                    params,
                    score,
                    epochs,
                )
            )

        loo_predictions, loo_metrics = self.evaluator.evaluate(
            prepared,
            params_by_target,
            epochs_by_target,
        )

        summary = pd.DataFrame(
            [
                {
                    "target": result.target,
                    "best_cv_score": result.best_score,
                    "recommended_epochs": result.recommended_epochs,
                    **result.best_params,
                }
                for result in training_results
            ]
        )
        summary_path = self.project_dir / self.config.reports_dir / "training_summary.xlsx"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary.to_excel(summary_path, index=False)

        return {
            "prepared_dataset": prepared,
            "training_results": training_results,
            "training_summary": summary,
            "loo_predictions": loo_predictions,
            "loo_metrics": loo_metrics,
            "optuna_trials": optuna_trials,
        }
