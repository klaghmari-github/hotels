"""
Exploration des modèles design pour l'onglet Model Explore.

Fonctions API
-------------
  explore_overview              méta, importances, perfs train/eval, n arbres
  trees_table                   une ligne par arbre (profondeur, n features,
                                R²/RMSE *cumulés* sur le jeu d'eval)
  get_tree                      dump XGBoost parsé en JSON pour le SVG
  feature_importance_payload    barres d'importance

Perf « par arbre »
-----------------
En boosting, l'arbre k prédit un correctif, pas la cible brute. On évalue
donc la prédiction cumulative après les k+1 premiers arbres
(booster.predict(..., iteration_range=(0, k+1))). C'est la seule métrique
lisible métier.

Lecture des modèles : models/design/<id>/ via model_train.load_design_model.
Pour l'eval année incomplete (moyenne /12), voir model_eval.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.multioutput import MultiOutputRegressor

from archive.accor_1_0_6.pipelines.src.accor.model_data import MAIN_TARGET
from archive.accor_1_0_6.pipelines.src.accor.model_train import (
    DESIGN_DIR,
    get_last_trained,
    get_top_model,
    list_design_models,
    load_design_model,
    _load_model_frame,
)


def _load_model_bundle(model_id: str, *, tier: str = "intermediate") -> dict[str, Any]:
    """Charge un modèle intermédiaire (design/) ou final (final/design/)."""
    if tier == "final":
        from archive.accor_1_0_6.pipelines.src.accor.model_final import load_final_model

        return load_final_model(model_id)
    return load_design_model(model_id)

_SPLIT_RE = re.compile(
    r"^(\d+):\[(f\d+|[^<\]]+)<([^\]]+)\]\s+yes=(\d+),no=(\d+),missing=(\d+)"
    r"(?:,gain=([^,]+))?(?:,cover=([^,\s]+))?"
)
_LEAF_RE = re.compile(r"^(\d+):leaf=([^\s,]+)(?:,cover=([^\s,]+))?")


def _get_estimators(bundle: dict[str, Any]) -> list[Any]:
    model = bundle["model"]
    if isinstance(model, MultiOutputRegressor):
        return list(model.estimators_)
    return [model]


def _feature_name(feature_cols: list[str], token: str) -> str:
    if token.startswith("f") and token[1:].isdigit():
        idx = int(token[1:])
        if 0 <= idx < len(feature_cols):
            return feature_cols[idx]
    return token


def parse_tree_dump(dump: str, feature_cols: list[str]) -> dict[str, Any]:
    nodes: dict[int, dict[str, Any]] = {}
    for raw in dump.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _LEAF_RE.match(line)
        if m:
            nid = int(m.group(1))
            nodes[nid] = {
                "id": nid,
                "is_leaf": True,
                "value": float(m.group(2)),
                "cover": float(m.group(3)) if m.group(3) else None,
                "label": f"leaf = {float(m.group(2)):.4g}",
            }
            continue
        m = _SPLIT_RE.match(line)
        if m:
            nid = int(m.group(1))
            feat = _feature_name(feature_cols, m.group(2))
            thr = float(m.group(3))
            nodes[nid] = {
                "id": nid,
                "is_leaf": False,
                "feature": feat,
                "threshold": thr,
                "yes": int(m.group(4)),
                "no": int(m.group(5)),
                "missing": int(m.group(6)),
                "gain": float(m.group(7)) if m.group(7) else None,
                "cover": float(m.group(8)) if m.group(8) else None,
                "label": f"{feat} < {thr:.4g}",
            }
    for nid, node in list(nodes.items()):
        if not node["is_leaf"]:
            node["left"] = nodes.get(node["yes"])
            node["right"] = nodes.get(node["no"])
    root = nodes.get(0) or {"id": 0, "is_leaf": True, "value": 0.0, "label": "empty"}
    return _strip(root)


def _strip(node: dict[str, Any] | None, depth: int = 0) -> dict[str, Any]:
    if node is None or depth > 64:
        return {"id": -1, "is_leaf": True, "value": 0.0, "label": "…"}
    if node.get("is_leaf"):
        return {
            "id": node["id"],
            "is_leaf": True,
            "value": node.get("value"),
            "cover": node.get("cover"),
            "label": node.get("label"),
        }
    return {
        "id": node["id"],
        "is_leaf": False,
        "feature": node.get("feature"),
        "threshold": node.get("threshold"),
        "gain": node.get("gain"),
        "cover": node.get("cover"),
        "label": node.get("label"),
        "left": _strip(node.get("left"), depth + 1),
        "right": _strip(node.get("right"), depth + 1),
    }


def _tree_depth(node: dict[str, Any] | None) -> int:
    if not node or node.get("is_leaf"):
        return 0
    return 1 + max(_tree_depth(node.get("left")), _tree_depth(node.get("right")))


def _tree_features(node: dict[str, Any] | None, acc: set[str] | None = None) -> set[str]:
    if acc is None:
        acc = set()
    if not node or node.get("is_leaf"):
        return acc
    if node.get("feature"):
        acc.add(str(node["feature"]))
    _tree_features(node.get("left"), acc)
    _tree_features(node.get("right"), acc)
    return acc


def _estimator_for_main(bundle: dict[str, Any], meta: dict[str, Any]) -> tuple[Any, int, str]:
    """Retourne (estimator, target_index, target_name) pour la cible principale."""
    target_cols = list(bundle.get("target_cols") or meta.get("target_cols") or [])
    main = meta.get("main_target") or bundle.get("main_target") or MAIN_TARGET
    estimators = _get_estimators(bundle)
    if main in target_cols:
        idx = target_cols.index(main)
    else:
        idx = 0
        main = target_cols[0] if target_cols else "target_0"
    idx = min(idx, len(estimators) - 1)
    return estimators[idx], idx, main


def explore_overview(model_id: str, *, tier: str = "intermediate") -> dict[str, Any]:
    loaded = _load_model_bundle(model_id, tier=tier)
    bundle = loaded["bundle"]
    meta = loaded["meta"]
    feature_cols = list(bundle.get("feature_cols") or meta.get("feature_cols") or [])
    target_cols = list(bundle.get("target_cols") or meta.get("target_cols") or [])
    est, t_idx, main = _estimator_for_main(bundle, meta)

    n_trees = 0
    try:
        n_trees = int(est.get_booster().num_boosted_rounds())
    except Exception:
        n_trees = int(getattr(est, "n_estimators", 0) or 0)

    imp = meta.get("top_feature_importance") or []
    if not imp and hasattr(est, "feature_importances_"):
        pairs = [
            {"feature": feature_cols[i], "importance": float(est.feature_importances_[i])}
            for i in range(min(len(feature_cols), len(est.feature_importances_)))
        ]
        pairs.sort(key=lambda x: -x["importance"])
        imp = pairs[:40]

    metrics_eval = meta.get("metrics_eval") or meta.get("metrics_test") or {}
    main_metrics = (metrics_eval.get("per_target") or {}).get(main) or {}

    if tier == "final":
        from archive.accor_1_0_6.pipelines.src.accor.model_final import (
            get_final_last_trained,
            get_final_top_model,
            list_final_models,
        )

        models = list_final_models()
        last = get_final_last_trained()
        top = get_final_top_model()
    else:
        models = list_design_models()
        last = get_last_trained()
        top = get_top_model()
    rank = next(
        (m["rank"] for m in models if m.get("id") == model_id or m.get("name") == model_id),
        None,
    )

    return {
        "id": model_id,
        "name": meta.get("name") or model_id,
        "tier": tier,
        "rank": rank,
        "created_at": meta.get("created_at"),
        "n_features": len(feature_cols),
        "n_targets": len(target_cols),
        "feature_cols": feature_cols,
        "base_feature_cols": meta.get("base_feature_cols") or bundle.get("base_feature_cols"),
        "pred_feature_cols": meta.get("pred_feature_cols") or bundle.get("pred_feature_cols"),
        "intermediate_model_id": meta.get("intermediate_model_id")
        or bundle.get("intermediate_model_id"),
        "target_cols": target_cols,
        "main_target": main,
        "main_target_index": t_idx,
        "n_trees": n_trees,
        "global_feature_importance": imp,
        "metrics_eval": metrics_eval,
        "metrics_train": meta.get("metrics_train"),
        "main_target_metrics": main_metrics,
        "xgb_params": meta.get("xgb_params") or bundle.get("params"),
        "n_train": meta.get("n_train"),
        "n_eval": meta.get("n_eval"),
        "eval_year": meta.get("eval_year"),
        "last_trained": last,
        "top_model": top,
        "models": models,
    }


def get_tree(
    model_id: str,
    *,
    target_index: int | None = None,
    tree_index: int = 0,
    tier: str = "intermediate",
) -> dict[str, Any]:
    loaded = _load_model_bundle(model_id, tier=tier)
    bundle = loaded["bundle"]
    meta = loaded["meta"]
    feature_cols = list(bundle.get("feature_cols") or [])
    if target_index is None:
        est, t_idx, main = _estimator_for_main(bundle, meta)
    else:
        estimators = _get_estimators(bundle)
        t_idx = int(target_index)
        est = estimators[t_idx]
        target_cols = list(bundle.get("target_cols") or [])
        main = target_cols[t_idx] if t_idx < len(target_cols) else f"target_{t_idx}"

    booster = est.get_booster()
    dumps = booster.get_dump(with_stats=True)
    n_trees = len(dumps)
    if tree_index < 0 or tree_index >= n_trees:
        raise ValueError(f"tree_index hors bornes 0..{n_trees - 1}")
    tree = parse_tree_dump(dumps[tree_index], feature_cols)
    return {
        "model_id": model_id,
        "target_index": t_idx,
        "target_name": main,
        "tree_index": tree_index,
        "n_trees": n_trees,
        "depth": _tree_depth(tree),
        "n_features": len(_tree_features(tree)),
        "tree": tree,
        "dump": dumps[tree_index],
    }


def trees_table(model_id: str, *, tier: str = "intermediate") -> dict[str, Any]:
    """
    Table des arbres pour la cible principale.

    Pour XGBoost, une « performance » par arbre isolé n'a pas toujours de sens
    (chaque arbre prédit un résidu). On calcule la perf **cumulative** après
    k+1 arbres (pred avec iteration_range) sur le jeu d'évaluation — c'est la
    métrique exploitable. Classement par R² cumulé décroissant n'a de sens que
    pour afficher la progression ; on garde l'ordre naturel d'entraînement
    (arbre 0..N) et on expose r2/rmse cumulés.
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from xgboost import DMatrix

    loaded = _load_model_bundle(model_id, tier=tier)
    bundle = loaded["bundle"]
    meta = loaded["meta"]
    feature_cols = list(bundle.get("feature_cols") or [])
    est, t_idx, main = _estimator_for_main(bundle, meta)

    frame, md_meta = _load_model_frame()
    # Modèle final : reconstruire X = descriptives + pred_* via intermédiaire
    if tier == "final":
        from archive.accor_1_0_6.pipelines.src.accor.model_final import build_stacked_features
        from archive.accor_1_0_6.pipelines.src.accor.model_train import load_design_model

        mid = meta.get("intermediate_model_id") or bundle.get("intermediate_model_id")
        if not mid:
            return {
                "model_id": model_id,
                "main_target": main,
                "trees": [],
                "note": "intermediate_model_id manquant sur le modèle final",
            }
        inter = load_design_model(str(mid))["bundle"]
        frame, feature_cols, _, _ = build_stacked_features(frame, md_meta, inter)
    else:
        for c in feature_cols:
            if c in frame.columns:
                frame[c] = pd.to_numeric(frame[c], errors="coerce").fillna(0.0)

    if main in frame.columns:
        y = pd.to_numeric(frame[main], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    else:
        return {
            "model_id": model_id,
            "main_target": main,
            "trees": [],
            "note": f"Cible {main} absente de model_data",
        }

    if "_is_eval" in frame.columns:
        mask = frame["_is_eval"].astype(int) == 1
    elif md_meta.get("eval_year") is not None and "annee" in frame.columns:
        mask = pd.to_numeric(frame["annee"], errors="coerce") == int(md_meta["eval_year"])
    else:
        mask = pd.Series(True, index=frame.index)

    missing = [c for c in feature_cols if c not in frame.columns]
    if missing:
        return {
            "model_id": model_id,
            "main_target": main,
            "trees": [],
            "note": f"Features manquantes : {missing[:5]}",
        }
    X = frame.loc[mask, feature_cols].to_numpy(dtype=float)
    y_eval = y[mask.to_numpy()]
    if len(X) < 2:
        return {"model_id": model_id, "main_target": main, "trees": [], "note": "Pas assez de lignes eval"}

    booster = est.get_booster()
    n_trees = int(booster.num_boosted_rounds())
    dmat = DMatrix(X, feature_names=feature_cols)
    dumps = booster.get_dump(with_stats=True)

    rows: list[dict[str, Any]] = []
    # subsample iterations if many trees
    step = max(1, n_trees // 100)
    indices = list(range(0, n_trees, step))
    if indices[-1] != n_trees - 1:
        indices.append(n_trees - 1)

    for k in indices:
        tree = parse_tree_dump(dumps[k], feature_cols)
        pred = booster.predict(dmat, iteration_range=(0, k + 1))
        msk = np.isfinite(y_eval) & np.isfinite(pred)
        if msk.sum() < 2:
            continue
        yt, yp = y_eval[msk], pred[msk]
        r2 = float(r2_score(yt, yp))
        rmse = float(np.sqrt(mean_squared_error(yt, yp)))
        mae = float(mean_absolute_error(yt, yp))
        rows.append(
            {
                "tree_index": k,
                "depth": _tree_depth(tree),
                "n_features": len(_tree_features(tree)),
                "r2_cumulative": r2,
                "rmse_cumulative": rmse,
                "mae_cumulative": mae,
                "n_trees_used": k + 1,
                "performance_note": "cumulatif (boosting)",
            }
        )

    # full model metrics
    full_pred = booster.predict(dmat)
    msk = np.isfinite(y_eval) & np.isfinite(full_pred)
    global_m = {}
    if msk.sum() >= 2:
        yt, yp = y_eval[msk], full_pred[msk]
        global_m = {
            "r2": float(r2_score(yt, yp)),
            "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
            "mae": float(mean_absolute_error(yt, yp)),
            "n": int(msk.sum()),
        }

    return {
        "model_id": model_id,
        "main_target": main,
        "n_trees": n_trees,
        "global": global_m,
        "trees": rows,
        "note": (
            "Perf = prédiction cumulative après k arbres (XGBoost boosting). "
            "Un arbre isolé ne prédit pas directement la cible."
        ),
    }


def feature_importance_payload(
    model_id: str,
    *,
    target_index: int | None = None,
    tier: str = "intermediate",
) -> dict[str, Any]:
    ov = explore_overview(model_id, tier=tier)
    return {
        "model_id": model_id,
        "tier": tier,
        "scope": "main_target",
        "target_name": ov["main_target"],
        "importance": ov["global_feature_importance"],
    }


# compat
def tree_performances(model_id: str, *, target_index: int = 0, max_points: int = 80) -> dict[str, Any]:
    return trees_table(model_id)
