"""
Exploration des modèles arbre (XGBoost) sauvegardés.

- Structure d'un arbre (dump → JSON pour visualisation)
- Performance cumulative par itération (arbre) vs performance globale
- Feature importance (globale + par target si multi-output)
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.multioutput import MultiOutputRegressor

from model_train import _load_frame, load_model

_SPLIT_RE = re.compile(
    r"^(\d+):\[(f\d+|[^<\]]+)<([^\]]+)\]\s+yes=(\d+),no=(\d+),missing=(\d+)"
    r"(?:,gain=([^,]+))?(?:,cover=([^,\s]+))?"
)
_LEAF_RE = re.compile(
    r"^(\d+):leaf=([^\s,]+)(?:,cover=([^\s,]+))?"
)


def _get_estimators(bundle: dict[str, Any]) -> list[Any]:
    """Retourne la liste des XGBRegressor (un par target, ou un seul)."""
    model = bundle["model"]
    if isinstance(model, MultiOutputRegressor):
        return list(model.estimators_)
    return [model]


def _feature_name(feature_cols: list[str], token: str) -> str:
    """Mappe f12 → nom de feature (ou laisse le token)."""
    if token.startswith("f") and token[1:].isdigit():
        idx = int(token[1:])
        if 0 <= idx < len(feature_cols):
            return feature_cols[idx]
    return token


def parse_tree_dump(dump: str, feature_cols: list[str]) -> dict[str, Any]:
    """
    Parse le dump texte d'un arbre XGBoost en arbre JSON.

    Format dump::
        0:[f22<0.28] yes=1,no=2,missing=2,gain=...,cover=...
        1:leaf=-1.2,cover=10
    """
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
            continue
    # Attache children pour le layout
    for nid, node in list(nodes.items()):
        if not node["is_leaf"]:
            node["left"] = nodes.get(node["yes"])
            node["right"] = nodes.get(node["no"])
    root = nodes.get(0)
    if root is None:
        return {"id": 0, "is_leaf": True, "value": 0.0, "label": "empty"}
    return _strip_cycles(root)


def _strip_cycles(node: dict[str, Any] | None, depth: int = 0) -> dict[str, Any]:
    """Copie récursive sans références croisées (JSON-safe)."""
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
        "left": _strip_cycles(node.get("left"), depth + 1),
        "right": _strip_cycles(node.get("right"), depth + 1),
    }


def _estimator_importance(est: Any, feature_cols: list[str]) -> list[dict[str, Any]]:
    if not hasattr(est, "feature_importances_"):
        return []
    imp = est.feature_importances_
    pairs = [
        {"feature": feature_cols[i], "importance": float(imp[i])}
        for i in range(min(len(feature_cols), len(imp)))
    ]
    pairs.sort(key=lambda x: -x["importance"])
    return pairs


def explore_overview(model_id: str) -> dict[str, Any]:
    """Vue d'ensemble d'un modèle pour l'onglet Explore."""
    loaded = load_model(model_id)
    bundle = loaded["bundle"]
    meta = loaded["meta"]
    feature_cols: list[str] = list(bundle.get("feature_cols") or meta.get("feature_cols") or [])
    target_cols: list[str] = list(bundle.get("target_cols") or meta.get("target_cols") or [])
    estimators = _get_estimators(bundle)

    targets_info: list[dict[str, Any]] = []
    for i, est in enumerate(estimators):
        name = target_cols[i] if i < len(target_cols) else f"target_{i}"
        n_trees = 0
        try:
            n_trees = int(est.get_booster().num_boosted_rounds())
        except Exception:
            n_trees = int(getattr(est, "n_estimators", 0) or 0)
        targets_info.append(
            {
                "index": i,
                "name": name,
                "n_trees": n_trees,
                "feature_importance": _estimator_importance(est, feature_cols)[:40],
            }
        )

    # Importance globale (moyenne multi-output) depuis meta ou recalcul
    global_imp = meta.get("top_feature_importance") or []
    if not global_imp and targets_info:
        acc: dict[str, float] = {}
        for t in targets_info:
            for row in t["feature_importance"]:
                acc[row["feature"]] = acc.get(row["feature"], 0.0) + row["importance"]
        n = max(len(targets_info), 1)
        global_imp = [
            {"feature": k, "importance": v / n}
            for k, v in sorted(acc.items(), key=lambda x: -x[1])[:40]
        ]

    return {
        "id": model_id,
        "created_at": meta.get("created_at"),
        "source": meta.get("source"),
        "n_features": len(feature_cols),
        "n_targets": len(target_cols),
        "feature_cols": feature_cols,
        "target_cols": target_cols,
        "targets": targets_info,
        "global_feature_importance": global_imp,
        "metrics_test": meta.get("metrics_test"),
        "metrics_train": meta.get("metrics_train"),
        "xgb_params": meta.get("xgb_params") or bundle.get("params"),
        "n_rows_used": meta.get("n_rows_used"),
        "n_train": meta.get("n_train"),
        "n_test": meta.get("n_test"),
    }


