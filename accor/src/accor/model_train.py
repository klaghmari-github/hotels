"""
Entraînement XGBoost à partir de model_data.

Pipeline
--------
1. Charge (ou reconstruit) model_data.
2. Features = colonnes descriptives (meta).
3. Targets = volumes + pct cibles (multi-output).
4. Split temporel : _is_eval=0 train, _is_eval=1 eval (dernière année).
5. Un XGBRegressor par cible (sklearn MultiOutputRegressor).
6. Sauvegarde design : models/design/<slug>/model.pkl + config.json.
7. Deploy : copie vers models/deploy/ (modèle « en production » simu).

Côté UI
-------
POST /api/model/build       lance un batch (manuel + grille hyperparams)
GET  /api/model/build/progress   état JSON pour le poll
list_design_models / get_top_model   ranking (souvent sur montant_ventes)
deploy_model                écrit models/deploy/

Classes internes
----------------
BuildProgress     état d'un batch (thread d'entraînement)
GridSearchPlanner produit cartésien des grilles, dédupliqué

Fichiers annexes : models/last_trained.json, models/build_progress.json.
Exploration détaillée des arbres : model_explore.py.
Eval année incomplete (moyenne /12) : model_eval.py.
"""

from __future__ import annotations

import itertools
import json
import pickle
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from accor.data_io import DATA_DIR, MODELS_DIR, PROJECT_ROOT
from accor.model_data import (
    MAIN_TARGET,
    MODEL_DATA_FILENAME,
    MODEL_DATA_SHEET,
    ensure_model_data,
    load_model_data_meta,
    rebuild_model_data,
)

ROOT = PROJECT_ROOT
DESIGN_DIR = MODELS_DIR / "design"
DEPLOY_DIR = MODELS_DIR / "deploy"
LAST_TRAINED_FILE = MODELS_DIR / "last_trained.json"
BUILD_PROGRESS_FILE = MODELS_DIR / "build_progress.json"

_build_lock = threading.Lock()
_build_thread: threading.Thread | None = None


