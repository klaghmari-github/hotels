"""
Entraînement XGBoost pour prédiction des ventes mensuelles.

Inputs (features)
-----------------
- Mix F&B / N_F_B : ``pct_categories_mois_*``, ``pct_cat_*``
- Mix sous-catégories dans leur catégorie : ``pct_sous_cat_*``
- Contexte optionnel : mois, année, fériés / vacances, météo, fiche hôtel

Targets (à prédire)
-------------------
Volumes mensuels : ``nombre_ventes``, ``montant_ventes``, et plus si demandé
(``nombre_paniers``, ``nombre_produits``, volumes ``cat_*`` / ``sous_cat_*``).

Le bouton **Build** de l'UI appelle :func:`train_model` qui :
1. charge ``data/all_data.xlsx`` (All Data) ou ``hotel_sales_data.xlsx``
2. construit X / y
3. entraîne un multi-output XGBoost
4. sauvegarde le modèle + meta dans ``models/``
"""

from __future__ import annotations

import json
import pickle
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"

# Hyperparamètres XGBoost exposés dans l'UI (valeurs par défaut sensées)
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

# Schéma des paramètres pour le formulaire (type + bornes)
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

# Cibles par défaut (volumes mensuels)
DEFAULT_TARGETS = [
    "nombre_ventes",
    "montant_ventes",
    "nombre_paniers",
    "nombre_produits",
]

# Groupes de features (toggles UI)
FEATURE_GROUPS = {
    "pct_mix": {
        "label": "Mix F&B / N_F_B (%)",
        "description": "pct_categories_mois_* et pct_cat_*",
        "default": True,
    },
    "pct_sous_cat": {
        "label": "Mix sous-catégories (%)",
        "description": "pct_sous_cat_* (part dans sa catégorie)",
        "default": True,
    },
    "calendar": {
        "label": "Calendrier",
        "description": "mois, année, fériés / vacances",
        "default": True,
    },
    "weather": {
        "label": "Météo",
        "description": "colonnes meteo_*",
        "default": True,
    },
    "hotel": {
        "label": "Fiche hôtel",
        "description": "nb chambres, TO, équipements…",
        "default": False,
    },
}


def _load_frame(source: str = "data") -> pd.DataFrame:
    """Charge All Data (all_data.xlsx) ou hotel_sales_data.xlsx."""
    if source == "sales":
        path = DATA_DIR / "hotel_sales_data.xlsx"
        sheet = "hotel_sales"
    else:
        path = DATA_DIR / "all_data.xlsx"
        if not path.exists():
            legacy = DATA_DIR / "data.xlsx"
            path = legacy if legacy.exists() else path
        sheet = "all_data"
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    try:
        return pd.read_excel(path, sheet_name=sheet)
    except ValueError:
        # Ancien nom de feuille « data » ou première feuille
        try:
            return pd.read_excel(path, sheet_name="data")
        except ValueError:
            return pd.read_excel(path, sheet_name=0)


def _is_numeric_series(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s)


def discover_columns(frame: pd.DataFrame) -> dict[str, list[str]]:
    """Classe les colonnes en groupes feature / target pour l'UI."""
    cols = list(frame.columns)

    pct_mix = [
        c
        for c in cols
        if c.startswith("pct_categories_")
        or re.match(r"^pct_cat_", c)
    ]
    pct_sous = [c for c in cols if c.startswith("pct_sous_cat_")]
    calendar = [
        c
        for c in (
            "annee",
            "mois",
            "nb_jours_feries",
            "nb_jours_vacances_scolaires",
            "nb_jours_vacances_hors_feries",
            "nb_jours_dans_mois",
        )
        if c in frame.columns
    ]
    weather = [c for c in cols if c.startswith("meteo_") and _is_numeric_series(frame[c])]
    hotel = [
        c
        for c in cols
        if c.startswith("hotel_")
        and c not in {"hotel_code", "hotel_name", "hotel_brand", "hotel_city", "hotel_adresse_postale_1", "hotel_adresse_postale_2", "hotel_geo_source"}
        and _is_numeric_series(frame[c])
    ]

    # Targets = volumes (pas les pct, pas les meta)
    volume_prefixes = ("nombre_ventes", "montant_ventes", "nombre_paniers", "nombre_produits")
    targets: list[str] = []
    for c in cols:
        if c in volume_prefixes:
            targets.append(c)
            continue
        if c.startswith(("cat_", "sous_cat_", "heure_", "weekend_")) and any(
            c.endswith(m) for m in volume_prefixes
        ):
            targets.append(c)

    return {
        "pct_mix": sorted(pct_mix),
        "pct_sous_cat": sorted(pct_sous),
        "calendar": calendar,
        "weather": sorted(weather),
        "hotel": sorted(hotel),
        "targets": targets,
        "default_targets": [t for t in DEFAULT_TARGETS if t in frame.columns],
    }


