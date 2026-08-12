"""
Moteur ML exposé dans l'UI (eval admin + estimations utilisateur).

Chaîne en trois étapes (par solution : simply / liberty / connected) :

  1) ml_tc
       XGBoost → taux de conversion réel
       (nombre_ventes / nombre_guests, recalculé obs + sim)
       Features = leviers + mix + hd_ + px_ + wx_ + hol_ + br_
                 + sim_v2_brut (CA / marges issus de la restitution sim_v2 pure)

  2) ml_tc_sim_v2  (intermédiaire, pas un modèle)
       CA_sim_v2 appliqué avec le TC prédit par ml_tc :
         ml_tc_sim_v2 = sim_v2_brut × (tc_ml_tc / tc_baseline_solution)
       C'est le « CA qu'aurait donné sim_v2 si on forçait le TC de ml_tc ».

  3) ml_ca
       XGBoost → CA final (montant_ventes_par_mois)
       Features = variables descriptives de ml_tc
                 + ml_tc_sim_v2 (sortie intermédiaire)
       Décision reportée par le moteur « ml » dans les évaluations et
       les estimations utilisateur.

Pourquoi cette architecture ?
  sim_v2 seul (règles métier) approche déjà bien le CA réel.
  Un ML qui ne prédit que le TC puis scale sim_v2 échoue souvent : le TC
  prédit n'est pas le TC « compatible sim_v2 » qui redonnerait le bon CA.
  ml_ca apprend la correction résiduelle entre le CA « sim_v2×TC_ml » et
  la réalité, en gardant le contexte riche (proximité, météo, marque…).

Fichiers modèles :
  models/super/{solution}/ml_tc.json + ml_tc_metadata.json
  models/super/{solution}/ml_ca.json + ml_ca_metadata.json
  models/super/{solution}/loo/{hotel}/… (eval leave-one-out)
"""

from __future__ import annotations

import json
import logging
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
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
CA_TARGET = "montant_ventes_par_mois"
META_PRED_TARGETS = tuple(t for t, _ in TARGETS)

# Préfixes colonnes enrichies
SIM_V2_BRUT_PREFIX = "sim_v2_brut__"
ML_TC_SIM_V2_PREFIX = "ml_tc_sim_v2__"

# Colonnes exclues des features descriptives (fuites / ids / cibles)
_FEATURE_EXCLUDE = {
    "scenario_id",
    "hotel_code",
    "solution",
    "is_observation",
    "scenario_removed_natures",
    CONVERSION_TARGET,
    "nombre_ventes_par_mois",  # fuite du TC
    # CA / marges réels (cibles ml_ca — jamais features brutes)
    "montant_ventes_par_mois",
    "montant_marge_par_mois",
    "montant_marge_selon_coef_par_mois",
}


@dataclass(frozen=True)
class SuperModelConfig:
    """Hyperparamètres XGBoost (ml_tc et ml_ca)."""

    n_estimators: int = 300
    learning_rate: float = 0.05
    max_depth: int = 5
    min_child_weight: float = 2.0
    subsample: float = 0.85
    colsample_bytree: float = 0.80
    colsample_bylevel: float = 0.80
    reg_lambda: float = 2.0
    reg_alpha: float = 0.1
    gamma: float = 0.0
    early_stopping_rounds: int = 40
    random_seed: int = 42
    n_jobs: int = -1
    # ml_ca : un peu plus de capacité (cible CA plus large)
    ca_n_estimators: int = 400
    ca_max_depth: int = 6
    ca_learning_rate: float = 0.04


def _norm_sol(s: Any) -> str:
    return str(s or "").strip().lower().replace("_", " ")


def _conversion_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    """Métriques sur le taux de conversion (sortie ml_tc)."""
    col_r = "taux_conversion_reel"
    col_p = "taux_conversion_predit"
    if col_r not in predictions.columns or col_p not in predictions.columns:
        return pd.DataFrame()
    y_true = predictions[col_r].to_numpy(dtype=float)
    y_pred = predictions[col_p].to_numpy(dtype=float)
    err = y_pred - y_true
    nz = np.abs(y_true) > 1e-12
    return pd.DataFrame(
        [
            {
                "target": CONVERSION_TARGET,
                "target_label": "Taux de conversion (ml_tc)",
                "nombre_hotels": len(predictions),
                "mae": float(mean_absolute_error(y_true, y_pred)),
                "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
                "mape": (
                    float(np.mean(np.abs(err[nz] / y_true[nz])) * 100.0)
                    if nz.any()
                    else float("nan")
                ),
                "biais": float(np.mean(err)),
            }
        ]
    )