class BuildProgress:
    """
    Etat partage d un build batch (manuel + grid).

    Thread-safe ; persiste un resume dans models/build_progress.json
    pour le polling UI.

    Champs utiles UI
    ----------------
    done / total     modeles termines / prevus
    job_fraction     0–1 avancement *dans* le job courant (cibles / arbres)
    pct              pourcentage global (done + fraction) / total
    phase            prepare | train | save | done | error | idle
    current_target   nom de la cible en cours (multi-output)
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = self._empty()
        self._last_persist = 0.0

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "status": "idle",
            "phase": "idle",
            "done": 0,
            "total": 0,
            "job_fraction": 0.0,
            "pct": 0.0,
            "current_name": "",
            "current_target": "",
            "message": "",
            "results": [],
            "error": None,
            "rank_metric": "r2",
            "main_target": MAIN_TARGET,
            "started_at": None,
            "finished_at": None,
        }

    def _compute_pct_unlocked(self) -> float:
        status = self._state.get("status")
        done = float(self._state.get("done") or 0)
        total = max(1.0, float(self._state.get("total") or 1))
        frac = float(self._state.get("job_fraction") or 0.0)
        frac = min(max(frac, 0.0), 1.0)
        if status == "done":
            return 100.0
        if status == "error":
            return min(99.0, (done / total) * 100.0)
        if status == "running":
            # plafonner a 99.5 tant que pas fini (evite barre a 100% trop tot)
            return min(99.5, ((done + frac) / total) * 100.0)
        if total and done:
            return min(100.0, (done / total) * 100.0)
        return 0.0

    def snapshot(self) -> dict[str, Any]:
        with _build_lock:
            out = dict(self._state)
            out["results"] = list(self._state.get("results") or [])
            out["pct"] = round(self._compute_pct_unlocked(), 1)
            out["job_fraction"] = float(self._state.get("job_fraction") or 0.0)
            return out

    def update(self, **kwargs: Any) -> None:
        """
        Met a jour l'etat en memoire (toujours) et persiste sur disque
        au plus toutes les ~0.35 s (les callbacks arbres sont frequents).
        Force l'ecriture si status/done/phase changent de facon structurelle.
        """
        force = any(
            k in kwargs for k in ("status", "done", "results", "error", "phase")
        )
        with _build_lock:
            self._state.update(kwargs)
            self._state["pct"] = self._compute_pct_unlocked()
            now = time.monotonic()
            if force or (now - self._last_persist) >= 0.35:
                self._persist_unlocked()
                self._last_persist = now

    def reset_running(
        self,
        *,
        total: int,
        main_target: str,
        rank_metric: str,
    ) -> None:
        with _build_lock:
            self._state = self._empty()
            self._state.update(
                {
                    "status": "running",
                    "phase": "prepare",
                    "done": 0,
                    "total": total,
                    "job_fraction": 0.0,
                    "pct": 0.0,
                    "main_target": main_target,
                    "rank_metric": rank_metric,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "message": "Demarrage…",
                }
            )
            self._last_persist = 0.0
            self._persist_unlocked()
            self._last_persist = time.monotonic()

    def is_running(self) -> bool:
        with _build_lock:
            return self._state.get("status") == "running"

    def _persist_unlocked(self) -> None:
        try:
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            slim = []
            for r in self._state.get("results") or []:
                slim.append(
                    {
                        "name": r.get("name"),
                        "id": r.get("id"),
                        "kind": r.get("kind"),
                        "rank": r.get("rank"),
                        "score": r.get("score"),
                        "main_target": r.get("main_target"),
                        "rank_metric": r.get("rank_metric"),
                        "metric_value": r.get("metric_value"),
                        "xgb_params": r.get("xgb_params"),
                        "metrics_eval": r.get("metrics_eval"),
                        "n_train": r.get("n_train"),
                        "n_eval": r.get("n_eval"),
                        "error": r.get("error"),
                        "ok": r.get("ok"),
                    }
                )
            payload = {
                **self._state,
                "results": slim,
                "pct": self._compute_pct_unlocked(),
            }
            BUILD_PROGRESS_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass


class GridSearchPlanner:
    """Planifie les jobs d entrainement : 1 manuel + N combinaisons grid."""

    def __init__(
        self,
        *,
        base_name: str,
        manual_params: dict[str, Any],
        grid: dict[str, list[Any]] | None = None,
    ) -> None:
        self.base_name = _slug(base_name or "xgb_sales")
        self.manual_params = _coerce_params(manual_params)
        self.grid = grid or {}

    def jobs(self) -> list[tuple[str, str, dict[str, Any]]]:
        """Liste (name, kind, params) a entrainer."""
        out: list[tuple[str, str, dict[str, Any]]] = [
            (self.base_name, "manual", self.manual_params)
        ]
        combos = expand_grid_search(self.grid, base_params=self.manual_params)
        for i, combo in enumerate(combos, start=1):
            if combo == self.manual_params:
                continue
            out.append((f"{self.base_name}_gs_{i:03d}", "grid", combo))
        return out

    def counts(self) -> dict[str, Any]:
        jobs = self.jobs()
        n_grid = sum(1 for _, k, _ in jobs if k == "grid")
        return {
            "n_manual": 1,
            "n_grid": n_grid,
            "n_grid_raw": len(
                expand_grid_search(self.grid, base_params=self.manual_params)
            ),
            "total": len(jobs),
        }


# Instance module-level pour le polling Flask
_BUILD_PROGRESS = BuildProgress()

DEFAULT_XGB_PARAMS: dict[str, Any] = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.08,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "min_child_weight": 1,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "gamma": 0.0,
    "random_state": 42,
    "n_jobs": -1,
    "objective": "reg:squarederror",
    "tree_method": "hist",
}

PARAM_SCHEMA: list[dict[str, Any]] = [
    {"name": "n_estimators", "label": "n_estimators", "type": "int", "min": 10, "max": 2000, "step": 10},
    {"name": "max_depth", "label": "max_depth", "type": "int", "min": 1, "max": 20, "step": 1},
    {"name": "learning_rate", "label": "learning_rate", "type": "float", "min": 0.001, "max": 1.0, "step": 0.01},
    {"name": "subsample", "label": "subsample", "type": "float", "min": 0.1, "max": 1.0, "step": 0.05},
    {"name": "colsample_bytree", "label": "colsample_bytree", "type": "float", "min": 0.1, "max": 1.0, "step": 0.05},
    {"name": "min_child_weight", "label": "min_child_weight", "type": "float", "min": 0, "max": 50, "step": 0.5},
    {"name": "reg_alpha", "label": "reg_alpha (L1)", "type": "float", "min": 0, "max": 10, "step": 0.1},
    {"name": "reg_lambda", "label": "reg_lambda (L2)", "type": "float", "min": 0, "max": 10, "step": 0.1},
    {"name": "gamma", "label": "gamma", "type": "float", "min": 0, "max": 10, "step": 0.1},
    {"name": "random_state", "label": "random_state", "type": "int", "min": 0, "max": 99999, "step": 1},
]


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (name or "xgb_sales").strip())[:60]
    return s or "xgb_sales"


def _load_model_frame() -> tuple[pd.DataFrame, dict[str, Any]]:
    ensure_model_data(force=False)
    path = DATA_DIR / MODEL_DATA_FILENAME
    if not path.exists():
        rebuild_model_data()
    try:
        frame = pd.read_excel(path, sheet_name=MODEL_DATA_SHEET)
    except ValueError:
        frame = pd.read_excel(path, sheet_name=0)
    meta = load_model_data_meta()
    if not meta:
        # recompute roles
        from accor.model_data import classify_columns, build_model_dataframe

        _, meta = build_model_dataframe(frame.drop(columns=["_is_eval"], errors="ignore"))
    return frame, meta


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, names: list[str]) -> dict[str, Any]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    per_target: dict[str, dict[str, float]] = {}
    for i, name in enumerate(names):
        yt = y_true[:, i] if y_true.ndim == 2 else y_true
        yp = y_pred[:, i] if y_pred.ndim == 2 else y_pred
        if y_true.ndim == 2:
            yt, yp = y_true[:, i], y_pred[:, i]
        mask = np.isfinite(yt) & np.isfinite(yp)
        if mask.sum() < 2:
            per_target[name] = {"rmse": float("nan"), "mae": float("nan"), "r2": float("nan"), "n": int(mask.sum())}
            continue
        yt_m, yp_m = yt[mask], yp[mask]
        per_target[name] = {
            "rmse": float(np.sqrt(mean_squared_error(yt_m, yp_m))),
            "mae": float(mean_absolute_error(yt_m, yp_m)),
            "r2": float(r2_score(yt_m, yp_m)),
            "n": int(mask.sum()),
        }

    def _avg(key: str) -> float:
        vals = [v[key] for v in per_target.values() if np.isfinite(v[key])]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "per_target": per_target,
        "mean_rmse": _avg("rmse"),
        "mean_mae": _avg("mae"),
        "mean_r2": _avg("r2"),
    }


def get_config_payload() -> dict[str, Any]:
    """Config UI Model Build (hyperparams + dernier modèle)."""
    try:
        frame, meta = _load_model_frame()
        n_rows = len(frame)
    except Exception as exc:
        return {
            "error": str(exc),
            "xgb_params": DEFAULT_XGB_PARAMS,
            "param_schema": PARAM_SCHEMA,
            "model_name": "xgb_sales",
            "models": list_design_models(),
        }

    last = get_last_trained()
    params = DEFAULT_XGB_PARAMS
    model_name = "xgb_sales"
    if last and last.get("xgb_params"):
        params = {**DEFAULT_XGB_PARAMS, **last["xgb_params"]}
        model_name = last.get("name") or last.get("id") or model_name

    return {
        "source": "model_data",
        "n_rows": n_rows,
        "n_train": meta.get("n_train"),
        "n_eval": meta.get("n_eval"),
        "eval_year": meta.get("eval_year"),
        "n_features": meta.get("n_descriptive"),
        "n_targets": meta.get("n_target"),
        "feature_cols": meta.get("descriptive_columns") or [],
        "target_cols": meta.get("target_columns") or [],
        "main_target": meta.get("main_target") or MAIN_TARGET,
        "xgb_params": params,
        "param_schema": PARAM_SCHEMA,
        "model_name": model_name,
        "last_trained": last,
        "models": list_design_models(),
        "design_dir": str(DESIGN_DIR),
        "deploy_dir": str(DEPLOY_DIR),
        "rank_metrics": [
            {"id": "r2", "label": "R2 (plus eleve = mieux)"},
            {"id": "rmse", "label": "RMSE (plus bas = mieux)"},
            {"id": "mae", "label": "MAE (plus bas = mieux)"},
        ],
        "default_rank_metric": "r2",
        "default_grid_search": {
            "n_estimators": [100, 200],
            "max_depth": [4, 6],
            "learning_rate": [0.05, 0.1],
        },
    }


def list_design_models() -> list[dict[str, Any]]:
    """Liste les modèles design, triés par perf (R² montant_ventes eval, puis mean_r2)."""
    DESIGN_DIR.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for conf_path in DESIGN_DIR.glob("*/config.json"):
        try:
            meta = json.loads(conf_path.read_text(encoding="utf-8"))
            meta["id"] = conf_path.parent.name
            meta["name"] = meta.get("name") or conf_path.parent.name
            meta["path"] = str(conf_path.parent)
            out.append(meta)
        except Exception:
            continue

    def score(m: dict[str, Any]) -> float:
        mt = m.get("metrics_eval") or m.get("metrics_test") or {}
        per = (mt.get("per_target") or {})
        main = m.get("main_target") or MAIN_TARGET
        if main in per and per[main].get("r2") is not None:
            try:
                return float(per[main]["r2"])
            except (TypeError, ValueError):
                pass
        try:
            return float(mt.get("mean_r2") or float("-inf"))
        except (TypeError, ValueError):
            return float("-inf")

    out.sort(key=score, reverse=True)
    for i, m in enumerate(out):
        m["rank"] = i + 1
        m["score_r2"] = score(m)
    return out


def get_last_trained() -> dict[str, Any] | None:
    if LAST_TRAINED_FILE.exists():
        try:
            info = json.loads(LAST_TRAINED_FILE.read_text(encoding="utf-8"))
            name = info.get("name") or info.get("id")
            if name:
                conf = DESIGN_DIR / name / "config.json"
                if conf.exists():
                    meta = json.loads(conf.read_text(encoding="utf-8"))
                    meta["id"] = name
                    meta["name"] = name
                    return meta
            return info
        except Exception:
            pass
    models = list_design_models()
    if not models:
        return None
    # plus récent par created_at
    models_by_date = sorted(
        models, key=lambda m: m.get("created_at") or "", reverse=True
    )
    return models_by_date[0]


def get_top_model() -> dict[str, Any] | None:
    models = list_design_models()
    return models[0] if models else None


def _coerce_params(xgb_params: dict[str, Any] | None) -> dict[str, Any]:
    params = {**DEFAULT_XGB_PARAMS}
    if not xgb_params:
        return params
    for k, v in xgb_params.items():
        if k not in DEFAULT_XGB_PARAMS:
            continue
        if isinstance(DEFAULT_XGB_PARAMS[k], int) and not isinstance(
            DEFAULT_XGB_PARAMS[k], bool
        ):
            params[k] = int(v)
        elif isinstance(DEFAULT_XGB_PARAMS[k], float):
            params[k] = float(v)
        else:
            params[k] = v
    return params


def expand_grid_search(
    grid: dict[str, list[Any]] | None,
    *,
    base_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Produit la liste des jeux de parametres XGBoost pour une grid search.

    grid: { "max_depth": [4, 6], "n_estimators": [100, 200] }
    Les cles absentes gardent la valeur de base_params / DEFAULT.
    """
    base = _coerce_params(base_params)
    if not grid:
        return []
    clean: dict[str, list[Any]] = {}
    for k, vals in grid.items():
        if k not in DEFAULT_XGB_PARAMS:
            continue
        if vals is None:
            continue
        if not isinstance(vals, (list, tuple)):
            vals = [vals]
        parsed: list[Any] = []
        for v in vals:
            if v is None or v == "":
                continue
            try:
                if isinstance(DEFAULT_XGB_PARAMS[k], int) and not isinstance(
                    DEFAULT_XGB_PARAMS[k], bool
                ):
                    parsed.append(int(v))
                elif isinstance(DEFAULT_XGB_PARAMS[k], float):
                    parsed.append(float(v))
                else:
                    parsed.append(v)
            except (TypeError, ValueError):
                continue
        # dedupe preserve order
        seen: set[Any] = set()
        uniq: list[Any] = []
        for v in parsed:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        if uniq:
            clean[k] = uniq
    if not clean:
        return []
    keys = sorted(clean.keys())
    combos: list[dict[str, Any]] = []
    for values in itertools.product(*(clean[k] for k in keys)):
        p = dict(base)
        for k, v in zip(keys, values):
            p[k] = v
        combos.append(p)
    return combos


