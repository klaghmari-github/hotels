"""
ML expose dans l'UI : modeles de **taux de conversion** separes par solution.

Architecture (pas de melange simply / liberty / connected) :
  - model_simply, model_liberty, model_connected
  - chacun predit : taux_conversion = nombre_ventes / nombre_guests
  - CA / marge finaux =
        CA_sim_v2  × (conversion_ML / conversion_baseline_solution)
        marge_sim_v2 × meme ratio

Le simulateur sim_v2 fournit l'intensite / mix ; le ML ajuste le taux
de conversion clients propre au contexte (par solution).
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
    load_ml_dataset,
    metrics_frame,
    mix_columns,
)
from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths

logger = logging.getLogger(__name__)

SOLUTIONS = ("simply", "liberty", "connected")
CONVERSION_TARGET = "taux_conversion"
META_PRED_TARGETS = tuple(t for t, _ in TARGETS)


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


def _norm_sol(s: Any) -> str:
    return str(s or "").strip().lower().replace("_", " ")


class SuperModelService:
    """
    Trois modeles de conversion (simply / liberty / connected) + scale sim_v2.
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

    # ------------------------------------------------------------------ data
    def load_dataset(self) -> pd.DataFrame:
        """Liste simulations sim_v2 + taux_conversion."""
        df = load_ml_dataset(
            self.paths, self.factory, mode="sim_v2", prefer_rich=False
        )
        df = df.copy()
        df["solution"] = df["solution"].map(_norm_sol)
        # reconstruire conversion si absente (vues non rebuildees)
        if CONVERSION_TARGET not in df.columns:
            if (
                "nombre_ventes_par_mois" in df.columns
                and "nombre_guests_par_mois" in df.columns
            ):
                g = pd.to_numeric(df["nombre_guests_par_mois"], errors="coerce")
                v = pd.to_numeric(df["nombre_ventes_par_mois"], errors="coerce")
                df[CONVERSION_TARGET] = (v / g.replace(0, np.nan)).fillna(0.0)
            else:
                # fallback : proxy ventes/guests via CA (moins ideal)
                guests = (
                    pd.to_numeric(df.get("hotel_nb_chambres"), errors="coerce").fillna(0)
                    * pd.to_numeric(df.get("hotel_to_annuel"), errors="coerce").fillna(0)
                    * pd.to_numeric(
                        df.get("hotel_guests_per_chambre"), errors="coerce"
                    ).fillna(0)
                    * 30.5
                )
                ca = pd.to_numeric(
                    df.get("montant_ventes_par_mois"), errors="coerce"
                ).fillna(0)
                # proxy non comparable — forcer rebuild dataset
                df[CONVERSION_TARGET] = 0.0
                logger.warning(
                    "taux_conversion absent du dataset ML — "
                    "rebuild v_ml_training_dataset recommande"
                )
        df[CONVERSION_TARGET] = pd.to_numeric(
            df[CONVERSION_TARGET], errors="coerce"
        ).fillna(0.0)
        # bornes raisonnables
        df[CONVERSION_TARGET] = df[CONVERSION_TARGET].clip(lower=0.0, upper=1.0)
        return df

    def _feature_columns(self, df: pd.DataFrame) -> list[str]:
        """Features descriptives sans solution dummies (modeles separes)."""
        exclude = {
            "scenario_id",
            "hotel_code",
            "solution",
            "is_observation",
            "scenario_removed_natures",
            CONVERSION_TARGET,
            "nombre_ventes_par_mois",
            "nombre_guests_par_mois",
        } | {t for t, _ in TARGETS}
        ordered: list[str] = []
        for c in [*CONTEXT_FEATURES, *mix_columns(df)]:
            if c in df.columns and c not in exclude and c not in ordered:
                ordered.append(c)
        for c in sorted(df.columns):
            if c in exclude or c in ordered:
                continue
            if pd.api.types.is_numeric_dtype(df[c]):
                ordered.append(c)
        return ordered

    def _xy(
        self, df: pd.DataFrame, feature_names: list[str]
    ) -> tuple[pd.DataFrame, np.ndarray, pd.Series]:
        x = df.reindex(columns=feature_names).astype(float).fillna(0.0)
        y = df[CONVERSION_TARGET].to_numpy(dtype=float)
        groups = df["hotel_code"].astype(str)
        return x, y, groups

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
            "random_state": cfg.random_seed,
            "n_jobs": cfg.n_jobs,
            "verbosity": 0,
            "objective": "reg:squarederror",
            "tree_method": "hist",
        }

    def _fit_conversion(
        self,
        x_train: pd.DataFrame,
        y_train: np.ndarray,
        groups: pd.Series | None = None,
    ) -> XGBRegressor:
        model = XGBRegressor(**self._model_params())
        if groups is not None and groups.nunique() >= 3:
            gkf = GroupKFold(n_splits=min(3, int(groups.nunique())))
            tr_idx, va_idx = next(gkf.split(x_train, y_train, groups))
            model.fit(
                x_train.iloc[tr_idx],
                y_train[tr_idx],
                eval_set=[(x_train.iloc[va_idx], y_train[va_idx])],
                verbose=False,
            )
        else:
            model.fit(x_train, y_train, verbose=False)
        return model

    def _solution_dir(self, solution: str) -> Path:
        d = self.models_dir / _norm_sol(solution)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _load_sim_v2_loo_map(self) -> dict[str, dict[str, float]]:
        p2 = self.paths.out_sim_v2("eval_sim_v2_loo.xlsx")
        if not p2.exists():
            return {}
        try:
            df = pd.read_excel(p2, sheet_name="predictions")
        except Exception:  # noqa: BLE001
            return {}
        out: dict[str, dict[str, float]] = {}
        for _, r in df.iterrows():
            code = str(r.get("hotel_code") or "").strip()
            if not code:
                continue
            out[code] = {
                "montant_ventes_par_mois": float(
                    r.get("montant_ventes_par_mois_predit")
                    or r.get("ca_pred")
                    or 0
                ),
                "montant_marge_selon_coef_par_mois": float(
                    r.get("montant_marge_selon_coef_par_mois_predite")
                    or r.get("marge_pred")
                    or 0
                ),
                "montant_marge_par_mois": float(
                    r.get("montant_marge_par_mois_predite")
                    or r.get("montant_marge_par_mois_predit")
                    or 0
                ),
            }
        return out

    def _sim_v2_pred_for_observation(self, row: pd.Series) -> dict[str, float]:
        """Restitution sim_v2 live pour une ligne hotel / mix."""
        try:
            from src.sim_v2.service import SimV2Service

            svc = SimV2Service(self.paths, factory=self.factory)
            type_mix: dict[str, float] = {}
            gamme_mix: dict[str, float] = {}
            for c, v in row.items():
                cs = str(c)
                if cs.startswith("type_") and cs.endswith("_part_natures"):
                    key = (
                        cs[len("type_") : -len("_part_natures")]
                        .replace("_", " ")
                        .replace("f b", "F&B")
                    )
                    if "non" in key.lower():
                        key = "NON F&B"
                    elif "f" in key.lower() and "b" in key.lower():
                        key = "F&B"
                    type_mix[key] = float(v or 0)
                if cs.startswith("gamme_") and cs.endswith("_part_natures"):
                    key = cs[len("gamme_") : -len("_part_natures")].replace(
                        "_", " "
                    )
                    gamme_mix[key] = float(v or 0)
            nb = float(row.get("hotel_nb_chambres") or 100)
            to = float(row.get("hotel_to_annuel") or 0.7)
            guests = float(row.get("hotel_guests_per_chambre") or 1.7)
            m_lin = float(row.get("metres_lineaires") or 6)
            sol = _norm_sol(row.get("solution") or "simply")
            df = svc.predict(
                hotel_nb_chambres=nb,
                hotel_to_annuel=to,
                hotel_guests_per_chambre=guests,
                metres_lineaires=m_lin,
                type_mix=type_mix or {"F&B": 0.7, "NON F&B": 0.3},
                gamme_mix=gamme_mix or None,
            )
            if df is None or df.empty:
                return {t: 0.0 for t in META_PRED_TARGETS}
            if "solution" in df.columns:
                hit = df.loc[df["solution"].astype(str).str.lower() == sol]
                if hit.empty:
                    hit = df
            else:
                hit = df
            r = hit.iloc[0]
            return {
                "montant_ventes_par_mois": float(
                    r.get("montant_ventes_par_mois_predit")
                    or r.get("montant_ventes_par_mois")
                    or 0
                ),
                "montant_marge_selon_coef_par_mois": float(
                    r.get("montant_marge_selon_coef_par_mois_predite")
                    or r.get("montant_marge_selon_coef_par_mois")
                    or 0
                ),
                "montant_marge_par_mois": float(
                    r.get("montant_marge_par_mois_predite")
                    or r.get("montant_marge_par_mois")
                    or 0
                ),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("sim_v2 pred failed: %s", exc)
            return {t: 0.0 for t in META_PRED_TARGETS}

    @staticmethod
    def _scale_with_conversion(
        sim_v2: dict[str, float],
        conv_pred: float,
        conv_baseline: float,
    ) -> dict[str, float]:
        """CA_ml = CA_sim_v2 × (conv_ML / conv_baseline_solution)."""
        base = float(conv_baseline) if conv_baseline and conv_baseline > 1e-12 else 1e-12
        ratio = max(0.0, float(conv_pred)) / base
        out: dict[str, float] = {
            "taux_conversion_predit": float(conv_pred),
            "taux_conversion_baseline": float(conv_baseline),
            "conversion_scale": float(ratio),
        }
        for t in META_PRED_TARGETS:
            out[t] = max(0.0, float(sim_v2.get(t) or 0.0) * ratio)
        return out

    # ------------------------------------------------------------------ train
    def train_final(self, df: pd.DataFrame | None = None) -> list[dict[str, Any]]:
        """Entrainement de 3 modeles de conversion (un par solution)."""
        df = df if df is not None else self.load_dataset()
        logger.info(
            "ml conversion dataset: rows=%s hotels=%s",
            len(df),
            df["hotel_code"].nunique(),
        )
        feature_names = self._feature_columns(df)
        results: list[dict[str, Any]] = []

        for sol in SOLUTIONS:
            sub = df.loc[df["solution"] == sol].copy()
            if sub.empty:
                logger.warning("Pas de donnees pour model_%s — skip", sol)
                continue
            x, y, groups = self._xy(sub, feature_names)
            if len(sub) < 3 or float(np.nanstd(y)) < 1e-12:
                # fallback : conversion moyenne constante (predict = baseline)
                baseline = float(np.nanmean(y)) if len(y) else 0.05
                meta = {
                    "solution": sol,
                    "target": CONVERSION_TARGET,
                    "feature_names": feature_names,
                    "params": self._model_params(),
                    "training_rows": len(sub),
                    "training_hotels": int(sub["hotel_code"].nunique()),
                    "conversion_baseline": baseline,
                    "engine": "ml",
                    "model_kind": "conversion_mean_fallback",
                    "note": (
                        f"model_{sol}: trop peu de variance — "
                        "prediction = moyenne solution"
                    ),
                }
                sdir = self._solution_dir(sol)
                (sdir / "conversion_metadata.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                # pas de .json model — predict_row utilisera baseline
                results.append(meta)
                logger.info(
                    "model_%s fallback mean conv=%.5f (rows=%s)",
                    sol,
                    baseline,
                    len(sub),
                )
                continue

            model = self._fit_conversion(x, y, groups)
            baseline = float(np.nanmean(y))
            sdir = self._solution_dir(sol)
            model_path = sdir / "conversion.json"
            meta_path = sdir / "conversion_metadata.json"
            model.save_model(str(model_path))
            meta = {
                "solution": sol,
                "target": CONVERSION_TARGET,
                "feature_names": feature_names,
                "params": self._model_params(),
                "training_rows": len(sub),
                "training_hotels": int(sub["hotel_code"].nunique()),
                "conversion_baseline": baseline,
                "conversion_mean": baseline,
                "conversion_std": float(np.nanstd(y)),
                "engine": "ml",
                "model_kind": "conversion_xgb_by_solution",
                "note": (
                    f"model_{sol}: predit taux_conversion ; "
                    "CA = sim_v2 × (conv_ML / conv_baseline)"
                ),
            }
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            results.append(meta)
            logger.info(
                "model_%s sauve (%s rows, %s hotels, baseline=%.5f)",
                sol,
                len(sub),
                sub["hotel_code"].nunique(),
                baseline,
            )

        # index global pour compat (pointeur vers architecture)
        index = {
            "engine": "ml",
            "architecture": "conversion_by_solution + sim_v2_scale",
            "solutions": list(SOLUTIONS),
            "models": results,
        }
        (self.models_dir / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # marqueur pour detecter l'architecture (ancien super stack n'a pas ca)
        # aussi ecrire un metadata "montant_ventes" factice? non — predict_row
        # lit index / solution dirs
        return results

    def _predict_conversion(
        self,
        solution: str,
        feature_row: dict[str, float],
        *,
        model: XGBRegressor | None = None,
        feature_names: list[str] | None = None,
        baseline: float | None = None,
    ) -> tuple[float, float]:
        """Retourne (conv_pred, conv_baseline)."""
        sol = _norm_sol(solution)
        sdir = self._solution_dir(sol)
        meta_path = sdir / "conversion_metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {}
        names = feature_names or meta.get("feature_names") or list(
            CONTEXT_FEATURES
        )
        base = (
            float(baseline)
            if baseline is not None
            else float(meta.get("conversion_baseline") or 0.05)
        )
        model_path = sdir / "conversion.json"
        if model is None and model_path.exists():
            model = XGBRegressor()
            model.load_model(str(model_path))
        if model is None:
            return base, base
        # build_feature_row avec solution dummies inutiles si absents des names
        x = build_feature_row(names, feature_row, sol)
        pred = float(model.predict(x)[0])
        pred = max(0.0, min(1.0, pred))
        return pred, base

    # ------------------------------------------------------------------ LOO
    def leave_one_hotel_out(
        self,
        df: pd.DataFrame | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Eval par hotel :
          - entraine model_SOLUTION sans l'hotel (sauf mono-solution → biaise)
          - predit conversion
          - scale CA/marge sim_v2
        """
        df = df if df is not None else self.load_dataset()
        feature_names = self._feature_columns(df)
        observation = df["is_observation"].astype(bool)
        obs = df.loc[observation].copy()
        hotels = sorted(obs["hotel_code"].astype(str).unique())
        sim_loo = self._load_sim_v2_loo_map()

        # effectifs par solution (observations)
        sol_of = {
            str(r.hotel_code): _norm_sol(r.solution)
            for r in obs.itertuples(index=False)
        }
        sol_counts: dict[str, int] = {}
        for s in sol_of.values():
            sol_counts[s] = sol_counts.get(s, 0) + 1

        rows: list[dict[str, Any]] = []
        for index, hotel in enumerate(hotels, start=1):
            sol = sol_of.get(hotel, "simply")
            biased = sol_counts.get(sol, 0) <= 1
            logger.info(
                "ml conversion LOO %s/%s | hotel=%s sol=%s%s",
                index,
                len(hotels),
                hotel,
                sol,
                " | eval_biased" if biased else "",
            )
            test_mask = observation & (df["hotel_code"].astype(str) == hotel)
            if int(test_mask.sum()) != 1:
                raise ValueError(
                    f"Observation unique attendue pour {hotel}, "
                    f"trouve {int(test_mask.sum())}"
                )
            source = df.loc[test_mask].iloc[0]
            # train = meme solution uniquement
            train_sol = df["solution"] == sol
            if biased:
                train_mask = train_sol
            else:
                train_mask = train_sol & (df["hotel_code"].astype(str) != hotel)

            sub = df.loc[train_mask]
            if sub.empty:
                sub = df.loc[train_sol]

            x_tr, y_tr, g_tr = self._xy(sub, feature_names)
            if len(sub) >= 3 and float(np.nanstd(y_tr)) > 1e-12:
                model = self._fit_conversion(x_tr, y_tr, g_tr)
                baseline = float(np.nanmean(y_tr))
            else:
                model = None
                baseline = (
                    float(np.nanmean(y_tr))
                    if len(y_tr)
                    else float(source.get(CONVERSION_TARGET) or 0.05)
                )

            feat_row = {
                c: float(source[c])
                for c in feature_names
                if c in source.index and pd.notna(source[c])
            }
            x_te = build_feature_row(feature_names, feat_row, sol)
            if model is not None:
                conv_pred = max(0.0, min(1.0, float(model.predict(x_te)[0])))
            else:
                conv_pred = baseline

            if hotel in sim_loo:
                v2 = sim_loo[hotel]
            else:
                v2 = self._sim_v2_pred_for_observation(source)

            scaled = self._scale_with_conversion(v2, conv_pred, baseline)
            conv_reel = float(source.get(CONVERSION_TARGET) or 0.0)

            row: dict[str, Any] = {
                "hotel_code": hotel,
                "solution": sol,
                "eval_biased": bool(biased),
                "taux_conversion_reel": conv_reel,
                "taux_conversion_predit": conv_pred,
                "taux_conversion_baseline": baseline,
                "conversion_scale": scaled["conversion_scale"],
            }
            for t, _lab in TARGETS:
                actual = float(source.get(t) or 0.0)
                pred = float(scaled.get(t) or 0.0)
                row[f"{t}_reel"] = actual
                row[f"{t}_predit"] = pred
                row[f"{t}_erreur"] = pred - actual
                row[f"{t}_erreur_absolue"] = abs(pred - actual)
                # aussi pred sim_v2 brute pour diagnostic
                row[f"pred_sim_v2__{t}"] = float(v2.get(t) or 0.0)
            rows.append(row)

        predictions = pd.DataFrame(rows)
        return predictions, metrics_frame(predictions, TARGETS)

    def export_loo(
        self,
        predictions: pd.DataFrame | None = None,
        metrics: pd.DataFrame | None = None,
    ) -> Path:
        if predictions is None or metrics is None:
            predictions, metrics = self.leave_one_hotel_out()
        path = self.paths.out_ml("eval_ml_loo.xlsx")
        path.parent.mkdir(parents=True, exist_ok=True)
        resume = metrics.copy()
        resume.insert(0, "source", "ml")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            predictions.to_excel(writer, sheet_name="predictions", index=False)
            metrics.to_excel(writer, sheet_name="metrics", index=False)
            resume.to_excel(writer, sheet_name="resume", index=False)
        for alias_name in ("eval_super_loo.xlsx", "eval_catboost_loo.xlsx"):
            alias = self.paths.out_ml(alias_name)
            with pd.ExcelWriter(alias, engine="openpyxl") as writer:
                predictions.to_excel(
                    writer, sheet_name="predictions", index=False
                )
                metrics.to_excel(writer, sheet_name="metrics", index=False)
                resume.to_excel(writer, sheet_name="resume", index=False)
        logger.info("Export ml conversion-by-solution LOO : %s", path)
        return path

    def predict_row(
        self,
        feature_row: dict[str, float],
        solution: str,
        *,
        hotel_code: str | None = None,
        type_mix: dict[str, float] | None = None,
        gamme_mix: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Production :
          1) model_{solution} → taux_conversion
          2) sim_v2 → CA / marge
          3) scale CA par ratio conversion
        """
        sol = _norm_sol(solution)
        sdir = self._solution_dir(sol)
        meta_path = sdir / "conversion_metadata.json"
        index_path = self.models_dir / "index.json"
        if not meta_path.exists() and not index_path.exists():
            # fallback ancien super stack?
            legacy = self.models_dir / "montant_ventes_par_mois_metadata.json"
            if legacy.exists():
                raise FileNotFoundError(
                    "Ancien modele ml (stacking) detecte. "
                    "Relancer : python run.py ml --rebuild "
                    "(architecture conversion par solution)"
                )
            raise FileNotFoundError(
                "Modele ml absent. Lancer : python run.py ml --rebuild"
            )

        conv_pred, conv_base = self._predict_conversion(sol, feature_row)

        series = pd.Series(
            {
                **feature_row,
                "solution": sol,
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
        v2 = self._sim_v2_pred_for_observation(series)
        if hotel_code:
            loo = self._load_sim_v2_loo_map().get(str(hotel_code))
            if not any(v2.values()) and loo:
                v2 = loo

        scaled = self._scale_with_conversion(v2, conv_pred, conv_base)
        out: dict[str, Any] = {
            "solution": sol,
            "engine": "ml",
            "model": f"model_{sol}",
            "taux_conversion_predit": scaled["taux_conversion_predit"],
            "taux_conversion_baseline": scaled["taux_conversion_baseline"],
            "conversion_scale": scaled["conversion_scale"],
            "base_predictions": {
                "sim_v2": {t: float(v2.get(t) or 0) for t in META_PRED_TARGETS},
                "conversion_ml": {
                    "taux_conversion": conv_pred,
                    "baseline": conv_base,
                },
            },
        }
        for t in META_PRED_TARGETS:
            out[t] = float(scaled.get(t) or 0.0)
        return out

    def run_full(self) -> dict[str, Any]:
        # s'assurer que la vue dataset a les colonnes conversion
        try:
            cp = self.factory.open(read_only=False)
            try:
                cp.p_table_view("v_ml_training_dataset")
            finally:
                cp.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh v_ml_training_dataset: %s", exc)

        df = self.load_dataset()
        self.train_final(df)
        predictions, metrics = self.leave_one_hotel_out(df)
        path = self.export_loo(predictions, metrics)
        return {
            "predictions": predictions,
            "metrics": metrics,
            "excel": path,
            "engine": "ml",
            "architecture": "conversion_by_solution + sim_v2_scale",
            "source": df.attrs.get("ml_source"),
        }
