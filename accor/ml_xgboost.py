from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import optuna
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GroupKFold
from xgboost import XGBRegressor

from main import ConnectionPipeline


@dataclass(frozen=True)
class MLTarget:
    name: str
    label: str


@dataclass(frozen=True)
class MLConfig:
    dataset_name: str = "v_ml_training_dataset"
    random_state: int = 42
    optuna_trials: int = 80
    optuna_timeout_seconds: int | None = None
    cv_splits: int = 5
    reserved_cpus: int = 2
    models_dir: str = "models/xgboost"
    reports_dir: str = "reports/xgboost"
    optuna_dir: str = "reports/xgboost/optuna"

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
class PreparedDataset:
    source: pd.DataFrame
    features: pd.DataFrame
    feature_names: list[str]
    groups: pd.Series
    observation_mask: pd.Series


@dataclass(frozen=True)
class TargetTrainingResult:
    target: str
    best_params: dict[str, Any]
    best_score: float
    model_path: str
    metadata_path: str


class MLDatasetBuilder:
    CONTEXT_FEATURES = [
        "hotel_nb_chambres",
        "hotel_to_annuel",
        "hotel_guests_per_chambre",
        "metres_lineaires",
    ]

    REQUIRED_COLUMNS = {
        "scenario_id",
        "hotel_code",
        "solution",
        "is_observation",
        "hotel_nb_chambres",
        "hotel_to_annuel",
        "hotel_guests_per_chambre",
        "metres_lineaires",
        "montant_ventes_par_mois",
        "montant_marge_par_mois",
        "montant_marge_selon_coef_par_mois",
    }

    def __init__(
        self,
        cp: ConnectionPipeline,
        config: MLConfig,
    ):
        self.cp = cp
        self.config = config

    def load(self) -> pd.DataFrame:
        dataframe = self.cp.p_table_view(
            self.config.dataset_name
        ).df()

        missing = self.REQUIRED_COLUMNS.difference(
            dataframe.columns
        )

        if missing:
            raise ValueError(
                "Colonnes manquantes dans le dataset ML : "
                + ", ".join(sorted(missing))
            )

        if dataframe.empty:
            raise ValueError(
                "Le dataset ML est vide. La table t_dataset_pivot "
                "doit etre alimentee avant l'entrainement."
            )

        dataframe = dataframe.copy()
        dataframe["hotel_code"] = (
            dataframe["hotel_code"].astype(str)
        )
        dataframe["solution"] = (
            dataframe["solution"].astype(str)
        )
        dataframe["is_observation"] = (
            dataframe["is_observation"].astype(bool)
        )

        return dataframe

    @staticmethod
    def mix_columns(dataframe: pd.DataFrame) -> list[str]:
        return sorted(
            column
            for column in dataframe.columns
            if (
                column.startswith("type_")
                or column.startswith("gamme_")
            )
            and column.endswith("_part_natures")
        )

    def validate(self, dataframe: pd.DataFrame) -> None:
        mix_columns = self.mix_columns(dataframe)

        if not mix_columns:
            raise ValueError(
                "Aucune colonne de part type ou gamme n'a ete trouvee."
            )

        numeric_columns = [
            *self.CONTEXT_FEATURES,
            *mix_columns,
            *[target.name for target in self.config.targets],
        ]

        null_columns = [
            column
            for column in numeric_columns
            if dataframe[column].isna().any()
        ]

        if null_columns:
            raise ValueError(
                "Valeurs nulles detectees dans : "
                + ", ".join(null_columns)
            )

        invalid_parts = dataframe[mix_columns].lt(0).any().any()

        if invalid_parts:
            raise ValueError(
                "Les parts de types et de gammes doivent etre positives."
            )

        observations = (
            dataframe[dataframe["is_observation"]]
            .groupby("hotel_code")
            .size()
        )

        invalid_observations = observations[
            observations != 1
        ]

        if not invalid_observations.empty:
            raise ValueError(
                "Chaque hotel doit avoir exactement une observation. "
                "Hotels invalides : "
                + ", ".join(invalid_observations.index.astype(str))
            )

        missing_observations = set(
            dataframe["hotel_code"].unique()
        ).difference(observations.index)

        if missing_observations:
            raise ValueError(
                "Observation initiale absente pour : "
                + ", ".join(sorted(missing_observations))
            )

    def prepare(self) -> PreparedDataset:
        dataframe = self.load()
        self.validate(dataframe)

        mix_columns = self.mix_columns(dataframe)
        features = dataframe[
            [*self.CONTEXT_FEATURES, *mix_columns]
        ].astype(float)

        solution_features = pd.get_dummies(
            dataframe["solution"],
            prefix="solution",
            dtype=float,
        )

        features = pd.concat(
            [features, solution_features],
            axis=1,
        )

        features = features.reindex(
            sorted(features.columns),
            axis=1,
        )

        return PreparedDataset(
            source=dataframe,
            features=features,
            feature_names=features.columns.tolist(),
            groups=dataframe["hotel_code"],
            observation_mask=dataframe["is_observation"],
        )