def get_tree(
    model_id: str,
    *,
    target_index: int = 0,
    tree_index: int = 0,
) -> dict[str, Any]:
    """Structure JSON d'un arbre (target_index, tree_index 0-based)."""
    loaded = load_model(model_id)
    bundle = loaded["bundle"]
    feature_cols: list[str] = list(bundle.get("feature_cols") or [])
    target_cols: list[str] = list(bundle.get("target_cols") or [])
    estimators = _get_estimators(bundle)

    if target_index < 0 or target_index >= len(estimators):
        raise ValueError(f"target_index hors bornes 0..{len(estimators) - 1}")

    est = estimators[target_index]
    booster = est.get_booster()
    dumps = booster.get_dump(with_stats=True)
    n_trees = len(dumps)
    if tree_index < 0 or tree_index >= n_trees:
        raise ValueError(f"tree_index hors bornes 0..{n_trees - 1}")

    tree = parse_tree_dump(dumps[tree_index], feature_cols)
    target_name = target_cols[target_index] if target_index < len(target_cols) else f"target_{target_index}"
    return {
        "model_id": model_id,
        "target_index": target_index,
        "target_name": target_name,
        "tree_index": tree_index,
        "n_trees": n_trees,
        "tree": tree,
        "dump": dumps[tree_index],
    }