def _select_features(
    frame: pd.DataFrame,
    groups: dict[str, bool],
    extra_features: list[str] | None = None,
) -> list[str]:
    discovered = discover_columns(frame)
    selected: list[str] = []
    for gname, enabled in groups.items():
        if not enabled:
            continue
        selected.extend(discovered.get(gname, []))
    if extra_features:
        for c in extra_features:
            if c in frame.columns and c not in selected:
                selected.append(c)
    # Dédup en gardant l'ordre
    seen: set[str] = set()
    out: list[str] = []
    for c in selected:
        if c not in seen and c in frame.columns and _is_numeric_series(frame[c]):
            seen.add(c)
            out.append(c)
    return out


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, names: list[str]) -> dict[str, Any]:
    """RMSE / MAE / R² par target + moyenne."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    per_target: dict[str, dict[str, float]] = {}
    for i, name in enumerate(names):
        yt = y_true[:, i]
        yp = y_pred[:, i]
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
    # Moyenne simple des métriques finies
    def _avg(key: str) -> float:
        vals = [v[key] for v in per_target.values() if np.isfinite(v[key])]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "per_target": per_target,
        "mean_rmse": _avg("rmse"),
        "mean_mae": _avg("mae"),
        "mean_r2": _avg("r2"),
    }


def get_config_payload(source: str = "data") -> dict[str, Any]:
    """Payload pour l'écran de configuration du modèle."""
    frame = _load_frame(source)
    discovered = discover_columns(frame)
    models = list_models()
    return {
        "source": source,
        "n_rows": len(frame),
        "n_columns": len(frame.columns),
        "feature_groups": {
            k: {
                **v,
                "columns": discovered.get(k, []),
                "n_columns": len(discovered.get(k, [])),
            }
            for k, v in FEATURE_GROUPS.items()
        },
        "targets": discovered["targets"],
        "default_targets": discovered["default_targets"],
        "xgb_params": DEFAULT_XGB_PARAMS,
        "param_schema": PARAM_SCHEMA,
        "test_size": 0.2,
        "models": models,
        "models_dir": str(MODELS_DIR),
    }