class XGBoostParameterOptimizer:
    def __init__(
        self,
        config: MLConfig,
        project_dir: str | Path,
    ):
        self.config = config
        self.project_dir = Path(project_dir).resolve()
        self.optuna_dir = (
            self.project_dir / config.optuna_dir
        )
        self.optuna_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def available_cpus(self) -> int:
        return max(
            1,
            (os.cpu_count() or 1)
            - self.config.reserved_cpus,
        )

    def fixed_params(self) -> dict[str, Any]:
        return {
            "objective": "reg:squarederror",
            "booster": "gbtree",
            "tree_method": "hist",
            "random_state": self.config.random_state,
            "n_jobs": self.available_cpus(),
            "verbosity": 0,
        }

    @staticmethod
    def suggested_params(
        trial: optuna.Trial,
    ) -> dict[str, Any]:
        return {
            "n_estimators": trial.suggest_int(
                "n_estimators",
                250,
                1800,
            ),
            "learning_rate": trial.suggest_float(
                "learning_rate",
                0.01,
                0.15,
                log=True,
            ),
            "max_depth": trial.suggest_int(
                "max_depth",
                2,
                7,
            ),
            "min_child_weight": trial.suggest_float(
                "min_child_weight",
                1.0,
                30.0,
                log=True,
            ),
            "subsample": trial.suggest_float(
                "subsample",
                0.60,
                1.00,
            ),
            "colsample_bytree": trial.suggest_float(
                "colsample_bytree",
                0.50,
                1.00,
            ),
            "gamma": trial.suggest_float(
                "gamma",
                0.0,
                8.0,
            ),
            "reg_alpha": trial.suggest_float(
                "reg_alpha",
                1e-8,
                20.0,
                log=True,
            ),
            "reg_lambda": trial.suggest_float(
                "reg_lambda",
                1e-3,
                100.0,
                log=True,
            ),
        }

    @staticmethod
    def sample_weights(groups: pd.Series) -> np.ndarray:
        group_counts = groups.value_counts()
        weights = groups.map(
            lambda group: 1.0 / group_counts[group]
        ).to_numpy(dtype=float)

        return weights / weights.mean()

    @staticmethod
    def normalized_score(
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> float:
        scale = max(
            float(np.mean(np.abs(y_true))),
            1e-9,
        )
        nmae = mean_absolute_error(
            y_true,
            y_pred,
        ) / scale
        nrmse = math.sqrt(
            mean_squared_error(
                y_true,
                y_pred,
            )
        ) / scale

        return 0.5 * nmae + 0.5 * nrmse

    def optimize(
        self,
        prepared: PreparedDataset,
        target: str,
    ) -> tuple[dict[str, Any], float, pd.DataFrame]:
        groups = prepared.groups
        distinct_groups = groups.nunique()
        n_splits = min(
            self.config.cv_splits,
            distinct_groups,
        )

        if n_splits < 2:
            raise ValueError(
                "Au moins deux hotels sont necessaires pour optimiser XGBoost."
            )

        splitter = GroupKFold(
            n_splits=n_splits,
        )
        target_values = prepared.source[target].to_numpy(
            dtype=float
        )

        storage_path = (
            self.optuna_dir / f"{target}.sqlite3"
        )
        storage_url = f"sqlite:///{storage_path}"

        sampler = optuna.samplers.TPESampler(
            seed=self.config.random_state,
        )
        pruner = optuna.pruners.MedianPruner(
            n_startup_trials=10,
            n_warmup_steps=1,
        )
        study = optuna.create_study(
            study_name=f"xgboost_{target}",
            storage=storage_url,
            load_if_exists=True,
            direction="minimize",
            sampler=sampler,
            pruner=pruner,
        )

        fixed_params = self.fixed_params()

        def objective(trial: optuna.Trial) -> float:
            params = {
                **fixed_params,
                **self.suggested_params(trial),
            }
            scores: list[float] = []

            for fold_index, (
                train_index,
                validation_index,
            ) in enumerate(
                splitter.split(
                    prepared.features,
                    target_values,
                    groups,
                ),
                start=1,
            ):
                validation_observations = (
                    prepared.observation_mask.iloc[
                        validation_index
                    ].to_numpy()
                )
                evaluation_index = validation_index[
                    validation_observations
                ]

                if len(evaluation_index) == 0:
                    raise ValueError(
                        "Aucune observation dans un fold de validation."
                    )

                model = XGBRegressor(**params)
                model.fit(
                    prepared.features.iloc[train_index],
                    target_values[train_index],
                    sample_weight=self.sample_weights(
                        groups.iloc[train_index]
                    ),
                    verbose=False,
                )

                prediction = np.maximum(
                    model.predict(
                        prepared.features.iloc[
                            evaluation_index
                        ]
                    ),
                    0.0,
                )
                score = self.normalized_score(
                    target_values[evaluation_index],
                    prediction,
                )
                scores.append(score)

                trial.report(
                    float(np.mean(scores)),
                    step=fold_index,
                )

                if trial.should_prune():
                    raise optuna.TrialPruned()

            return float(np.mean(scores))

        existing_complete_trials = len(
            [
                trial
                for trial in study.trials
                if trial.state
                == optuna.trial.TrialState.COMPLETE
            ]
        )
        remaining_trials = max(
            0,
            self.config.optuna_trials
            - existing_complete_trials,
        )

        if remaining_trials > 0:
            logging.info(
                "Optimisation %s : %s nouveaux essais Optuna",
                target,
                remaining_trials,
            )
            study.optimize(
                objective,
                n_trials=remaining_trials,
                timeout=self.config.optuna_timeout_seconds,
                n_jobs=1,
                show_progress_bar=False,
            )

        trials = study.trials_dataframe()
        trials.to_csv(
            self.optuna_dir / f"{target}_trials.csv",
            index=False,
        )

        return (
            {**fixed_params, **study.best_params},
            float(study.best_value),
            trials,
        )


class XGBoostModelTrainer:
    def __init__(
        self,
        config: MLConfig,
        project_dir: str | Path,
    ):
        self.config = config
        self.project_dir = Path(project_dir).resolve()
        self.models_dir = (
            self.project_dir / config.models_dir
        )
        self.models_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def sample_weights(groups: pd.Series) -> np.ndarray:
        group_counts = groups.value_counts()
        weights = groups.map(
            lambda group: 1.0 / group_counts[group]
        ).to_numpy(dtype=float)
        return weights / weights.mean()

    def train(
        self,
        prepared: PreparedDataset,
        target: MLTarget,
        params: dict[str, Any],
        best_score: float,
    ) -> TargetTrainingResult:
        model = XGBRegressor(**params)
        model.fit(
            prepared.features,
            prepared.source[target.name].to_numpy(
                dtype=float
            ),
            sample_weight=self.sample_weights(
                prepared.groups
            ),
            verbose=False,
        )

        model_path = (
            self.models_dir / f"{target.name}.json"
        )
        metadata_path = (
            self.models_dir
            / f"{target.name}_metadata.json"
        )
        model.save_model(model_path)

        metadata = {
            "target": target.name,
            "target_label": target.label,
            "feature_names": prepared.feature_names,
            "params": params,
            "best_cv_score": best_score,
            "training_rows": len(prepared.source),
            "training_hotels": int(
                prepared.groups.nunique()
            ),
            "solutions": sorted(
                prepared.source["solution"]
                .astype(str)
                .unique()
                .tolist()
            ),
        }
        metadata_path.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return TargetTrainingResult(
            target=target.name,
            best_params=params,
            best_score=best_score,
            model_path=str(model_path),
            metadata_path=str(metadata_path),
        )


class LeaveOneHotelOutEvaluator:
    def __init__(
        self,
        config: MLConfig,
        project_dir: str | Path,
    ):
        self.config = config
        self.project_dir = Path(project_dir).resolve()
        self.reports_dir = (
            self.project_dir / config.reports_dir
        )
        self.reports_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def sample_weights(groups: pd.Series) -> np.ndarray:
        group_counts = groups.value_counts()
        weights = groups.map(
            lambda group: 1.0 / group_counts[group]
        ).to_numpy(dtype=float)
        return weights / weights.mean()

    @staticmethod
    def metrics(
        predictions: pd.DataFrame,
        target: MLTarget,
    ) -> dict[str, Any]:
        true_column = f"{target.name}_reel"
        predicted_column = f"{target.name}_predit"
        y_true = predictions[true_column].to_numpy(
            dtype=float
        )
        y_pred = predictions[predicted_column].to_numpy(
            dtype=float
        )
        error = y_pred - y_true
        non_zero = np.abs(y_true) > 1e-9

        return {
            "target": target.name,
            "target_label": target.label,
            "nombre_hotels": len(predictions),
            "mae": mean_absolute_error(y_true, y_pred),
            "rmse": math.sqrt(
                mean_squared_error(y_true, y_pred)
            ),
            "mape": (
                float(
                    np.mean(
                        np.abs(error[non_zero] / y_true[non_zero])
                    )
                    * 100.0
                )
                if non_zero.any()
                else np.nan
            ),
            "biais": float(np.mean(error)),
        }

    def evaluate(
        self,
        prepared: PreparedDataset,
        params_by_target: dict[str, dict[str, Any]],
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        observations = prepared.source[
            prepared.observation_mask
        ].copy()
        hotel_codes = sorted(
            observations["hotel_code"].astype(str).unique()
        )
        rows: list[dict[str, Any]] = []

        for index, hotel_code in enumerate(
            hotel_codes,
            start=1,
        ):
            logging.info(
                "Evaluation ML LOO %s/%s | hotel=%s",
                index,
                len(hotel_codes),
                hotel_code,
            )
            train_mask = (
                prepared.groups.astype(str)
                != hotel_code
            )
            test_mask = (
                prepared.observation_mask
                & (
                    prepared.groups.astype(str)
                    == hotel_code
                )
            )

            if test_mask.sum() != 1:
                raise ValueError(
                    f"Observation unique introuvable pour {hotel_code}"
                )

            source_row = prepared.source.loc[
                test_mask
            ].iloc[0]
            result_row: dict[str, Any] = {
                "hotel_code": hotel_code,
                "solution": source_row["solution"],
                "solution_vue_en_apprentissage": bool(
                    (
                        prepared.source.loc[
                            train_mask,
                            "solution",
                        ]
                        == source_row["solution"]
                    ).any()
                ),
            }

            for target in self.config.targets:
                model = XGBRegressor(
                    **params_by_target[target.name]
                )
                model.fit(
                    prepared.features.loc[train_mask],
                    prepared.source.loc[
                        train_mask,
                        target.name,
                    ].to_numpy(dtype=float),
                    sample_weight=self.sample_weights(
                        prepared.groups.loc[train_mask]
                    ),
                    verbose=False,
                )
                prediction = max(
                    float(
                        model.predict(
                            prepared.features.loc[test_mask]
                        )[0]
                    ),
                    0.0,
                )
                actual = float(source_row[target.name])
                result_row[f"{target.name}_reel"] = actual
                result_row[f"{target.name}_predit"] = prediction
                result_row[f"{target.name}_erreur"] = (
                    prediction - actual
                )
                result_row[
                    f"{target.name}_erreur_absolue"
                ] = abs(prediction - actual)

            rows.append(result_row)

        predictions = pd.DataFrame(rows)
        metrics = pd.DataFrame(
            [
                self.metrics(predictions, target)
                for target in self.config.targets
            ]
        )

        report_path = (
            self.reports_dir
            / "leave_one_hotel_out.xlsx"
        )
        with pd.ExcelWriter(
            report_path,
            engine="openpyxl",
        ) as writer:
            predictions.to_excel(
                writer,
                sheet_name="predictions",
                index=False,
            )
            metrics.to_excel(
                writer,
                sheet_name="metrics",
                index=False,
            )

        predictions.to_parquet(
            self.reports_dir
            / "leave_one_hotel_out_predictions.parquet",
            index=False,
        )
        metrics.to_csv(
            self.reports_dir
            / "leave_one_hotel_out_metrics.csv",
            index=False,
        )

        return predictions, metrics


class FeatureImportanceReporter:
    def __init__(
        self,
        config: MLConfig,
        project_dir: str | Path,
    ):
        self.config = config
        self.project_dir = Path(project_dir).resolve()
        self.reports_dir = (
            self.project_dir / config.reports_dir
        )
        self.reports_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def build(
        self,
        training_results: list[TargetTrainingResult],
        feature_names: list[str],
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []

        for result in training_results:
            model = XGBRegressor()
            model.load_model(result.model_path)
            booster = model.get_booster()
            gains = booster.get_score(
                importance_type="gain"
            )

            for feature_index, feature_name in enumerate(
                feature_names
            ):
                rows.append(
                    {
                        "target": result.target,
                        "feature": feature_name,
                        "gain": float(
                            gains.get(
                                feature_name,
                                gains.get(
                                    f"f{feature_index}",
                                    0.0,
                                ),
                            )
                        ),
                    }
                )

        dataframe = pd.DataFrame(rows)
        dataframe["rang"] = (
            dataframe.groupby("target")["gain"]
            .rank(
                method="dense",
                ascending=False,
            )
            .astype(int)
        )
        dataframe = dataframe.sort_values(
            ["target", "rang", "feature"]
        )
        dataframe.to_excel(
            self.reports_dir
            / "feature_importance.xlsx",
            index=False,
        )
        return dataframe


class V2ComparisonReporter:
    TARGET_MAPPING = {
        "montant_ventes_par_mois": (
            "montant_ventes_erreur_absolue",
            "montant_ventes_erreur",
            "montant_ventes_erreur_relative",
        ),
        "montant_marge_par_mois": (
            "montant_marge_erreur_absolue",
            "montant_marge_erreur",
            "montant_marge_erreur_relative",
        ),
        "montant_marge_selon_coef_par_mois": (
            "montant_marge_selon_coef_erreur_absolue",
            "montant_marge_selon_coef_erreur",
            "montant_marge_selon_coef_erreur_relative",
        ),
    }

    def __init__(
        self,
        cp: ConnectionPipeline,
        config: MLConfig,
        project_dir: str | Path,
    ):
        self.cp = cp
        self.config = config
        self.project_dir = Path(project_dir).resolve()
        self.reports_dir = (
            self.project_dir / config.reports_dir
        )
        self.reports_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def build(
        self,
        ml_metrics: pd.DataFrame,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []

        for metric in ml_metrics.itertuples(index=False):
            rows.append(
                {
                    "modele": "XGBoost",
                    "methode": "ML",
                    "target": metric.target,
                    "nombre_hotels": metric.nombre_hotels,
                    "mae": metric.mae,
                    "rmse": metric.rmse,
                    "mape": metric.mape,
                    "biais": metric.biais,
                }
            )

        if not self.cp.table_exists("t_loo_results"):
            comparison = pd.DataFrame(rows)
            comparison.to_excel(
                self.reports_dir / "ml_vs_sim_v2.xlsx",
                index=False,
            )
            return comparison

        v2_results = self.cp.table_view(
            "t_loo_results"
        ).df()

        if v2_results.empty:
            comparison = pd.DataFrame(rows)
            comparison.to_excel(
                self.reports_dir / "ml_vs_sim_v2.xlsx",
                index=False,
            )
            return comparison

        for method, method_df in v2_results.groupby(
            "methode",
            sort=True,
        ):
            for target in self.config.targets:
                absolute_column, error_column, relative_column = (
                    self.TARGET_MAPPING[target.name]
                )
                rows.append(
                    {
                        "modele": "Simulateur V2",
                        "methode": str(method),
                        "target": target.name,
                        "nombre_hotels": len(method_df),
                        "mae": float(
                            method_df[absolute_column].mean()
                        ),
                        "rmse": float(
                            math.sqrt(
                                np.mean(
                                    np.square(
                                        method_df[error_column]
                                    )
                                )
                            )
                        ),
                        "mape": float(
                            method_df[relative_column].mean()
                            * 100.0
                        ),
                        "biais": float(
                            method_df[error_column].mean()
                        ),
                    }
                )

        comparison = pd.DataFrame(rows).sort_values(
            ["target", "mae", "modele", "methode"]
        )
        comparison.to_excel(
            self.reports_dir / "ml_vs_sim_v2.xlsx",
            index=False,
        )
        return comparison


class XGBoostWorkflow:
    def __init__(
        self,
        cp: ConnectionPipeline,
        config: MLConfig | None = None,
        project_dir: str | Path | None = None,
    ):
        self.cp = cp
        self.config = config or MLConfig()
        self.project_dir = (
            Path(project_dir).resolve()
            if project_dir is not None
            else cp.project_dir
        )
        self.dataset_builder = MLDatasetBuilder(
            cp,
            self.config,
        )
        self.optimizer = XGBoostParameterOptimizer(
            self.config,
            self.project_dir,
        )
        self.trainer = XGBoostModelTrainer(
            self.config,
            self.project_dir,
        )
        self.evaluator = LeaveOneHotelOutEvaluator(
            self.config,
            self.project_dir,
        )
        self.importance_reporter = FeatureImportanceReporter(
            self.config,
            self.project_dir,
        )
        self.comparison_reporter = V2ComparisonReporter(
            cp,
            self.config,
            self.project_dir,
        )

    def run(self) -> dict[str, Any]:
        prepared = self.dataset_builder.prepare()
        training_results: list[TargetTrainingResult] = []
        params_by_target: dict[str, dict[str, Any]] = {}

        logging.info(
            "Dataset ML : %s lignes | %s hotels | %s variables",
            len(prepared.source),
            prepared.groups.nunique(),
            len(prepared.feature_names),
        )

        for target in self.config.targets:
            logging.info(
                "Optimisation XGBoost : %s",
                target.name,
            )
            params, score, _ = self.optimizer.optimize(
                prepared,
                target.name,
            )
            params_by_target[target.name] = params
            training_results.append(
                self.trainer.train(
                    prepared,
                    target,
                    params,
                    score,
                )
            )

        loo_predictions, loo_metrics = (
            self.evaluator.evaluate(
                prepared,
                params_by_target,
            )
        )
        feature_importance = (
            self.importance_reporter.build(
                training_results,
                prepared.feature_names,
            )
        )
        model_comparison = self.comparison_reporter.build(
            loo_metrics
        )

        summary = {
            "config": asdict(self.config),
            "training_rows": len(prepared.source),
            "training_hotels": int(
                prepared.groups.nunique()
            ),
            "feature_count": len(
                prepared.feature_names
            ),
            "models": [
                asdict(result)
                for result in training_results
            ],
        }
        summary_path = (
            self.project_dir
            / self.config.reports_dir
            / "training_summary.json"
        )
        summary_path.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "prepared_dataset": prepared,
            "training_results": training_results,
            "loo_predictions": loo_predictions,
            "loo_metrics": loo_metrics,
            "feature_importance": feature_importance,
            "model_comparison": model_comparison,
            "summary": summary,
        }


def run_xgboost_workflow(
    cp: ConnectionPipeline,
    optuna_trials: int = 80,
    cv_splits: int = 5,
) -> dict[str, Any]:
    config = MLConfig(
        optuna_trials=optuna_trials,
        cv_splits=cv_splits,
    )
    workflow = XGBoostWorkflow(
        cp=cp,
        config=config,
    )
    return workflow.run()