def _score_result(
    result: dict[str, Any],
    *,
    main_target: str,
    rank_metric: str,
) -> float:
    """Score pour trier les modeles (plus grand = mieux pour r2, inverse pour rmse/mae)."""
    mt = result.get("metrics_eval") or result.get("metrics_test") or {}
    per = mt.get("per_target") or {}
    metric = (rank_metric or "r2").lower().strip()
    if metric not in ("r2", "rmse", "mae"):
        metric = "r2"
    val = None
    if main_target in per and per[main_target].get(metric) is not None:
        try:
            val = float(per[main_target][metric])
        except (TypeError, ValueError):
            val = None
    if val is None:
        key = f"mean_{metric}"
        try:
            val = float(mt.get(key))
        except (TypeError, ValueError):
            val = float("nan")
    if not np.isfinite(val):
        return float("-inf")
    # r2: higher better; rmse/mae: lower better -> negate
    if metric in ("rmse", "mae"):
        return -val
    return val


def get_build_progress() -> dict[str, Any]:
    """Etat du build batch (manuel + grid) pour la barre de progression."""
    return _BUILD_PROGRESS.snapshot()


def _fit_xgb_multioutput(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    params: dict[str, Any],
    target_cols: list[str],
    progress_hook: Any | None = None,
):
    """
    Fit un regresseur multi-cibles avec progression fine.

    Enchaîne un XGBRegressor par cible (équivalent MultiOutputRegressor
    n_jobs=1) et appelle ``progress_hook(frac, message, target_name)``
    pendant l'entraînement (cibles + arbres).
    """
    from sklearn.multioutput import MultiOutputRegressor
    from xgboost import XGBRegressor

    n_targets = int(y_train.shape[1]) if y_train.ndim > 1 else 1
    n_estimators = max(1, int(params.get("n_estimators") or 100))

    def _report(frac: float, msg: str, target: str = "") -> None:
        if progress_hook is None:
            return
        try:
            progress_hook(min(max(float(frac), 0.0), 1.0), msg, target)
        except Exception:
            pass

    # ---- une seule cible ----
    if n_targets == 1:
        y = y_train.ravel() if y_train.ndim > 1 else y_train
        tname = target_cols[0] if target_cols else "y"

        def _tree_cb(epoch: int) -> None:
            # epoch 0-based ; fraction dans [0, 1]
            _report((epoch + 1) / n_estimators, f"{tname} · arbre {epoch + 1}/{n_estimators}", tname)

        est = _make_xgb_regressor(params, on_iteration=_tree_cb)
        _report(0.0, f"Entrainement {tname}…", tname)
        est.fit(X_train, y)
        _report(1.0, f"{tname} termine", tname)
        return est

    # ---- multi-output : un estimateur par cible ----
    base = XGBRegressor(**{k: v for k, v in params.items() if k != "callbacks"})
    model = MultiOutputRegressor(base, n_jobs=1)
    estimators = []
    for i, tname in enumerate(target_cols):
        tname = str(tname)

        def _tree_cb(epoch: int, _i=i, _t=tname) -> None:
            frac = (_i + (epoch + 1) / n_estimators) / n_targets
            _report(frac, f"Cible {_i + 1}/{n_targets} · {_t} · arbre {epoch + 1}/{n_estimators}", _t)

        est = _make_xgb_regressor(params, on_iteration=_tree_cb)
        _report(i / n_targets, f"Cible {i + 1}/{n_targets} · {tname}", tname)
        est.fit(X_train, y_train[:, i])
        estimators.append(est)
        _report((i + 1) / n_targets, f"Cible {i + 1}/{n_targets} · {tname} ok", tname)

    model.estimators_ = estimators
    try:
        model.n_features_in_ = X_train.shape[1]
    except Exception:
        pass
    return model


