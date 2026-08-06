"""
Super-modele (stacking) expose comme « ml » dans l'UI.

Couches intermediaires (non affichees) :
  1) XGBoost base : entraine sur la liste de simulations sim_v2
     (v_ml_training_dataset / pivot — features TO, guests, chambres, mix type/gamme)
  2) sim_v2 restitution : prediction simulateur pour le meme vecteur

Meta-modele XGB :
  features descriptives (contexte + mix + solution)
  + pred_sim_v2__*
  + pred_xgboost__*
  → CA / marge / marge selon coef

LOO hotel pour l'eval admin ; production via predict_row.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from xgboost import XGBRegressor

from src.ml.common import (
    CONTEXT_FEATURES,
    TARGETS,
    build_feature_row,
    feature_matrix,
    load_ml_dataset,
    metrics_frame,
    mix_columns,
)
from src.ml.xgboost_model import XGBoostService
from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths

logger = logging.getLogger(__name__)

# Couches de base uniquement (pas affichees dans l'UI)
BASE_ENGINES = ("sim_v2", "xgboost")
# Cibles meta = les 3 sorties metier
META_TARGETS = TARGETS
META_PRED_TARGETS = tuple(t for t, _ in META_TARGETS)


@dataclass(frozen=True)
class SuperModelConfig:
    n_estimators: int = 400
    learning_rate: float = 0.05
    max_depth: int = 4
    min_child_weight: float = 2.0
    subsample: float = 0.9
    colsample_bytree: float = 0.9
    reg_lambda: float = 2.0
    early_stopping_rounds: int = 40
    random_seed: int = 42
    n_jobs: int = -1


class SuperModelService:
    """
    Stacking final = ml affiche.
    XGBoost base entraine sur simulations sim_v2 (skinny).
    """

    def __init__(
        self,
        paths: Paths | None = None,
        config: SuperModelConfig | None = None,
        factory: PipelineFactory | None = None,
    ):
        self.paths = (paths or Paths()).ensure()
        self.config = config or SuperModelConfig()
        self.factory = factory or PipelineFactory(self.paths)
        self.models_dir = self.paths.models_super
        self.models_dir.mkdir(parents=True, exist_ok=True)
        # couche XGB : uniquement sim_v2 pre-agreg (liste simulations)
        self.xgboost = XGBoostService(
            self.paths, factory=self.factory, variant="ml1"
        )

    def load_dataset(self) -> pd.DataFrame:
        """Liste simulations sim_v2 (pas le rich dataset)."""
        return load_ml_dataset(
            self.paths, self.factory, mode="sim_v2", prefer_rich=False
        )

    def _meta_model_params(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "n_estimators": cfg.n_estimators,
            "learning_rate": cfg.learning_rate,
            "max_depth": cfg.max_depth,
            "min_child_weight": cfg.min_child_weight,
            "subsample": cfg.subsample,
            "colsample_bytree": cfg.colsample_bytree,
            "reg_lambda": cfg.reg_lambda,
            "random_state": cfg.random_seed,
            "n_jobs": cfg.n_jobs,
            "verbosity": 0,
            "objective": "reg:squarederror",
            "tree_method": "hist",
        }

    def _fit_meta(
        self,
        x_train: pd.DataFrame,
        y_train: np.ndarray,
        groups: pd.Series | None = None,
    ) -> XGBRegressor:
        model = XGBRegressor(**self._meta_model_params())
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

    def _load_sim_v2_loo_map(self) -> dict[str, dict[str, float]]:
        """hotel_code -> {target: pred} depuis LOO sim_v2."""
        out: dict[str, dict[str, float]] = {}
        p2 = self.paths.out_sim_v2("eval_sim_v2_loo.xlsx")
        if not p2.exists():
            return out
        df = pd.read_excel(p2, sheet_name="predictions")
        for _, r in df.iterrows():
            code = str(r.get("hotel_code") or "")
            if not code:
                continue
            out[code] = {
                "montant_ventes_par_mois": float(
                    r.get("montant_ventes_par_mois_predit") or 0
                ),
                "montant_marge_par_mois": float(
                    r.get("montant_marge_par_mois_predite")
                    or r.get("montant_marge_par_mois_predit")
                    or 0
                ),
                "montant_marge_selon_coef_par_mois": float(
                    r.get("montant_marge_selon_coef_par_mois_predite")
                    or r.get("montant_marge_selon_coef_par_mois_predit")
                    or 0
                ),
            }
        return out

    def _predict_xgboost_oof(
        self,
        *,
        train_df: pd.DataFrame,
        x_train: pd.DataFrame,
        x_test: pd.DataFrame,
        train_groups: pd.Series,
    ) -> dict[str, float]:
        """Entraine XGB hors hotel test, predit la ligne observation."""
        preds: dict[str, float] = {}
        for target, _ in META_TARGETS:
            if target not in train_df.columns:
                preds[target] = 0.0
                continue
            y_train = train_df[target].to_numpy(dtype=float)
            model = self.xgboost._fit_one(x_train, y_train, train_groups)
            preds[target] = max(float(model.predict(x_test)[0]), 0.0)
        return preds

    def _sim_v2_pred_for_observation(self, row: pd.Series) -> dict[str, float]:
        """Restitution sim_v2 pour une ligne (params hotel + mix)."""
        from src.sim_v2.service import SimV2Service

        try:
            svc = SimV2Service(self.paths, self.factory)
            type_mix: dict[str, float] = {}
            gamme_mix: dict[str, float] = {}
            for c in mix_columns(pd.DataFrame([row])):
                val = float(row.get(c) or 0)
                if c.startswith("type_") and c.endswith("_part_natures"):
                    label = c[len("type_") : -len("_part_natures")].replace("_", " ")
                    type_mix[label] = val
                elif c.startswith("gamme_") and c.endswith("_part_natures"):
                    label = c[len("gamme_") : -len("_part_natures")].replace("_", " ")
                    gamme_mix[label] = val
            if not type_mix:
                type_mix = {"F&B": 0.7, "NON F&B": 0.3}
            if not gamme_mix:
                gamme_mix = {
                    "sans alcool": 0.35,
                    "food salee": 0.25,
                    "food sucree": 0.15,
                    "accessoires": 0.15,
                    "sos": 0.10,
                }
            # renormalise gamme a 1 (format restitution)
            s = sum(gamme_mix.values()) or 1.0
            gamme_mix = {k: v / s for k, v in gamme_mix.items()}
            st = sum(type_mix.values()) or 1.0
            type_mix = {k: v / st for k, v in type_mix.items()}

            df = svc.predict(
                hotel_nb_chambres=float(row.get("hotel_nb_chambres") or 100),
                hotel_to_annuel=float(row.get("hotel_to_annuel") or 0.7),
                hotel_guests_per_chambre=float(
                    row.get("hotel_guests_per_chambre") or 1.7
                ),
                metres_lineaires=float(row.get("metres_lineaires") or 6),
                type_mix=type_mix,
                gamme_mix=gamme_mix,
            )
            sol = str(row.get("solution") or "").lower()
            if "solution" in df.columns:
                hit = df.loc[df["solution"].astype(str).str.lower() == sol]
                if hit.empty:
                    hit = df
            else:
                hit = df
            r = hit.iloc[0]
            return {
                "montant_ventes_par_mois": float(
                    r.get("montant_ventes_par_mois_predit") or 0
                ),
                "montant_marge_par_mois": float(
                    r.get("montant_marge_par_mois_predite")
                    or r.get("montant_marge_par_mois_predit")
                    or 0
                ),
                "montant_marge_selon_coef_par_mois": float(
                    r.get("montant_marge_selon_coef_par_mois_predite")
                    or r.get("montant_marge_selon_coef_par_mois_predit")
                    or 0
                ),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("sim_v2 pred super: %s", exc)
            return {t: 0.0 for t in META_PRED_TARGETS}

    @staticmethod
    def _meta_feature_names(base_feature_names: list[str]) -> list[str]:
        names = list(base_feature_names)
        for eng in BASE_ENGINES:
            for target in META_PRED_TARGETS:
                names.append(f"pred_{eng}__{target}")
        return names

    def _build_meta_row(
        self,
        base_feat: pd.Series,
        base_preds: dict[str, dict[str, float]],
        feature_names: list[str],
    ) -> dict[str, float]:
        row = {n: 0.0 for n in feature_names}
        for n in base_feat.index:
            if n in row:
                row[n] = float(base_feat[n])
        for eng in BASE_ENGINES:
            preds = base_preds.get(eng) or {}
            for target in META_PRED_TARGETS:
                key = f"pred_{eng}__{target}"
                if key in row:
                    row[key] = float(preds.get(target) or 0.0)
        return row

    def leave_one_hotel_out(
        self,
        df: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        LOO stacking hotel :
          1) XGB base sans l'hotel
          2) pred sim_v2 (LOO excel ou restitution)
          3) meta-XGB sur hotels restants
        """
        df = df if df is not None else self.load_dataset()
        features, base_names = feature_matrix(df)
        meta_names = self._meta_feature_names(base_names)
        groups = df["hotel_code"].astype(str)
        observation = df["is_observation"]
        hotels = sorted(df.loc[observation, "hotel_code"].astype(str).unique())

        oof_base: dict[str, dict[str, dict[str, float]]] = {}
        oof_desc: dict[str, pd.Series] = {}
        oof_actual: dict[str, dict[str, float]] = {}
        oof_solution: dict[str, str] = {}
        sim_loo = self._load_sim_v2_loo_map()

        for index, hotel in enumerate(hotels, start=1):
            logger.info(
                "ml super LOO base %s/%s | hotel=%s", index, len(hotels), hotel
            )
            train_mask = groups != hotel
            test_mask = observation & (groups == hotel)
            if int(test_mask.sum()) != 1:
                raise ValueError(
                    f"Observation unique attendue pour {hotel}, "
                    f"trouve {int(test_mask.sum())}"
                )
            source = df.loc[test_mask].iloc[0]
            oof_solution[hotel] = str(source["solution"])
            oof_actual[hotel] = {
                t: float(source[t]) for t, _ in META_TARGETS if t in source
            }
            oof_desc[hotel] = features.loc[test_mask].iloc[0]

            x_train = features.loc[train_mask]
            x_test = features.loc[test_mask]
            train_groups = groups.loc[train_mask]
            train_df = df.loc[train_mask]

            xgb_preds = self._predict_xgboost_oof(
                train_df=train_df,
                x_train=x_train,
                x_test=x_test,
                train_groups=train_groups,
            )
            if hotel in sim_loo:
                v2 = sim_loo[hotel]
            else:
                v2 = self._sim_v2_pred_for_observation(source)

            oof_base[hotel] = {
                "xgboost": xgb_preds,
                "sim_v2": v2,
            }

        meta_rows = []
        for hotel in hotels:
            meta_rows.append(
                self._build_meta_row(
                    oof_desc[hotel], oof_base[hotel], meta_names
                )
            )
        meta_X = pd.DataFrame(meta_rows, index=hotels)[meta_names].astype(float)

        rows: list[dict[str, Any]] = []
        for index, hotel in enumerate(hotels, start=1):
            logger.info(
                "ml super LOO meta %s/%s | hotel=%s", index, len(hotels), hotel
            )
            train_hotels = [h for h in hotels if h != hotel]
            x_tr = meta_X.loc[train_hotels]
            x_te = meta_X.loc[[hotel]]
            g_tr = pd.Series(train_hotels, index=train_hotels)

            row: dict[str, Any] = {
                "hotel_code": hotel,
                "solution": oof_solution[hotel],
            }
            for eng in BASE_ENGINES:
                for target in META_PRED_TARGETS:
                    row[f"pred_{eng}__{target}"] = float(
                        (oof_base[hotel].get(eng) or {}).get(target) or 0
                    )

            for target, _label in META_TARGETS:
                if target not in oof_actual[hotel]:
                    continue
                y_tr = np.array(
                    [oof_actual[h].get(target, 0.0) for h in train_hotels],
                    dtype=float,
                )
                model = self._fit_meta(x_tr, y_tr, g_tr)
                pred = float(model.predict(x_te)[0])
                actual = float(oof_actual[hotel][target])
                row[f"{target}_reel"] = actual
                row[f"{target}_predit"] = pred
                row[f"{target}_erreur"] = pred - actual
                row[f"{target}_erreur_absolue"] = abs(pred - actual)

            rows.append(row)

        predictions = pd.DataFrame(rows)
        return predictions, metrics_frame(predictions, META_TARGETS)

    def train_final(self, df: pd.DataFrame | None = None) -> list[dict[str, Any]]:
        """
        Production :
          1) XGB base sur toutes les simulations sim_v2
          2) meta-features = descriptives + pred sim_v2 + pred xgb
          3) meta-XGB sur observations
        """
        df = df if df is not None else self.load_dataset()
        logger.info(
            "ml super dataset: source=%s rows=%s hotels=%s",
            df.attrs.get("ml_source"),
            len(df),
            df["hotel_code"].nunique(),
        )
        self.xgboost.train_final(df)

        obs = df.loc[df["is_observation"]].copy()
        if obs.empty:
            raise ValueError("Aucune observation pour entrainer le super-modele.")

        features, base_names = feature_matrix(obs)
        meta_names = self._meta_feature_names(base_names)
        sim_loo = self._load_sim_v2_loo_map()

        meta_rows = []
        for idx, source in obs.iterrows():
            hotel = str(source["hotel_code"])
            sol = str(source["solution"])
            base_feat = features.loc[idx]
            feat_row = {
                c: float(source[c])
                for c in [*CONTEXT_FEATURES, *mix_columns(obs)]
                if c in source.index
            }
            xg = self.xgboost.predict_row(feat_row, sol)
            v2 = sim_loo.get(hotel) or self._sim_v2_pred_for_observation(source)
            base_preds = {
                "xgboost": {t: float(xg.get(t) or 0) for t in META_PRED_TARGETS},
                "sim_v2": {
                    t: float((v2 or {}).get(t) or 0) for t in META_PRED_TARGETS
                },
            }
            meta_rows.append(
                self._build_meta_row(base_feat, base_preds, meta_names)
            )

        meta_X = pd.DataFrame(meta_rows).astype(float)[meta_names]
        results = []
        for target, label in META_TARGETS:
            if target not in obs.columns:
                continue
            y = obs[target].to_numpy(dtype=float)
            model = self._fit_meta(meta_X, y)
            model_path = self.models_dir / f"{target}.json"
            meta_path = self.models_dir / f"{target}_metadata.json"
            model.save_model(str(model_path))
            meta = {
                "target": target,
                "target_label": label,
                "feature_names": meta_names,
                "base_engines": list(BASE_ENGINES),
                "params": self._meta_model_params(),
                "training_rows": len(obs),
                "xgb_training_rows": len(df),
                "dataset_source": df.attrs.get("ml_source"),
                "engine": "ml",
                "note": "super stacking = sim_v2 + xgboost(sim_v2 simulations)",
            }
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results.append(meta)
            logger.info("ml (super) sauve : %s", model_path.name)
        return results

    def export_loo(
        self,
        predictions: pd.DataFrame | None = None,
        metrics: pd.DataFrame | None = None,
    ) -> Path:
        if predictions is None or metrics is None:
            predictions, metrics = self.leave_one_hotel_out()
        # eval_ml_loo = ce que l'UI admin /api/eval/ml lit
        path = self.paths.out_ml("eval_ml_loo.xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        resume = metrics.copy()
        resume.insert(0, "source", "ml")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            predictions.to_excel(writer, sheet_name="predictions", index=False)
            metrics.to_excel(writer, sheet_name="metrics", index=False)
            resume.to_excel(writer, sheet_name="resume", index=False)
        # alias historique
        alias = self.paths.out_ml("eval_super_loo.xlsx")
        with pd.ExcelWriter(alias, engine="openpyxl") as writer:
            predictions.to_excel(writer, sheet_name="predictions", index=False)
            metrics.to_excel(writer, sheet_name="metrics", index=False)
            resume.to_excel(writer, sheet_name="resume", index=False)
        # compat ancien catboost path pour clients qui lisent encore ce fichier
        legacy = self.paths.out_ml("eval_catboost_loo.xlsx")
        with pd.ExcelWriter(legacy, engine="openpyxl") as writer:
            predictions.to_excel(writer, sheet_name="predictions", index=False)
            metrics.to_excel(writer, sheet_name="metrics", index=False)
            resume.to_excel(writer, sheet_name="resume", index=False)
        logger.info("Export ml (super) LOO : %s", path)
        return path

    def predict_row(
        self,
        feature_row: dict[str, float],
        solution: str,
        *,
        hotel_code: str | None = None,
        type_mix: dict[str, float] | None = None,
        gamme_mix: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Prediction production = super-modele (affiche comme ml)."""
        targets = [t for t, _ in META_TARGETS]
        meta_path = self.models_dir / f"{targets[0]}_metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                "Modele ml (super) absent. Lancer : python run.py ml --rebuild"
            )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        feature_names: list[str] = meta["feature_names"]

        xg = self.xgboost.predict_row(feature_row, solution)

        series = pd.Series(
            {
                **feature_row,
                "solution": solution,
                **{
                    f"type_{k.replace(' ', '_').replace('&', '_')}_part_natures": v
                    for k, v in (type_mix or {}).items()
                },
                **{
                    f"gamme_{k.replace(' ', '_')}_part_natures": v
                    for k, v in (gamme_mix or {}).items()
                },
            }
        )
        # normalise cles type F&B
        v2 = self._sim_v2_pred_for_observation(series)
        if hotel_code:
            loo = self._load_sim_v2_loo_map().get(hotel_code)
            # live restitution preferred for what-if ; keep loo only if live fails
            if not any(v2.values()) and loo:
                v2 = loo

        base_preds = {
            "xgboost": {t: float(xg.get(t) or 0) for t in META_PRED_TARGETS},
            "sim_v2": {t: float(v2.get(t) or 0) for t in META_PRED_TARGETS},
        }

        base_only = [n for n in feature_names if not n.startswith("pred_")]
        base_vec = build_feature_row(base_only, feature_row, solution).iloc[0]
        meta_row = self._build_meta_row(base_vec, base_preds, feature_names)
        x = pd.DataFrame([meta_row])[feature_names].astype(float)

        out: dict[str, Any] = {
            "solution": solution,
            "engine": "ml",
            "base_predictions": base_preds,
        }
        for target in targets:
            model_path = self.models_dir / f"{target}.json"
            if not model_path.exists():
                continue
            model = XGBRegressor()
            model.load_model(str(model_path))
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
            "engine": "ml",
            "source": df.attrs.get("ml_source"),
        }