def list_models() -> list[dict[str, Any]]:
    """Liste les modèles sauvegardés (meta.json)."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for meta_path in sorted(MODELS_DIR.glob("*/meta.json"), reverse=True):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["id"] = meta_path.parent.name
            meta["path"] = str(meta_path.parent)
            out.append(meta)
        except Exception:
            continue
    return out


def train_model(
    *,
    source: str = "data",
    feature_groups: dict[str, bool] | None = None,
    targets: list[str] | None = None,
    xgb_params: dict[str, Any] | None = None,
    test_size: float = 0.2,
    model_name: str | None = None,
) -> dict[str, Any]:
    """
    Entraîne un multi-output XGBoost et sauvegarde sous ``models/<id>/``.

    Returns
    -------
    dict avec metrics, chemins, features, targets, params.
    """
    try:
        from sklearn.model_selection import train_test_split
        from sklearn.multioutput import MultiOutputRegressor
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise ImportError(
            "xgboost et scikit-learn sont requis : pip install xgboost scikit-learn"
        ) from exc

    frame = _load_frame(source)
    groups = {k: v["default"] for k, v in FEATURE_GROUPS.items()}
    if feature_groups:
        groups.update({k: bool(v) for k, v in feature_groups.items() if k in groups})

    feature_cols = _select_features(frame, groups)
    target_cols = targets or [t for t in DEFAULT_TARGETS if t in frame.columns]
    target_cols = [t for t in target_cols if t in frame.columns]
    # Ne pas prédire une feature avec elle-même
    target_cols = [t for t in target_cols if t not in feature_cols]

    if not feature_cols:
        raise ValueError("Aucune feature sélectionnée (activez au moins un groupe).")
    if not target_cols:
        raise ValueError("Aucune cible valide.")

    work = frame[feature_cols + target_cols].copy()
    for c in feature_cols + target_cols:
        work[c] = pd.to_numeric(work[c], errors="coerce")
    # Lignes avec au moins une cible renseignée
    work = work.dropna(subset=target_cols, how="all")
    # Impute features NaN par médiane (puis 0)
    for c in feature_cols:
        med = work[c].median()
        if pd.isna(med):
            med = 0.0
        work[c] = work[c].fillna(med)
    for c in target_cols:
        work[c] = work[c].fillna(0.0)

    if len(work) < 10:
        raise ValueError(f"Trop peu de lignes exploitables ({len(work)}).")

    X = work[feature_cols].to_numpy(dtype=float)
    y = work[target_cols].to_numpy(dtype=float)

    params = {**DEFAULT_XGB_PARAMS}
    if xgb_params:
        for k, v in xgb_params.items():
            if k in DEFAULT_XGB_PARAMS:
                if isinstance(DEFAULT_XGB_PARAMS[k], int) and not isinstance(
                    DEFAULT_XGB_PARAMS[k], bool
                ):
                    params[k] = int(v)
                elif isinstance(DEFAULT_XGB_PARAMS[k], float):
                    params[k] = float(v)
                else:
                    params[k] = v

    # Split temporel si année/mois dispo, sinon aléatoire
    strat = None
    if "annee" in frame.columns and len(work) == len(
        frame.loc[work.index] if work.index.equals(frame.index) else work
    ):
        pass  # index may differ after dropna
    ts = float(test_size)
    ts = min(max(ts, 0.05), 0.5)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=ts, random_state=int(params.get("random_state", 42))
    )

    base = XGBRegressor(**params)
    if y_train.ndim == 1 or y_train.shape[1] == 1:
        model = base
        if y_train.ndim == 2:
            y_train = y_train.ravel()
            y_test = y_test.ravel()
        model.fit(X_train, y_train)
        y_pred_train = model.predict(X_train).reshape(-1, 1)
        y_pred_test = model.predict(X_test).reshape(-1, 1)
        y_train_m = y_train.reshape(-1, 1)
        y_test_m = y_test.reshape(-1, 1)
    else:
        model = MultiOutputRegressor(base, n_jobs=1)
        model.fit(X_train, y_train)
        y_pred_train = model.predict(X_train)
        y_pred_test = model.predict(X_test)
        y_train_m = y_train
        y_test_m = y_test

    metrics_train = _metrics(y_train_m, y_pred_train, target_cols)
    metrics_test = _metrics(y_test_m, y_pred_test, target_cols)

    # Feature importance (moyenne sur multi-output)
    importance: dict[str, float] = {}
    try:
        if isinstance(model, MultiOutputRegressor):
            imps = []
            for est in model.estimators_:
                if hasattr(est, "feature_importances_"):
                    imps.append(est.feature_importances_)
            if imps:
                mean_imp = np.mean(np.vstack(imps), axis=0)
                importance = {
                    feature_cols[i]: float(mean_imp[i])
                    for i in range(len(feature_cols))
                }
        elif hasattr(model, "feature_importances_"):
            importance = {
                feature_cols[i]: float(model.feature_importances_[i])
                for i in range(len(feature_cols))
            }
    except Exception:
        importance = {}

    # Top-20 importances
    top_imp = sorted(importance.items(), key=lambda x: -x[1])[:20]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", (model_name or "xgb_sales").strip())[:40]
    model_id = f"{slug}_{stamp}"
    out_dir = MODELS_DIR / model_id
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = out_dir / "model.pkl"
    with model_path.open("wb") as f:
        pickle.dump(
            {
                "model": model,
                "feature_cols": feature_cols,
                "target_cols": target_cols,
                "params": params,
            },
            f,
        )

    meta = {
        "id": model_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "n_rows_used": int(len(work)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "test_size": ts,
        "feature_groups": groups,
        "feature_cols": feature_cols,
        "n_features": len(feature_cols),
        "target_cols": target_cols,
        "n_targets": len(target_cols),
        "xgb_params": params,
        "metrics_train": metrics_train,
        "metrics_test": metrics_test,
        "top_feature_importance": [{"feature": k, "importance": v} for k, v in top_imp],
        "model_file": str(model_path.name),
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "ok": True,
        "id": model_id,
        "path": str(out_dir),
        "model_file": str(model_path),
        "metrics_train": metrics_train,
        "metrics_test": metrics_test,
        "n_rows_used": int(len(work)),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "n_features": len(feature_cols),
        "n_targets": len(target_cols),
        "feature_cols": feature_cols,
        "target_cols": target_cols,
        "top_feature_importance": meta["top_feature_importance"],
        "xgb_params": params,
    }


def load_model(model_id: str) -> dict[str, Any]:
    """Charge un modèle sauvegardé."""
    model_path = MODELS_DIR / model_id / "model.pkl"
    meta_path = MODELS_DIR / model_id / "meta.json"
    if not model_path.exists():
        raise FileNotFoundError(f"Modèle introuvable : {model_id}")
    with model_path.open("rb") as f:
        bundle = pickle.load(f)
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {"bundle": bundle, "meta": meta}