def _make_xgb_regressor(params: dict[str, Any], *, on_iteration: Any | None = None):
    """XGBRegressor + callback d'iteration optionnel (progression arbres)."""
    from xgboost import XGBRegressor

    p = dict(params)
    p.pop("callbacks", None)
    if on_iteration is None:
        return XGBRegressor(**p)

    try:
        from xgboost.callback import TrainingCallback

        class _IterCB(TrainingCallback):
            def after_iteration(self, model, epoch, evals_log):  # noqa: ANN001
                try:
                    on_iteration(int(epoch))
                except Exception:
                    pass
                return False

        return XGBRegressor(**p, callbacks=[_IterCB()])
    except Exception:
        # versions xgboost sans callbacks sklearn : pas de progression arbres
        return XGBRegressor(**p)


def train_model(
    *,
    xgb_params: dict[str, Any] | None = None,
    model_name: str | None = None,
    save: bool = False,
    main_target: str | None = None,
    rebuild_data: bool = True,
    frame: pd.DataFrame | None = None,
    meta: dict[str, Any] | None = None,
    progress_hook: Any | None = None,
) -> dict[str, Any]:
    """
    Entraîne sur model_data.

    Si ``save=True``, écrit immédiatement dans design/<name>/.
    ``rebuild_data=False`` + frame/meta : reutilise les donnees (batch grid).
    ``progress_hook(frac, message, target_name)`` : 0–1 pendant le fit.
    """
    try:
        from sklearn.multioutput import MultiOutputRegressor
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise ImportError(
            "xgboost et scikit-learn sont requis : pip install xgboost scikit-learn"
        ) from exc

    if rebuild_data or frame is None or meta is None:
        if progress_hook:
            try:
                progress_hook(0.0, "Reconstruction model_data…", "")
            except Exception:
                pass
        rebuild_model_data()
        frame, meta = _load_model_frame()

    feature_cols = [c for c in (meta.get("descriptive_columns") or []) if c in frame.columns]
    target_cols = [c for c in (meta.get("target_columns") or []) if c in frame.columns]
    main_t = (main_target or meta.get("main_target") or MAIN_TARGET).strip()
    if main_t not in target_cols:
        if MAIN_TARGET in target_cols:
            main_t = MAIN_TARGET
        elif target_cols:
            main_t = target_cols[0]
    main_target = main_t

    if not feature_cols:
        raise ValueError("Aucune feature descriptive dans model_data.")
    if not target_cols:
        raise ValueError("Aucune cible dans model_data.")

    # Split eval
    if "_is_eval" in frame.columns:
        is_eval = frame["_is_eval"].astype(int) == 1
    elif "annee" in frame.columns and meta.get("eval_year") is not None:
        is_eval = pd.to_numeric(frame["annee"], errors="coerce") == int(meta["eval_year"])
    else:
        is_eval = pd.Series(False, index=frame.index)
        # fallback 20% last rows
        n = len(frame)
        is_eval.iloc[int(n * 0.8) :] = True

    work = frame.copy()
    for c in feature_cols + target_cols:
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)

    train_df = work.loc[~is_eval]
    eval_df = work.loc[is_eval]
    if len(train_df) < 5:
        raise ValueError(f"Trop peu de lignes d'apprentissage ({len(train_df)}).")
    if len(eval_df) < 1:
        raise ValueError("Aucune ligne d'évaluation (dernière année).")

    X_train = train_df[feature_cols].to_numpy(dtype=float)
    y_train = train_df[target_cols].to_numpy(dtype=float)
    X_eval = eval_df[feature_cols].to_numpy(dtype=float)
    y_eval = eval_df[target_cols].to_numpy(dtype=float)

    params = _coerce_params(xgb_params)

    model = _fit_xgb_multioutput(
        X_train,
        y_train,
        params=params,
        target_cols=target_cols,
        progress_hook=progress_hook,
    )
    y_pred_train = model.predict(X_train)
    y_pred_eval = model.predict(X_eval)
    if y_pred_train.ndim == 1:
        y_pred_train = y_pred_train.reshape(-1, 1)
        y_pred_eval = y_pred_eval.reshape(-1, 1)
    y_train_m, y_eval_m = y_train, y_eval
    if y_train_m.ndim == 1:
        y_train_m = y_train_m.reshape(-1, 1)
        y_eval_m = y_eval_m.reshape(-1, 1)

    metrics_train = _metrics(y_train_m, y_pred_train, target_cols)
    metrics_eval = _metrics(y_eval_m, y_pred_eval, target_cols)

    importance: dict[str, float] = {}
    try:
        if isinstance(model, MultiOutputRegressor):
            imps = [est.feature_importances_ for est in model.estimators_ if hasattr(est, "feature_importances_")]
            if imps:
                mean_imp = np.mean(np.vstack(imps), axis=0)
                importance = {feature_cols[i]: float(mean_imp[i]) for i in range(len(feature_cols))}
        elif hasattr(model, "feature_importances_"):
            importance = {
                feature_cols[i]: float(model.feature_importances_[i]) for i in range(len(feature_cols))
            }
    except Exception:
        importance = {}
    top_imp = sorted(importance.items(), key=lambda x: -x[1])[:40]

    name = _slug(model_name or "xgb_sales")
    bundle = {
        "model": model,
        "feature_cols": feature_cols,
        "target_cols": target_cols,
        "params": params,
        "main_target": main_target,
    }

    config = {
        "name": name,
        "id": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "model_data",
        "eval_year": meta.get("eval_year"),
        "n_rows_used": int(len(work)),
        "n_train": int(len(train_df)),
        "n_eval": int(len(eval_df)),
        "feature_cols": feature_cols,
        "n_features": len(feature_cols),
        "target_cols": target_cols,
        "n_targets": len(target_cols),
        "main_target": main_target,
        "xgb_params": params,
        "metrics_train": metrics_train,
        "metrics_eval": metrics_eval,
        # alias for explore compatibility
        "metrics_test": metrics_eval,
        "top_feature_importance": [{"feature": k, "importance": v} for k, v in top_imp],
        "feature_importance": importance,
        "model_file": "model.pkl",
        "config_file": "config.json",
    }

    result = {
        "ok": True,
        "id": name,
        "name": name,
        "bundle": bundle,
        "config": config,
        "metrics_train": metrics_train,
        "metrics_eval": metrics_eval,
        "metrics_test": metrics_eval,
        "n_train": int(len(train_df)),
        "n_eval": int(len(eval_df)),
        "n_features": len(feature_cols),
        "n_targets": len(target_cols),
        "feature_cols": feature_cols,
        "target_cols": target_cols,
        "main_target": main_target,
        "top_feature_importance": config["top_feature_importance"],
        "xgb_params": params,
        "saved": False,
    }

    if save:
        saved = save_design_model(name, bundle, config)
        result.update(saved)
        result["saved"] = True

    # remember last trained (in memory file even if not saved? save always on build per user)
    return result