def _rebuild_xy(bundle: dict[str, Any], meta: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    """Reconstruit X, y depuis la source pour évaluer les arbres."""
    source = meta.get("source") or "data"
    feature_cols: list[str] = list(bundle.get("feature_cols") or meta.get("feature_cols") or [])
    target_cols: list[str] = list(bundle.get("target_cols") or meta.get("target_cols") or [])
    frame = _load_frame(source)

    # Utilise uniquement les colonnes présentes
    feature_cols = [c for c in feature_cols if c in frame.columns]
    target_cols = [c for c in target_cols if c in frame.columns]
    if not feature_cols or not target_cols:
        raise ValueError("Colonnes features/targets introuvables dans la source.")

    work = frame[feature_cols + target_cols].copy()
    for c in feature_cols + target_cols:
        work[c] = pd.to_numeric(work[c], errors="coerce")
    work = work.dropna(subset=target_cols, how="all")
    for c in feature_cols:
        med = work[c].median()
        work[c] = work[c].fillna(0.0 if pd.isna(med) else med)
    for c in target_cols:
        work[c] = work[c].fillna(0.0)

    X = work[feature_cols].to_numpy(dtype=float)
    y = work[target_cols].to_numpy(dtype=float)
    return X, y, feature_cols, target_cols


def tree_performances(
    model_id: str,
    *,
    target_index: int = 0,
    max_points: int = 80,
) -> dict[str, Any]:
    """
    Performance cumulative après 1..N arbres vs performance du modèle complet.

    Pour chaque itération k, on prédit avec les k premiers arbres du booster
    et on calcule RMSE / MAE / R². La courbe se compare à la perf globale
    (toutes les itérations).
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from xgboost import DMatrix

    loaded = load_model(model_id)
    bundle = loaded["bundle"]
    meta = loaded["meta"]
    estimators = _get_estimators(bundle)
    target_cols: list[str] = list(bundle.get("target_cols") or meta.get("target_cols") or [])

    if target_index < 0 or target_index >= len(estimators):
        raise ValueError(f"target_index hors bornes 0..{len(estimators) - 1}")

    est = estimators[target_index]
    target_name = target_cols[target_index] if target_index < len(target_cols) else f"target_{target_index}"

    X, y, feature_cols, tcols = _rebuild_xy(bundle, meta)
    # Align target column
    if target_name in tcols:
        yi = tcols.index(target_name)
    else:
        yi = min(target_index, y.shape[1] - 1)
    y_true = y[:, yi]

    # Split train/test approximate: use last test_size portion (deterministic)
    n = len(X)
    test_size = float(meta.get("test_size") or 0.2)
    n_test = max(1, int(round(n * test_size)))
    n_train = n - n_test
    # Same random_state as training if possible
    rng = np.random.RandomState(int((meta.get("xgb_params") or {}).get("random_state", 42)))
    idx = rng.permutation(n)
    test_idx = idx[n_train:]
    X_test = X[test_idx]
    y_test = y_true[test_idx]

    booster = est.get_booster()
    n_trees = int(booster.num_boosted_rounds())
    dmat = DMatrix(X_test, feature_names=feature_cols)

    # Sample tree indices if too many
    if n_trees <= max_points:
        tree_indices = list(range(n_trees))
    else:
        step = max(1, n_trees // max_points)
        tree_indices = list(range(step - 1, n_trees, step))
        if tree_indices[-1] != n_trees - 1:
            tree_indices.append(n_trees - 1)

    series: list[dict[str, Any]] = []
    for k in tree_indices:
        # iteration_range is half-open [start, end)
        pred = booster.predict(dmat, iteration_range=(0, k + 1))
        mask = np.isfinite(y_test) & np.isfinite(pred)
        if mask.sum() < 2:
            continue
        yt, yp = y_test[mask], pred[mask]
        rmse = float(np.sqrt(mean_squared_error(yt, yp)))
        mae = float(mean_absolute_error(yt, yp))
        r2 = float(r2_score(yt, yp))
        series.append(
            {
                "tree_index": k,
                "n_trees_used": k + 1,
                "rmse": rmse,
                "mae": mae,
                "r2": r2,
            }
        )

    # Global = full model
    full_pred = booster.predict(dmat)
    mask = np.isfinite(y_test) & np.isfinite(full_pred)
    yt, yp = y_test[mask], full_pred[mask]
    global_metrics = {
        "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
        "mae": float(mean_absolute_error(yt, yp)),
        "r2": float(r2_score(yt, yp)),
        "n": int(mask.sum()),
    }

    # Relative performance: r2_k / r2_global, rmse_global / rmse_k
    g_r2 = global_metrics["r2"]
    g_rmse = global_metrics["rmse"]
    for row in series:
        row["r2_vs_global"] = (
            float(row["r2"] / g_r2) if g_r2 and abs(g_r2) > 1e-12 else None
        )
        row["rmse_vs_global"] = (
            float(g_rmse / row["rmse"]) if row["rmse"] and row["rmse"] > 1e-12 else None
        )
        # fraction of error closed: (rmse_1 - rmse_k) / (rmse_1 - rmse_full)
        # simpler: residual gap
        row["rmse_gap_to_global"] = float(row["rmse"] - g_rmse)
        row["r2_gap_to_global"] = float(g_r2 - row["r2"])

    # Meta global from training (if available)
    meta_test = (meta.get("metrics_test") or {}).get("per_target", {}).get(target_name)

    return {
        "model_id": model_id,
        "target_index": target_index,
        "target_name": target_name,
        "n_trees": n_trees,
        "n_test": int(len(y_test)),
        "global": global_metrics,
        "meta_test": meta_test,
        "series": series,
    }


def feature_importance_payload(model_id: str, *, target_index: int | None = None) -> dict[str, Any]:
    """Feature importance globale ou pour une target."""
    overview = explore_overview(model_id)
    if target_index is None:
        return {
            "model_id": model_id,
            "scope": "global",
            "importance": overview["global_feature_importance"],
        }
    targets = overview["targets"]
    if target_index < 0 or target_index >= len(targets):
        raise ValueError(f"target_index hors bornes 0..{len(targets) - 1}")
    t = targets[target_index]
    return {
        "model_id": model_id,
        "scope": "target",
        "target_index": target_index,
        "target_name": t["name"],
        "importance": t["feature_importance"],
    }