class SuperModelService:
    """
    Moteur ml = ml_tc → ml_tc_sim_v2 → ml_ca (un couple de modèles par solution).
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
        self._coeff_cache: pd.DataFrame | None = None

    # ------------------------------------------------------------------ data
    def _ensure_dataset_views(self, *, rebuild_rich: bool = False) -> None:
        """Rafraîchit v_ml_training_dataset et matérialise t_rich_data."""
        cp = self.factory.open(read_only=False)
        try:
            if rebuild_rich:
                for name in ("t_rich_data", "v_web_rich_data"):
                    try:
                        cp.con.execute(f"DROP TABLE IF EXISTS {name}")
                        cp.con.execute(f"DROP VIEW IF EXISTS {name}")
                    except Exception:  # noqa: BLE001
                        pass
            for name in (
                "v_hotel_proximity_features",
                "v_hotel_weather_features",
                "v_hotel_data_features",
                "v_hotel_holidays_features",
                "v_ml_hotel_context",
                "v_ml_training_dataset",
            ):
                try:
                    cp.p_table_view(name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("view %s: %s", name, exc)
            try:
                cp.p_table_view("t_rich_data")
            except Exception as exc:  # noqa: BLE001
                logger.warning("t_rich_data: %s", exc)
            # s'assurer que les coeffs sim_v2 sont disponibles
            try:
                cp.p_table_view("v_restitution_solution_coefficients")
            except Exception as exc:  # noqa: BLE001
                logger.warning("v_restitution_solution_coefficients: %s", exc)
        finally:
            cp.close()

    def load_dataset(self, *, rebuild_rich: bool = False) -> pd.DataFrame:
        """
        Dataset = sim_v2 (obs + sim) + hd_ + px_ + wx_ + hol_ + br_marque
                  + colonnes sim_v2_brut__* (restitution pure).

        Cible TC toujours recalculée :
          taux_conversion = nombre_ventes_par_mois / nombre_guests_par_mois
        """
        self._ensure_dataset_views(rebuild_rich=rebuild_rich)
        df = load_ml_dataset(
            self.paths,
            self.factory,
            mode="rich",
            prefer_rich=True,
            attach_brand=True,
        )
        df = df.copy()
        df["solution"] = df["solution"].map(_norm_sol)

        if (
            "nombre_ventes_par_mois" in df.columns
            and "nombre_guests_par_mois" in df.columns
        ):
            g = pd.to_numeric(df["nombre_guests_par_mois"], errors="coerce")
            v = pd.to_numeric(df["nombre_ventes_par_mois"], errors="coerce")
            df[CONVERSION_TARGET] = (v / g.replace(0, np.nan)).fillna(0.0)
        elif CONVERSION_TARGET in df.columns:
            df[CONVERSION_TARGET] = pd.to_numeric(
                df[CONVERSION_TARGET], errors="coerce"
            ).fillna(0.0)
            logger.warning(
                "nombre_ventes/guests absents — conversion non recalculée"
            )
        else:
            df[CONVERSION_TARGET] = 0.0
            logger.error("Impossible de construire taux_conversion")

        df[CONVERSION_TARGET] = df[CONVERSION_TARGET].clip(lower=0.0, upper=1.0)

        # Enrichissement sim_v2_brut (CA / marges restitution pure)
        df = self._enrich_sim_v2_brut(df)

        n_obs = int(df["is_observation"].sum()) if "is_observation" in df.columns else 0
        n_sim = len(df) - n_obs
        logger.info(
            "ml dataset: rows=%s (obs=%s sim=%s) hotels=%s source=%s",
            len(df),
            n_obs,
            n_sim,
            df["hotel_code"].nunique(),
            df.attrs.get("ml_source"),
        )
        return df

    # ------------------------------------------------------------------ sim_v2_brut vectorisé
    def _load_coefficients(self, *, force: bool = False) -> pd.DataFrame:
        if self._coeff_cache is not None and not force:
            return self._coeff_cache
        cp = self.factory.open(read_only=True)
        try:
            try:
                coeffs = cp.con.execute(
                    "SELECT * FROM v_restitution_solution_coefficients"
                ).df()
            except Exception:  # noqa: BLE001
                try:
                    coeffs = cp.p_table_view(
                        "v_restitution_solution_coefficients"
                    ).df()
                except Exception as exc:  # noqa: BLE001
                    logger.error("coeffs sim_v2 indisponibles: %s", exc)
                    coeffs = pd.DataFrame()
        finally:
            cp.close()
        if not coeffs.empty:
            coeffs = coeffs.copy()
            coeffs["solution"] = coeffs["solution"].map(_norm_sol)
        self._coeff_cache = coeffs
        return coeffs

    def _enrich_sim_v2_brut(
        self,
        df: pd.DataFrame,
        coeffs: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Ajoute sim_v2_brut__{target} = prédiction restitution sim_v2 pure
        pour chaque ligne (mix + leviers de la ligne, coeffs de sa solution).

        Formule (alignée pipeline 6_restitution_prediction) :
          guests = chambres × TO × guests/chambre × 30.5
          pred_var = coeff × guests × m_lin × target_part
          AVG par famille (type / gamme) puis AVG des familles.
        """
        out = df.copy()
        coeffs = coeffs if coeffs is not None else self._load_coefficients()
        for t in META_PRED_TARGETS:
            col = f"{SIM_V2_BRUT_PREFIX}{t}"
            if col not in out.columns:
                out[col] = 0.0

        if coeffs is None or coeffs.empty:
            logger.warning("sim_v2_brut: coeffs vides — colonnes à 0")
            return out

        # Mapping target → colonne coefficient
        coeff_map = {
            "montant_ventes_par_mois": "montant_ventes_coefficient",
            "montant_marge_selon_coef_par_mois": "montant_marge_selon_coef_coefficient",
            "montant_marge_par_mois": "montant_marge_coefficient",
        }

        nb = pd.to_numeric(out.get("hotel_nb_chambres"), errors="coerce").fillna(200.0)
        to = pd.to_numeric(out.get("hotel_to_annuel"), errors="coerce").fillna(0.7)
        gpc = pd.to_numeric(
            out.get("hotel_guests_per_chambre"), errors="coerce"
        ).fillna(1.7)
        m_lin = pd.to_numeric(out.get("metres_lineaires"), errors="coerce").fillna(6.0)
        guests = nb * to * gpc * 30.5
        sols = out["solution"].map(_norm_sol)

        # Préparer parts de mix pour chaque variable_name connue
        var_names = sorted(coeffs["variable_name"].astype(str).unique())
        parts = {}
        for vn in var_names:
            if vn in out.columns:
                parts[vn] = pd.to_numeric(out[vn], errors="coerce").fillna(0.0).to_numpy()
            else:
                parts[vn] = np.zeros(len(out), dtype=float)

        results = {t: np.zeros(len(out), dtype=float) for t in META_PRED_TARGETS}

        for sol in SOLUTIONS:
            mask = (sols == sol).to_numpy()
            if not mask.any():
                continue
            csol = coeffs.loc[coeffs["solution"] == sol]
            if csol.empty:
                continue
            idx = np.where(mask)[0]
            g = guests.to_numpy()[idx]
            ml = m_lin.to_numpy()[idx]

            for t, ccol in coeff_map.items():
                if ccol not in csol.columns:
                    continue
                # par famille : moyenne des pred_var (parts > 0)
                family_avgs: list[np.ndarray] = []
                for fam in csol["variable_family"].astype(str).unique():
                    cfam = csol.loc[csol["variable_family"].astype(str) == fam]
                    preds = []
                    for row in cfam.itertuples(index=False):
                        vn = str(row.variable_name)
                        part = parts.get(vn, np.zeros(len(out)))[idx]
                        coeff = float(getattr(row, ccol) or 0.0)
                        pred = coeff * g * ml * part
                        # ne garder que parts > 0 pour l'AVG famille
                        preds.append((pred, part > 0))
                    if not preds:
                        continue
                    stack = np.stack([p for p, _ in preds], axis=0)  # (n_var, n_rows)
                    active = np.stack([a for _, a in preds], axis=0)
                    # moyenne sur variables actives ; 0 si aucune
                    n_act = active.sum(axis=0).astype(float)
                    s = (stack * active).sum(axis=0)
                    fam_avg = np.divide(
                        s, n_act, out=np.zeros_like(s), where=n_act > 0
                    )
                    family_avgs.append(fam_avg)
                if family_avgs:
                    results[t][idx] = np.mean(np.stack(family_avgs, axis=0), axis=0)

        for t in META_PRED_TARGETS:
            out[f"{SIM_V2_BRUT_PREFIX}{t}"] = np.maximum(results[t], 0.0)

        logger.info(
            "sim_v2_brut enrichi: mean_ca=%.2f",
            float(out[f"{SIM_V2_BRUT_PREFIX}{CA_TARGET}"].mean()),
        )
        return out

    # ------------------------------------------------------------------ features
    def _descriptive_feature_columns(self, df: pd.DataFrame) -> list[str]:
        """
        Features descriptives partagées ml_tc / ml_ca (sans fuites CA réels).
        Inclut sim_v2_brut__* mais PAS ml_tc_sim_v2__* (ajoutées pour ml_ca).
        """
        exclude = set(_FEATURE_EXCLUDE)
        # exclure aussi toute colonne ml_tc_sim_v2 (pipeline intermédiaire)
        ordered: list[str] = []
        for c in [*CONTEXT_FEATURES, *mix_columns(df)]:
            if c in df.columns and c not in exclude and c not in ordered:
                if pd.api.types.is_numeric_dtype(df[c]):
                    ordered.append(c)
        # sim_v2_brut en tête des enrichissements (lisibilité)
        for c in sorted(df.columns):
            if str(c).startswith(SIM_V2_BRUT_PREFIX) and c not in ordered:
                ordered.append(c)
        for c in sorted(df.columns):
            if c in exclude or c in ordered:
                continue
            if str(c).startswith(ML_TC_SIM_V2_PREFIX):
                continue
            if pd.api.types.is_numeric_dtype(df[c]):
                ordered.append(c)
        return ordered

    def _ml_ca_feature_columns(
        self, descriptive: list[str], df: pd.DataFrame | None = None
    ) -> list[str]:
        """descriptives ml_tc + colonnes ml_tc_sim_v2__*."""
        extra = [f"{ML_TC_SIM_V2_PREFIX}{t}" for t in META_PRED_TARGETS]
        if df is not None:
            extra = [c for c in extra if c in df.columns] or extra
        # dédupliquer en gardant l'ordre
        seen: set[str] = set()
        out: list[str] = []
        for c in [*descriptive, *extra]:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def _xy(
        self,
        df: pd.DataFrame,
        feature_names: list[str],
        target: str,
    ) -> tuple[pd.DataFrame, np.ndarray, pd.Series]:
        x = df.reindex(columns=feature_names).astype(float).fillna(0.0)
        y = pd.to_numeric(df[target], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        groups = df["hotel_code"].astype(str)
        return x, y, groups

    def _model_params(
        self,
        *,
        stage: str = "ml_tc",
        with_early_stopping: bool = False,
    ) -> dict[str, Any]:
        cfg = self.config
        if stage == "ml_ca":
            params: dict[str, Any] = {
                "n_estimators": cfg.ca_n_estimators,
                "learning_rate": cfg.ca_learning_rate,
                "max_depth": cfg.ca_max_depth,
                "min_child_weight": cfg.min_child_weight,
                "subsample": cfg.subsample,
                "colsample_bytree": cfg.colsample_bytree,
                "colsample_bylevel": cfg.colsample_bylevel,
                "reg_lambda": cfg.reg_lambda,
                "reg_alpha": cfg.reg_alpha,
                "gamma": cfg.gamma,
                "random_state": cfg.random_seed,
                "n_jobs": cfg.n_jobs,
                "verbosity": 0,
                "objective": "reg:squarederror",
                "tree_method": "hist",
            }
        else:
            params = {
                "n_estimators": cfg.n_estimators,
                "learning_rate": cfg.learning_rate,
                "max_depth": cfg.max_depth,
                "min_child_weight": cfg.min_child_weight,
                "subsample": cfg.subsample,
                "colsample_bytree": cfg.colsample_bytree,
                "colsample_bylevel": cfg.colsample_bylevel,
                "reg_lambda": cfg.reg_lambda,
                "reg_alpha": cfg.reg_alpha,
                "gamma": cfg.gamma,
                "random_state": cfg.random_seed,
                "n_jobs": cfg.n_jobs,
                "verbosity": 0,
                "objective": "reg:squarederror",
                "tree_method": "hist",
            }
        if with_early_stopping:
            params["early_stopping_rounds"] = cfg.early_stopping_rounds
        return params

    def _fit_xgb(
        self,
        x_train: pd.DataFrame,
        y_train: np.ndarray,
        groups: pd.Series | None = None,
        *,
        stage: str = "ml_tc",
    ) -> XGBRegressor:
        use_es = (
            groups is not None
            and groups.nunique() >= 3
            and len(x_train) >= 30
        )
        model = XGBRegressor(
            **self._model_params(stage=stage, with_early_stopping=use_es)
        )
        if use_es:
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

    # ------------------------------------------------------------------ paths / IO
    def _solution_dir(self, solution: str) -> Path:
        d = self.models_dir / _norm_sol(solution)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _loo_dir(self, solution: str, hotel_code: str) -> Path:
        d = self._solution_dir(solution) / "loo" / str(hotel_code).strip().upper()
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _save_stage_bundle(
        self,
        directory: Path,
        stage: str,
        model: XGBRegressor | None,
        meta: dict[str, Any],
    ) -> None:
        """stage ∈ {ml_tc, ml_ca}."""
        directory.mkdir(parents=True, exist_ok=True)
        meta_path = directory / f"{stage}_metadata.json"
        model_path = directory / f"{stage}.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if model is not None:
            model.save_model(str(model_path))
        elif model_path.exists():
            model_path.unlink()

        # Compat lecture ancienne : ml_tc aussi sous conversion.*
        if stage == "ml_tc":
            legacy_meta = directory / "conversion_metadata.json"
            legacy_model = directory / "conversion.json"
            legacy_meta.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if model is not None:
                model.save_model(str(legacy_model))
            elif legacy_model.exists():
                legacy_model.unlink()

    def _load_stage_model(
        self,
        directory: Path,
        stage: str,
    ) -> tuple[XGBRegressor | None, dict[str, Any]]:
        meta_path = directory / f"{stage}_metadata.json"
        model_path = directory / f"{stage}.json"
        # fallback legacy pour ml_tc
        if stage == "ml_tc" and not meta_path.exists():
            meta_path = directory / "conversion_metadata.json"
            model_path = directory / "conversion.json"
        meta: dict[str, Any] = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        model = None
        if model_path.exists():
            model = XGBRegressor()
            model.load_model(str(model_path))
        return model, meta

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
        """Restitution sim_v2 live pour une ligne hôtel / mix (fallback)."""
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
            nb = float(row.get("hotel_nb_chambres") or 200)
            to = float(row.get("hotel_to_annuel") or 0.7)
            guests = float(row.get("hotel_guests_per_chambre") or 1.7)
            m_lin = float(row.get("metres_lineaires") or 6)
            sol = _norm_sol(row.get("solution") or "simply")
            pred_df = svc.predict(
                hotel_nb_chambres=nb,
                hotel_to_annuel=to,
                hotel_guests_per_chambre=guests,
                metres_lineaires=m_lin,
                type_mix=type_mix or {"F&B": 0.7, "NON F&B": 0.3},
                gamme_mix=gamme_mix or None,
            )
            if pred_df is None or pred_df.empty:
                return {t: 0.0 for t in META_PRED_TARGETS}
            if "solution" in pred_df.columns:
                hit = pred_df.loc[
                    pred_df["solution"].astype(str).str.lower() == sol
                ]
                if hit.empty:
                    hit = pred_df
            else:
                hit = pred_df
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
    def _scale_sim_v2_with_tc(
        sim_v2: dict[str, float],
        conv_pred: float,
        conv_baseline: float,
    ) -> dict[str, float]:
        """ml_tc_sim_v2 = sim_v2_brut × (tc_pred / tc_baseline)."""
        base = (
            float(conv_baseline) if conv_baseline and conv_baseline > 1e-12 else 1e-12
        )
        ratio = max(0.0, float(conv_pred)) / base
        out: dict[str, float] = {
            "taux_conversion_predit": float(conv_pred),
            "taux_conversion_baseline": float(conv_baseline),
            "conversion_scale": float(ratio),
        }
        for t in META_PRED_TARGETS:
            out[t] = max(0.0, float(sim_v2.get(t) or 0.0) * ratio)
        return out

    def _apply_ml_tc_sim_v2_columns(
        self,
        df: pd.DataFrame,
        tc_pred: np.ndarray,
        baseline: float,
    ) -> pd.DataFrame:
        """Ajoute ml_tc_sim_v2__* à partir de sim_v2_brut et tc_pred."""
        out = df.copy()
        base = float(baseline) if baseline and baseline > 1e-12 else 1e-12
        ratio = np.maximum(tc_pred.astype(float), 0.0) / base
        for t in META_PRED_TARGETS:
            brut_col = f"{SIM_V2_BRUT_PREFIX}{t}"
            if brut_col in out.columns:
                brut = pd.to_numeric(out[brut_col], errors="coerce").fillna(0.0)
            else:
                brut = pd.Series(0.0, index=out.index)
            out[f"{ML_TC_SIM_V2_PREFIX}{t}"] = (brut.to_numpy() * ratio).clip(min=0.0)
        out["_tc_pred"] = tc_pred
        out["_tc_baseline"] = baseline
        out["_conversion_scale"] = ratio
        return out

    # ------------------------------------------------------------------ features hôtel live
    def hotel_context_features(self, hotel_code: str) -> dict[str, float]:
        """Charge px_ / wx_ / hd_ / br_ pour un hôtel (prédiction user)."""
        code = str(hotel_code or "").strip()
        if not code:
            return {}
        out: dict[str, float] = {}
        cp = self.factory.open(read_only=True)
        try:
            for view, _prefix in (
                ("v_hotel_data_features", "hd_"),
                ("v_hotel_proximity_features", "px_"),
                ("v_hotel_weather_features", "wx_"),
                ("v_hotel_holidays_features", "hol_"),
            ):
                try:
                    hdf = cp.con.execute(
                        f"SELECT * FROM {view} WHERE CAST(hotel_code AS VARCHAR) = ?",
                        [code],
                    ).df()
                except Exception:  # noqa: BLE001
                    continue
                if hdf.empty:
                    continue
                row = hdf.iloc[0]
                for c, v in row.items():
                    if c == "hotel_code":
                        continue
                    try:
                        out[str(c)] = float(v) if pd.notna(v) else 0.0
                    except (TypeError, ValueError):
                        continue
            try:
                from src.ml.common import _attach_brand_features

                tiny = pd.DataFrame({"hotel_code": [code]})
                br = _attach_brand_features(tiny, cp)
                for c in br.columns:
                    if str(c).startswith("br_"):
                        try:
                            out[str(c)] = (
                                float(br.iloc[0][c])
                                if pd.notna(br.iloc[0][c])
                                else 0.0
                            )
                        except (TypeError, ValueError):
                            out[str(c)] = 0.0
            except Exception:  # noqa: BLE001
                pass
        finally:
            cp.close()
        return out

    # ------------------------------------------------------------------ train helpers
    def _predict_tc_array(
        self,
        model: XGBRegressor | None,
        x: pd.DataFrame,
        baseline: float,
    ) -> np.ndarray:
        if model is None:
            return np.full(len(x), float(baseline), dtype=float)
        pred = model.predict(x)
        return np.clip(np.asarray(pred, dtype=float), 0.0, 1.0)

    def _train_solution_pair(
        self,
        sub: pd.DataFrame,
        descriptive_features: list[str],
        sol: str,
        *,
        directory: Path,
        loo_hotel: str | None = None,
        eval_biased: bool = False,
    ) -> dict[str, Any]:
        """
        Entraîne ml_tc puis ml_ca pour une solution, sauvegarde dans directory.
        Retourne le meta combiné.
        """
        n_hotels = int(sub["hotel_code"].nunique())
        x_tc, y_tc, g_tc = self._xy(sub, descriptive_features, CONVERSION_TARGET)
        baseline = float(np.nanmean(y_tc)) if len(y_tc) else 0.05

        ml_tc: XGBRegressor | None = None
        if len(sub) >= 3 and float(np.nanstd(y_tc)) > 1e-12:
            ml_tc = self._fit_xgb(x_tc, y_tc, g_tc, stage="ml_tc")
        else:
            logger.warning(
                "ml_tc %s: variance insuffisante — fallback moyenne (%.5f)",
                sol,
                baseline,
            )

        tc_pred = self._predict_tc_array(ml_tc, x_tc, baseline)
        enriched = self._apply_ml_tc_sim_v2_columns(sub, tc_pred, baseline)
        ca_features = self._ml_ca_feature_columns(descriptive_features, enriched)
        x_ca, y_ca, g_ca = self._xy(enriched, ca_features, CA_TARGET)

        ml_ca: XGBRegressor | None = None
        if len(sub) >= 3 and float(np.nanstd(y_ca)) > 1e-12:
            ml_ca = self._fit_xgb(x_ca, y_ca, g_ca, stage="ml_ca")
        else:
            logger.warning(
                "ml_ca %s: variance insuffisante — fallback mean CA",
                sol,
            )

        n_px = sum(1 for c in descriptive_features if str(c).startswith("px_"))
        n_wx = sum(1 for c in descriptive_features if str(c).startswith("wx_"))
        n_hd = sum(1 for c in descriptive_features if str(c).startswith("hd_"))
        n_br = sum(1 for c in descriptive_features if str(c).startswith("br_"))
        n_brut = sum(
            1 for c in descriptive_features if str(c).startswith(SIM_V2_BRUT_PREFIX)
        )

        meta_tc: dict[str, Any] = {
            "solution": sol,
            "stage": "ml_tc",
            "target": CONVERSION_TARGET,
            "feature_names": descriptive_features,
            "params": self._model_params(stage="ml_tc"),
            "training_rows": len(sub),
            "training_hotels": n_hotels,
            "training_obs": (
                int(sub["is_observation"].sum())
                if "is_observation" in sub.columns
                else None
            ),
            "training_sim": (
                len(sub) - int(sub["is_observation"].sum())
                if "is_observation" in sub.columns
                else None
            ),
            "conversion_baseline": baseline,
            "conversion_mean": baseline,
            "conversion_std": float(np.nanstd(y_tc)) if len(y_tc) else 0.0,
            "n_features": len(descriptive_features),
            "n_features_px": n_px,
            "n_features_wx": n_wx,
            "n_features_hd": n_hd,
            "n_features_br": n_br,
            "n_features_sim_v2_brut": n_brut,
            "engine": "ml",
            "model_kind": "ml_tc" if ml_tc is not None else "ml_tc_mean_fallback",
            "algorithm": "xgboost_regressor",
            "note": (
                "ml_tc: XGBoost → taux_conversion réel ; "
                "features = descriptives + sim_v2_brut"
            ),
        }
        if loo_hotel:
            meta_tc["loo_hotel"] = loo_hotel
            meta_tc["eval_biased"] = bool(eval_biased)

        ca_baseline = float(np.nanmean(y_ca)) if len(y_ca) else 0.0
        meta_ca: dict[str, Any] = {
            "solution": sol,
            "stage": "ml_ca",
            "target": CA_TARGET,
            "feature_names": ca_features,
            "descriptive_feature_names": descriptive_features,
            "params": self._model_params(stage="ml_ca"),
            "training_rows": len(sub),
            "training_hotels": n_hotels,
            "conversion_baseline": baseline,
            "ca_baseline": ca_baseline,
            "ca_mean": ca_baseline,
            "ca_std": float(np.nanstd(y_ca)) if len(y_ca) else 0.0,
            "n_features": len(ca_features),
            "engine": "ml",
            "model_kind": "ml_ca" if ml_ca is not None else "ml_ca_mean_fallback",
            "algorithm": "xgboost_regressor",
            "chain": "ml_tc → ml_tc_sim_v2 → ml_ca",
            "note": (
                "ml_ca: XGBoost → CA final ; "
                "features = descriptives ml_tc + ml_tc_sim_v2"
            ),
        }
        if loo_hotel:
            meta_ca["loo_hotel"] = loo_hotel
            meta_ca["eval_biased"] = bool(eval_biased)

        self._save_stage_bundle(directory, "ml_tc", ml_tc, meta_tc)
        self._save_stage_bundle(directory, "ml_ca", ml_ca, meta_ca)

        return {
            "solution": sol,
            "ml_tc": meta_tc,
            "ml_ca": meta_ca,
            "conversion_baseline": baseline,
            "ca_baseline": ca_baseline,
            "ml_tc_model": ml_tc,
            "ml_ca_model": ml_ca,
            "descriptive_features": descriptive_features,
            "ca_features": ca_features,
        }

    # ------------------------------------------------------------------ train global
    def train_final(self, df: pd.DataFrame | None = None) -> list[dict[str, Any]]:
        """Entraînement des modèles globaux ml_tc + ml_ca (un couple par solution)."""
        df = df if df is not None else self.load_dataset()
        descriptive = self._descriptive_feature_columns(df)
        results: list[dict[str, Any]] = []

        n_px = sum(1 for c in descriptive if str(c).startswith("px_"))
        n_wx = sum(1 for c in descriptive if str(c).startswith("wx_"))
        n_hd = sum(1 for c in descriptive if str(c).startswith("hd_"))
        n_br = sum(1 for c in descriptive if str(c).startswith("br_"))
        n_brut = sum(1 for c in descriptive if str(c).startswith(SIM_V2_BRUT_PREFIX))
        logger.info(
            "features descriptives: total=%s px=%s wx=%s hd=%s br=%s sim_v2_brut=%s mix=%s",
            len(descriptive),
            n_px,
            n_wx,
            n_hd,
            n_br,
            n_brut,
            len(mix_columns(df)),
        )

        for sol in SOLUTIONS:
            sub = df.loc[df["solution"] == sol].copy()
            if sub.empty:
                logger.warning("Pas de données pour %s — skip", sol)
                continue
            sdir = self._solution_dir(sol)
            pair = self._train_solution_pair(
                sub, descriptive, sol, directory=sdir
            )
            results.append(
                {
                    "solution": sol,
                    "ml_tc": {
                        k: v
                        for k, v in pair["ml_tc"].items()
                        if k != "feature_names"
                    },
                    "ml_ca": {
                        k: v
                        for k, v in pair["ml_ca"].items()
                        if k not in {"feature_names", "descriptive_feature_names"}
                    },
                    "n_features_ml_tc": len(descriptive),
                    "n_features_ml_ca": len(pair["ca_features"]),
                    "conversion_baseline": pair["conversion_baseline"],
                    "ca_baseline": pair["ca_baseline"],
                }
            )
            logger.info(
                "ml_tc+ml_ca %s sauvés (rows=%s hotels=%s baseline_tc=%.5f)",
                sol,
                len(sub),
                int(sub["hotel_code"].nunique()),
                pair["conversion_baseline"],
            )

        index = {
            "engine": "ml",
            "architecture": "ml_tc → ml_tc_sim_v2 → ml_ca",
            "algorithm": "xgboost_regressor",
            "stages": {
                "ml_tc": {
                    "target": CONVERSION_TARGET,
                    "role": "Prédit le taux de conversion réel (ventes/guests)",
                    "features": "descriptives + sim_v2_brut",
                },
                "ml_tc_sim_v2": {
                    "target": None,
                    "role": (
                        "Intermédiaire : CA sim_v2 appliqué avec TC de ml_tc "
                        "(pas un modèle entraîné)"
                    ),
                    "formula": "sim_v2_brut × (tc_ml_tc / tc_baseline)",
                },
                "ml_ca": {
                    "target": CA_TARGET,
                    "role": "Prédit le CA final reporté par le moteur ml",
                    "features": "descriptives ml_tc + ml_tc_sim_v2",
                },
            },
            "solutions": list(SOLUTIONS),
            "models": results,
            "note": (
                "Le moteur « ml » des évaluations admin et estimations utilisateur "
                "est la chaîne complète ml_tc → ml_tc_sim_v2 → ml_ca. "
                "La décision finale est la sortie de ml_ca."
            ),
        }
        (self.models_dir / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # nettoyer anciens modèles CA multi-cibles à la racine super/
        for legacy in self.models_dir.glob("montant_*"):
            try:
                if legacy.is_file():
                    legacy.unlink()
                    logger.info("supprimé legacy %s", legacy.name)
            except OSError:
                pass
        return results

    def _predict_tc_from_dir(
        self,
        directory: Path,
        feature_row: dict[str, float],
        solution: str,
        *,
        model: XGBRegressor | None = None,
        meta: dict[str, Any] | None = None,
    ) -> tuple[float, float, list[str]]:
        """Retourne (tc_pred, tc_baseline, feature_names_tc)."""
        if model is None or meta is None:
            model, meta = self._load_stage_model(directory, "ml_tc")
        names = list(meta.get("feature_names") or list(CONTEXT_FEATURES))
        base = float(meta.get("conversion_baseline") or 0.05)
        if model is None:
            return base, base, names
        x = build_feature_row(names, feature_row, solution)
        pred = float(model.predict(x)[0])
        pred = max(0.0, min(1.0, pred))
        return pred, base, names

    def _predict_ca_from_dir(
        self,
        directory: Path,
        feature_row: dict[str, float],
        solution: str,
        *,
        model: XGBRegressor | None = None,
        meta: dict[str, Any] | None = None,
        ca_baseline: float | None = None,
    ) -> float:
        if model is None or meta is None:
            model, meta = self._load_stage_model(directory, "ml_ca")
        names = list(meta.get("feature_names") or [])
        base = (
            float(ca_baseline)
            if ca_baseline is not None
            else float(meta.get("ca_baseline") or 0.0)
        )
        if model is None or not names:
            return max(0.0, base)
        x = build_feature_row(names, feature_row, solution)
        pred = float(model.predict(x)[0])
        return max(0.0, pred)

    # ------------------------------------------------------------------ LOO
    def leave_one_hotel_out(
        self,
        df: pd.DataFrame | None = None,
        *,
        save_models: bool = True,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Eval leave-one-hotel-out par solution :

          - train ml_tc + ml_ca sans l'hôtel (si n_hotels_solution > 1)
          - sinon eval_biased (hôtel reste dans le train)
          - prédiction test : chaîne ml_tc → ml_tc_sim_v2 → ml_ca
        """
        df = df if df is not None else self.load_dataset()
        descriptive = self._descriptive_feature_columns(df)
        observation = df["is_observation"].astype(bool)
        obs = df.loc[observation].copy()
        hotels = sorted(obs["hotel_code"].astype(str).unique())
        sim_loo = self._load_sim_v2_loo_map()

        sol_of = {
            str(r.hotel_code): _norm_sol(r.solution)
            for r in obs.itertuples(index=False)
        }
        sol_counts: dict[str, int] = {}
        for s in sol_of.values():
            sol_counts[s] = sol_counts.get(s, 0) + 1

        if save_models:
            for sol in SOLUTIONS:
                loo_root = self._solution_dir(sol) / "loo"
                if loo_root.exists():
                    shutil.rmtree(loo_root, ignore_errors=True)

        rows: list[dict[str, Any]] = []
        for index, hotel in enumerate(hotels, start=1):
            sol = sol_of.get(hotel, "simply")
            biased = sol_counts.get(sol, 0) <= 1
            logger.info(
                "ml chain LOO %s/%s | hotel=%s sol=%s n_sol=%s%s",
                index,
                len(hotels),
                hotel,
                sol,
                sol_counts.get(sol, 0),
                " | eval_biased" if biased else "",
            )
            test_mask = observation & (df["hotel_code"].astype(str) == hotel)
            if int(test_mask.sum()) != 1:
                raise ValueError(
                    f"Observation unique attendue pour {hotel}, "
                    f"trouvé {int(test_mask.sum())}"
                )
            source = df.loc[test_mask].iloc[0]

            train_sol = df["solution"] == sol
            if biased:
                train_mask = train_sol
            else:
                train_mask = train_sol & (df["hotel_code"].astype(str) != hotel)
            sub = df.loc[train_mask]
            if sub.empty:
                sub = df.loc[train_sol]

            loo_dir = self._loo_dir(sol, hotel) if save_models else self._solution_dir(sol)
            pair = self._train_solution_pair(
                sub,
                descriptive,
                sol,
                directory=loo_dir if save_models else self._solution_dir(sol),
                loo_hotel=hotel if save_models else None,
                eval_biased=biased,
            )
            # si save_models=False, modèles en mémoire uniquement
            ml_tc = pair["ml_tc_model"]
            ml_ca = pair["ml_ca_model"]
            baseline = pair["conversion_baseline"]
            ca_features = pair["ca_features"]

            # Features test : descriptives + sim_v2_brut (déjà dans source)
            # Pour l'hôtel LOO, préférer sim_v2 LOO si dispo
            feat_row = {
                c: float(source[c])
                for c in descriptive
                if c in source.index and pd.notna(source[c])
            }
            if hotel in sim_loo:
                v2 = sim_loo[hotel]
                for t in META_PRED_TARGETS:
                    feat_row[f"{SIM_V2_BRUT_PREFIX}{t}"] = float(v2.get(t) or 0.0)
            else:
                v2 = {
                    t: float(source.get(f"{SIM_V2_BRUT_PREFIX}{t}") or 0.0)
                    for t in META_PRED_TARGETS
                }
                if not any(v2.values()):
                    v2 = self._sim_v2_pred_for_observation(source)
                    for t in META_PRED_TARGETS:
                        feat_row[f"{SIM_V2_BRUT_PREFIX}{t}"] = float(v2.get(t) or 0.0)

            # 1) ml_tc
            x_tc = build_feature_row(descriptive, feat_row, sol)
            if ml_tc is not None:
                conv_pred = max(0.0, min(1.0, float(ml_tc.predict(x_tc)[0])))
            else:
                conv_pred = baseline

            # 2) ml_tc_sim_v2
            scaled = self._scale_sim_v2_with_tc(v2, conv_pred, baseline)
            for t in META_PRED_TARGETS:
                feat_row[f"{ML_TC_SIM_V2_PREFIX}{t}"] = float(scaled.get(t) or 0.0)

            # 3) ml_ca
            x_ca = build_feature_row(ca_features, feat_row, sol)
            if ml_ca is not None:
                ca_pred = max(0.0, float(ml_ca.predict(x_ca)[0]))
            else:
                ca_pred = float(scaled.get(CA_TARGET) or pair["ca_baseline"] or 0.0)

            # Marges : proportionnelles au ratio CA_ml / CA_ml_tc_sim_v2
            ca_bridge = float(scaled.get(CA_TARGET) or 0.0)
            if ca_bridge > 1e-9:
                margin_ratio = ca_pred / ca_bridge
            else:
                margin_ratio = float(scaled.get("conversion_scale") or 1.0)

            final_preds = {
                CA_TARGET: ca_pred,
                "montant_marge_selon_coef_par_mois": max(
                    0.0,
                    float(scaled.get("montant_marge_selon_coef_par_mois") or 0.0)
                    * margin_ratio,
                ),
                "montant_marge_par_mois": max(
                    0.0,
                    float(scaled.get("montant_marge_par_mois") or 0.0) * margin_ratio,
                ),
            }

            conv_reel = float(source.get(CONVERSION_TARGET) or 0.0)
            row: dict[str, Any] = {
                "hotel_code": hotel,
                "solution": sol,
                "eval_biased": bool(biased),
                "taux_conversion_reel": conv_reel,
                "taux_conversion_predit": conv_pred,
                "taux_conversion_baseline": baseline,
                "conversion_scale": scaled["conversion_scale"],
                "ml_tc_sim_v2__montant_ventes_par_mois": float(
                    scaled.get(CA_TARGET) or 0.0
                ),
                "pred_sim_v2_brut__montant_ventes_par_mois": float(
                    v2.get(CA_TARGET) or 0.0
                ),
                "chain": "ml_tc→ml_tc_sim_v2→ml_ca",
            }
            for t, _lab in TARGETS:
                actual = float(source.get(t) or 0.0)
                pred = float(final_preds.get(t) or 0.0)
                row[f"{t}_reel"] = actual
                row[f"{t}_predit"] = pred
                row[f"{t}_erreur"] = pred - actual
                row[f"{t}_erreur_absolue"] = abs(pred - actual)
                row[f"pred_sim_v2__{t}"] = float(v2.get(t) or 0.0)
                row[f"pred_ml_tc_sim_v2__{t}"] = float(scaled.get(t) or 0.0)
            rows.append(row)

        predictions = pd.DataFrame(rows)
        ca_metrics = metrics_frame(predictions, TARGETS)
        conv_metrics = _conversion_metrics(predictions)
        metrics = (
            pd.concat([conv_metrics, ca_metrics], ignore_index=True)
            if not conv_metrics.empty
            else ca_metrics
        )
        return predictions, metrics

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
        logger.info("Export ml chain LOO : %s", path)
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
        Production (modèles globaux par solution) — chaîne complète :

          1) sim_v2_brut (restitution pure)
          2) ml_tc → taux_conversion
          3) ml_tc_sim_v2 = sim_v2_brut × (tc / baseline)
          4) ml_ca → CA final (décision moteur ml)
        """
        sol = _norm_sol(solution)
        sdir = self._solution_dir(sol)
        index_path = self.models_dir / "index.json"
        tc_meta_path = sdir / "ml_tc_metadata.json"
        legacy_meta = sdir / "conversion_metadata.json"
        if (
            not tc_meta_path.exists()
            and not legacy_meta.exists()
            and not index_path.exists()
        ):
            raise FileNotFoundError(
                "Modèle ml absent. Lancer : python run.py ml --rebuild"
            )

        # enrichir avec contexte hôtel (px/wx/hd/br)
        merged = dict(feature_row or {})
        if hotel_code:
            ctx = self.hotel_context_features(str(hotel_code))
            for k, v in ctx.items():
                if k not in merged:
                    merged[k] = v

        # mix → colonnes part_natures
        for k, v in (type_mix or {}).items():
            col = f"type_{k.replace(' ', '_').replace('&', '_')}_part_natures"
            merged.setdefault(col, float(v))
        for k, v in (gamme_mix or {}).items():
            col = f"gamme_{k.replace(' ', '_')}_part_natures"
            merged.setdefault(col, float(v))

        series = pd.Series({**merged, "solution": sol})
        v2 = self._sim_v2_pred_for_observation(series)
        if hotel_code:
            loo = self._load_sim_v2_loo_map().get(str(hotel_code))
            if not any(v2.values()) and loo:
                v2 = loo
        for t in META_PRED_TARGETS:
            merged[f"{SIM_V2_BRUT_PREFIX}{t}"] = float(v2.get(t) or 0.0)

        # 1) ml_tc
        conv_pred, conv_base, _tc_feats = self._predict_tc_from_dir(
            sdir, merged, sol
        )

        # 2) ml_tc_sim_v2
        scaled = self._scale_sim_v2_with_tc(v2, conv_pred, conv_base)
        for t in META_PRED_TARGETS:
            merged[f"{ML_TC_SIM_V2_PREFIX}{t}"] = float(scaled.get(t) or 0.0)

        # 3) ml_ca
        ca_pred = self._predict_ca_from_dir(sdir, merged, sol)
        # Si ml_ca absent (legacy conversion only) → fallback scale
        _, ca_meta = self._load_stage_model(sdir, "ml_ca")
        if not ca_meta and not (sdir / "ml_ca.json").exists():
            ca_pred = float(scaled.get(CA_TARGET) or 0.0)

        ca_bridge = float(scaled.get(CA_TARGET) or 0.0)
        if ca_bridge > 1e-9:
            margin_ratio = ca_pred / ca_bridge
        else:
            margin_ratio = float(scaled.get("conversion_scale") or 1.0)

        out: dict[str, Any] = {
            "solution": sol,
            "engine": "ml",
            "model": f"ml_ca_{sol}",
            "chain": "ml_tc→ml_tc_sim_v2→ml_ca",
            "algorithm": "xgboost_regressor",
            "target": CA_TARGET,
            "taux_conversion_predit": float(conv_pred),
            "taux_conversion_baseline": float(conv_base),
            "conversion_scale": float(scaled["conversion_scale"]),
            "ml_tc_sim_v2__montant_ventes_par_mois": ca_bridge,
            "base_predictions": {
                "sim_v2_brut": {
                    t: float(v2.get(t) or 0) for t in META_PRED_TARGETS
                },
                "ml_tc": {
                    "taux_conversion": conv_pred,
                    "baseline": conv_base,
                },
                "ml_tc_sim_v2": {
                    t: float(scaled.get(t) or 0) for t in META_PRED_TARGETS
                },
            },
        }
        out[CA_TARGET] = float(ca_pred)
        out["montant_marge_selon_coef_par_mois"] = max(
            0.0,
            float(scaled.get("montant_marge_selon_coef_par_mois") or 0.0)
            * margin_ratio,
        )
        out["montant_marge_par_mois"] = max(
            0.0,
            float(scaled.get("montant_marge_par_mois") or 0.0) * margin_ratio,
        )
        return out

    def run_full(self, *, rebuild_rich: bool = True) -> dict[str, Any]:
        """
        Pipeline complet :
          1) rebuild dataset riche + sim_v2_brut
          2) train ml_tc + ml_ca globaux (user)
          3) LOO chaîne complète (+ sauvegarde modèles LOO)
          4) export eval pour admin
        """
        df = self.load_dataset(rebuild_rich=rebuild_rich)
        self.train_final(df)
        predictions, metrics = self.leave_one_hotel_out(df, save_models=True)
        path = self.export_loo(predictions, metrics)
        return {
            "predictions": predictions,
            "metrics": metrics,
            "excel": path,
            "engine": "ml",
            "architecture": "ml_tc → ml_tc_sim_v2 → ml_ca",
            "algorithm": "xgboost_regressor",
            "target": CA_TARGET,
            "source": df.attrs.get("ml_source"),
            "n_features": len(self._descriptive_feature_columns(df)),
        }