def save_design_model(
    name: str,
    bundle: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Écrit / écrase ``models/design/<name>/``."""
    name = _slug(name)
    DESIGN_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = DESIGN_DIR / name
    # écrase
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = out_dir / "model.pkl"
    with model_path.open("wb") as f:
        pickle.dump(bundle, f)

    config = {**config, "name": name, "id": name, "path": str(out_dir)}
    conf_path = out_dir / "config.json"
    conf_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    LAST_TRAINED_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_TRAINED_FILE.write_text(
        json.dumps({"name": name, "id": name, "created_at": config.get("created_at")}, indent=2),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "id": name,
        "name": name,
        "path": str(out_dir),
        "model_file": str(model_path),
        "config_file": str(conf_path),
    }


def build_and_save(
    *,
    xgb_params: dict[str, Any] | None = None,
    model_name: str | None = None,
    main_target: str | None = None,
) -> dict[str, Any]:
    """Build simple = un seul jeu de parametres + sauvegarde design."""
    result = train_model(
        xgb_params=xgb_params,
        model_name=model_name,
        save=True,
        main_target=main_target,
        rebuild_data=True,
    )
    result.pop("bundle", None)
    return result


def _run_build_batch(
    *,
    model_name: str,
    xgb_params: dict[str, Any],
    grid_search: dict[str, list[Any]] | None,
    main_target: str,
    rank_metric: str,
) -> None:
    """Thread worker: modele manuel + toutes les combinaisons grid search."""
    progress = _BUILD_PROGRESS
    try:
        planner = GridSearchPlanner(
            base_name=model_name or "xgb_sales",
            manual_params=xgb_params or {},
            grid=grid_search,
        )
        jobs = planner.jobs()
        progress.update(
            status="running",
            phase="prepare",
            done=0,
            total=len(jobs),
            job_fraction=0.0,
            current_name="",
            current_target="",
            message="Preparation model_data…",
            results=[],
            error=None,
            rank_metric=rank_metric,
            main_target=main_target,
        )

        rebuild_model_data()
        frame, meta = _load_model_frame()
        target_cols = meta.get("target_columns") or []
        main_t = (main_target or meta.get("main_target") or MAIN_TARGET).strip()
        if main_t not in target_cols:
            main_t = MAIN_TARGET if MAIN_TARGET in target_cols else (
                target_cols[0] if target_cols else MAIN_TARGET
            )
        metric = (rank_metric or "r2").lower().strip()
        if metric not in ("r2", "rmse", "mae"):
            metric = "r2"

        results: list[dict[str, Any]] = []
        n_jobs = len(jobs)
        for idx, (name, kind, params) in enumerate(jobs):
            progress.update(
                phase="train",
                done=idx,
                total=n_jobs,
                job_fraction=0.0,
                current_name=name,
                current_target="",
                message=f"Modele {idx + 1}/{n_jobs} · {name}",
            )

            def _hook(frac: float, msg: str, target: str = "", _idx=idx, _name=name) -> None:
                progress.update(
                    phase="train",
                    done=_idx,
                    job_fraction=float(frac),
                    current_name=_name,
                    current_target=target or "",
                    message=f"Modele {_idx + 1}/{n_jobs} · {_name} — {msg}",
                )

            try:
                res = train_model(
                    xgb_params=params,
                    model_name=name,
                    save=True,
                    main_target=main_t,
                    rebuild_data=False,
                    frame=frame,
                    meta=meta,
                    progress_hook=_hook,
                )
                res.pop("bundle", None)
                res["kind"] = kind
                res["rank_metric"] = metric
                res["ok"] = True
                mt = res.get("metrics_eval") or {}
                per = (mt.get("per_target") or {}).get(main_t) or {}
                if metric in per and per[metric] is not None:
                    res["metric_value"] = float(per[metric])
                else:
                    res["metric_value"] = mt.get(f"mean_{metric}")
                res["score"] = _score_result(
                    res, main_target=main_t, rank_metric=metric
                )
            except Exception as exc:
                res = {
                    "ok": False,
                    "name": name,
                    "id": name,
                    "kind": kind,
                    "error": str(exc),
                    "xgb_params": params,
                    "main_target": main_t,
                    "rank_metric": metric,
                    "metric_value": None,
                    "score": float("-inf"),
                }
            results.append(res)
            progress.update(
                done=idx + 1,
                job_fraction=0.0,
                current_target="",
                results=list(results),
                message=f"Modele {idx + 1}/{n_jobs} termine · {name}",
            )

        ranked = sorted(
            results, key=lambda r: float(r.get("score") or float("-inf")), reverse=True
        )
        for i, r in enumerate(ranked):
            r["rank"] = i + 1

        progress.update(
            status="done",
            phase="done",
            done=len(jobs),
            total=len(jobs),
            job_fraction=0.0,
            pct=100.0,
            current_name="",
            current_target="",
            message=f"Termine · {len(jobs)} modele(s)",
            results=ranked,
            main_target=main_t,
            rank_metric=metric,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        progress.update(
            status="error",
            phase="error",
            error=str(exc),
            message=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def start_build_batch(
    *,
    model_name: str | None = None,
    xgb_params: dict[str, Any] | None = None,
    grid_search: dict[str, list[Any]] | None = None,
    main_target: str | None = None,
    rank_metric: str = "r2",
) -> dict[str, Any]:
    """
    Lance en arriere-plan le build manuel + grid search.
    Suivre via get_build_progress().
    """
    global _build_thread
    if _BUILD_PROGRESS.is_running():
        return {
            "ok": False,
            "error": "Un build est deja en cours",
            "progress": _BUILD_PROGRESS.snapshot(),
        }

    planner = GridSearchPlanner(
        base_name=model_name or "xgb_sales",
        manual_params=xgb_params or {},
        grid=grid_search,
    )
    counts = planner.counts()
    main_t = main_target or MAIN_TARGET
    metric = (rank_metric or "r2").lower()
    _BUILD_PROGRESS.reset_running(
        total=counts["total"],
        main_target=main_t,
        rank_metric=metric,
    )

    t = threading.Thread(
        target=_run_build_batch,
        kwargs={
            "model_name": model_name or "xgb_sales",
            "xgb_params": xgb_params or {},
            "grid_search": grid_search,
            "main_target": main_t,
            "rank_metric": metric,
        },
        daemon=True,
    )
    _build_thread = t
    t.start()
    return {
        "ok": True,
        "status": "running",
        "total": counts["total"],
        "message": "Build lance",
    }


def count_grid_jobs(
    xgb_params: dict[str, Any] | None,
    grid_search: dict[str, list[Any]] | None,
) -> dict[str, Any]:
    """Nombre de modeles qui seront construits (manuel + grid uniques)."""
    return GridSearchPlanner(
        base_name="xgb",
        manual_params=xgb_params or {},
        grid=grid_search,
    ).counts()


def deploy_model(model_name: str | None = None) -> dict[str, Any]:
    """
    Copie le modèle design vers ``models/deploy/model.pkl`` + ``model.json``.
    Un seul modèle déployé à la fois.
    """
    name = _slug(model_name or "")
    if not name or name == "xgb_sales" and model_name is None:
        top = get_top_model() or get_last_trained()
        if not top:
            raise FileNotFoundError("Aucun modèle à déployer.")
        name = _slug(top.get("name") or top.get("id") or "")

    src_dir = DESIGN_DIR / name
    if not src_dir.exists():
        raise FileNotFoundError(f"Modèle design introuvable : {name}")

    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    # purge deploy
    for p in DEPLOY_DIR.iterdir():
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)

    src_model = src_dir / "model.pkl"
    src_conf = src_dir / "config.json"
    if not src_model.exists():
        raise FileNotFoundError(f"model.pkl manquant pour {name}")

    dst_model = DEPLOY_DIR / "model.pkl"
    dst_conf = DEPLOY_DIR / "model.json"
    shutil.copy2(src_model, dst_model)
    if src_conf.exists():
        conf = json.loads(src_conf.read_text(encoding="utf-8"))
        conf["deployed_at"] = datetime.now(timezone.utc).isoformat()
        conf["deployed_from"] = name
        dst_conf.write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        dst_conf.write_text(json.dumps({"name": name, "deployed_from": name}, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "deployed_from": name,
        "model_file": str(dst_model),
        "config_file": str(dst_conf),
    }


def load_design_model(model_id: str) -> dict[str, Any]:
    path = DESIGN_DIR / _slug(model_id) / "model.pkl"
    conf_path = DESIGN_DIR / _slug(model_id) / "config.json"
    if not path.exists():
        raise FileNotFoundError(f"Modèle introuvable : {model_id}")
    with path.open("rb") as f:
        bundle = pickle.load(f)
    meta = {}
    if conf_path.exists():
        meta = json.loads(conf_path.read_text(encoding="utf-8"))
    return {"bundle": bundle, "meta": meta}


# Compat aliases
def list_models() -> list[dict[str, Any]]:
    return list_design_models()


def load_model(model_id: str) -> dict[str, Any]:
    return load_design_model(model_id)
