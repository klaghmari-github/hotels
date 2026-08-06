"""
Évaluation d'un modèle design sur une année incomplete (souvent 2026).

Pourquoi /12 et pas /n_mois ?
  L'année n'a que quelques mois de vérité terrain, mais le référentiel
  métier reste le « revenu mensuel moyen » = total annuel / 12. On prend
  donc la somme sur les mois disponibles et on divise toujours par 12,
  côté réel comme côté prédit (mêmes mois pour les deux).

Par hôtel :
  avg_monthly_true = sum(y_true) / 12
  avg_monthly_pred = sum(y_pred) / 12

Puis métriques globales sur ces moyennes (MAE, RMSE, R², MAPE, biais),
plus un détail mois à mois.

API admin : GET /api/model/eval/meta , GET|POST /api/model/eval
UI : onglet Evaluation (static/js/admin/model-eval-panel.js)

Cible par défaut = MAIN_TARGET (montant_ventes) ; n'importe quelle
colonne cible du multi-output est sélectionnable.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.model_data import MAIN_TARGET
from archive.accor_1_0_6.pipelines.src.accor.model_train import (
    get_top_model,
    list_design_models,
    load_design_model,
    _load_model_frame,
)


def _safe_float(x: Any, default: float = float("nan")) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _metrics_1d(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Métriques simples (public non-datascientist) : MAE + MSE (+ biais)."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    n = int(mask.sum())
    if n == 0:
        return {
            "n": 0,
            "mae": float("nan"),
            "mse": float("nan"),
            "bias": float("nan"),
            "mean_true": float("nan"),
            "mean_pred": float("nan"),
        }
    yt, yp = y_true[mask], y_pred[mask]
    return {
        "n": n,
        "mae": float(mean_absolute_error(yt, yp)),
        "mse": float(mean_squared_error(yt, yp)),
        "bias": float(np.mean(yp - yt)),
        "mean_true": float(np.mean(yt)),
        "mean_pred": float(np.mean(yp)),
    }


def eval_meta(*, tier: str = "intermediate", solution: str | None = None) -> dict[str, Any]:
    """
    Payload pour l'onglet Evaluation / GET /api/model/eval/meta.

    ``tier`` = intermediate (models/design) ou final (models/final/design).
    ``solution`` = SIMPLY|LIBERTY|CONNECTED pour filtrer les modèles spécialisés.
    """
    from archive.accor_1_0_6.pipelines.src.accor.hotel_solutions import normalize_solution

    solution = normalize_solution(solution)
    tier = "final" if tier == "final" else "intermediate"
    try:
        _, meta = _load_model_frame()
    except Exception as exc:
        models = []
        top = None
        if tier == "final":
            from archive.accor_1_0_6.pipelines.src.accor.model_final import get_final_top_model, list_final_models

            models = list_final_models(solution=solution)
            top = get_final_top_model(solution=solution)
        else:
            models = list_design_models(solution=solution)
            top = get_top_model(solution=solution)
        return {
            "ok": False,
            "error": str(exc),
            "tier": tier,
            "solution": solution,
            "target_cols": [],
            "main_target": MAIN_TARGET,
            "eval_year": 2026,
            "models": models,
            "top_model": top,
        }

    if tier == "final":
        from archive.accor_1_0_6.pipelines.src.accor.model_final import get_final_top_model, list_final_models

        models = list_final_models(solution=solution)
        top = get_final_top_model(solution=solution)
        target_cols = [meta.get("main_target") or MAIN_TARGET]
    else:
        models = list_design_models(solution=solution)
        top = get_top_model(solution=solution)
        target_cols = meta.get("target_columns") or []

    return {
        "ok": True,
        "tier": tier,
        "solution": solution,
        "target_cols": target_cols,
        "main_target": meta.get("main_target") or MAIN_TARGET,
        "eval_year": int(meta.get("eval_year") or 2026),
        "n_eval_rows": meta.get("n_eval"),
        "n_train_rows": meta.get("n_train"),
        "models": models,
        "top_model": top,
        "divisor_months": "n_months_available",
        "metrics_public": ["mae", "mse"],
        "method": (
            "CA mensuel moyen = somme(mois dispo) / n_mois_dispo (pas /12). "
            "Metriques : MAE et MSE."
            + (
                " Modele final = stacking + hotel_solution_simply|liberty|connected."
                if tier == "final"
                else " Features descriptives incluent hotel_solution_*."
            )
        ),
    }


def evaluate_model(
    model_id: str | None = None,
    *,
    target: str | None = None,
    year: int | None = None,
    tier: str = "intermediate",
) -> dict[str, Any]:
    """
    Évalue un modèle sur l'année ``year`` (défaut meta.eval_year).

    ``tier`` = intermediate (design multi-output) ou final (stacking).
    model_id None → top_model puis premier dispo.
    target None → main_target (montant_ventes).

    Retourne ok, metrics_hotel_avg, metrics_month_level, hotels[],
    months_detail[], totals (sum et avg /12). Voir docs/MODEL.md.
    """
    tier = "final" if tier == "final" else "intermediate"

    if tier == "final":
        from archive.accor_1_0_6.pipelines.src.accor.model_final import (
            get_final_top_model,
            list_final_models,
            load_final_model,
        )

        models = list_final_models()
        if not model_id:
            top = get_final_top_model()
            model_id = (top or {}).get("id") or (top or {}).get("name")
        if not model_id and models:
            model_id = models[0].get("id") or models[0].get("name")
        if not model_id:
            return {"ok": False, "error": "Aucun modele final disponible.", "tier": tier}
        try:
            loaded = load_final_model(str(model_id))
        except Exception as exc:
            return {"ok": False, "error": f"Chargement modele final impossible : {exc}"}
    else:
        models = list_design_models()
        if not model_id:
            top = get_top_model()
            model_id = (top or {}).get("id") or (top or {}).get("name")
        if not model_id and models:
            model_id = models[0].get("id") or models[0].get("name")
        if not model_id:
            return {"ok": False, "error": "Aucun modele intermediaire disponible.", "tier": tier}
        try:
            loaded = load_design_model(str(model_id))
        except Exception as exc:
            return {"ok": False, "error": f"Chargement modele impossible : {exc}"}

    bundle = loaded.get("bundle") or {}
    conf_meta = loaded.get("meta") or {}
    model = bundle.get("model")
    feature_cols: list[str] = list(
        bundle.get("feature_cols") or conf_meta.get("feature_cols") or []
    )
    target_cols: list[str] = list(
        bundle.get("target_cols") or conf_meta.get("target_cols") or []
    )
    if model is None or not feature_cols:
        return {"ok": False, "error": "Bundle modele incomplet (features).", "tier": tier}
    if not target_cols:
        target_cols = [MAIN_TARGET]

    frame, meta = _load_model_frame()
    eval_year = int(year if year is not None else (meta.get("eval_year") or 2026))
    main_t = (target or meta.get("main_target") or MAIN_TARGET or target_cols[0]).strip()

    # --- Features : intermediaire = descriptives ; final = stacking ---
    work = frame.copy()
    if tier == "final":
        from archive.accor_1_0_6.pipelines.src.accor.model_final import build_stacked_features
        from archive.accor_1_0_6.pipelines.src.accor.model_train import load_design_model as _load_inter

        mid = conf_meta.get("intermediate_model_id") or bundle.get("intermediate_model_id")
        if not mid:
            return {
                "ok": False,
                "error": "Modele final sans intermediate_model_id.",
                "tier": tier,
            }
        try:
            inter_bundle = _load_inter(str(mid))["bundle"]
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Intermediaire {mid} introuvable : {exc}",
                "tier": tier,
            }
        try:
            work, feature_cols, _, _ = build_stacked_features(
                work, meta, inter_bundle
            )
        except Exception as exc:
            return {"ok": False, "error": f"Stacking features : {exc}", "tier": tier}
        # mono-cible final
        target_cols = [main_t] if main_t in work.columns else list(target_cols)
        if main_t not in target_cols and main_t in work.columns:
            target_cols = [main_t]
    else:
        for c in feature_cols:
            if c not in work.columns:
                work[c] = 0.0
            work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)

    if main_t not in target_cols:
        if main_t not in work.columns:
            return {
                "ok": False,
                "error": f"Cible inconnue : {main_t}",
                "target_cols": target_cols,
                "tier": tier,
            }
        target_cols = list(target_cols)
        if main_t not in target_cols and tier != "final":
            return {
                "ok": False,
                "error": (
                    f"La cible {main_t} n est pas dans le modele "
                    f"(cibles modele : {len(target_cols)})."
                ),
                "target_cols": target_cols,
                "tier": tier,
            }

    target_idx = target_cols.index(main_t) if main_t in target_cols else 0

    if main_t not in work.columns:
        return {
            "ok": False,
            "error": f"Colonne cible absente de model_data : {main_t}",
            "tier": tier,
        }
    work[main_t] = pd.to_numeric(work[main_t], errors="coerce")

    years = pd.to_numeric(work.get("annee"), errors="coerce")
    months = pd.to_numeric(work.get("mois"), errors="coerce")
    mask_year = years == eval_year
    # mois avec verite terrain
    mask = mask_year & work[main_t].notna()
    eval_df = work.loc[mask].copy()
    if eval_df.empty:
        return {
            "ok": False,
            "error": f"Aucune ligne model_data pour l annee {eval_year} avec {main_t}.",
            "eval_year": eval_year,
            "target": main_t,
            "model_id": model_id,
            "tier": tier,
        }

    missing = [c for c in feature_cols if c not in eval_df.columns]
    if missing:
        return {
            "ok": False,
            "error": f"Features manquantes : {missing[:8]}",
            "tier": tier,
        }

    X = eval_df[feature_cols].to_numpy(dtype=float)
    try:
        y_pred_all = model.predict(X)
    except Exception as exc:
        return {"ok": False, "error": f"Prediction echouee : {exc}", "tier": tier}

    y_pred_all = np.asarray(y_pred_all)
    if y_pred_all.ndim == 1:
        y_pred = y_pred_all.astype(float)
    else:
        if target_idx >= y_pred_all.shape[1]:
            return {"ok": False, "error": "Index cible hors bornes du multi-output."}
        y_pred = y_pred_all[:, target_idx].astype(float)

    y_true = eval_df[main_t].to_numpy(dtype=float)
    eval_df = eval_df.copy()
    eval_df["_y_true"] = y_true
    eval_df["_y_pred"] = y_pred

    # Detail mois
    month_rows: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(eval_df.iterrows()):
        month_rows.append(
            {
                "hotel_code": str(row.get("hotel_code") or ""),
                "hotel_name": str(row.get("hotel_name") or row.get("nom_hotel") or ""),
                "hotel_brand": str(row.get("hotel_brand") or ""),
                "annee": int(row["annee"]) if pd.notna(row.get("annee")) else eval_year,
                "mois": int(row["mois"]) if pd.notna(row.get("mois")) else None,
                "y_true": _safe_float(row["_y_true"]),
                "y_pred": _safe_float(row["_y_pred"]),
                "error": _safe_float(row["_y_pred"]) - _safe_float(row["_y_true"]),
            }
        )

    # Aggregation hotel : CA mensuel moyen = somme / nb mois **disponibles**
    # (pas /12 — 2023 et 2026 souvent incomplets)
    hotel_rows: list[dict[str, Any]] = []
    for code, g in eval_df.groupby(eval_df["hotel_code"].astype(str).str.strip()):
        n_m = max(int(len(g)), 1)
        s_true = float(pd.to_numeric(g["_y_true"], errors="coerce").fillna(0).sum())
        s_pred = float(pd.to_numeric(g["_y_pred"], errors="coerce").fillna(0).sum())
        avg_true = s_true / n_m
        avg_pred = s_pred / n_m
        name = ""
        brand = ""
        if "hotel_name" in g.columns:
            name = str(g["hotel_name"].iloc[0] or "")
        elif "nom_hotel" in g.columns:
            name = str(g["nom_hotel"].iloc[0] or "")
        if "hotel_brand" in g.columns:
            brand = str(g["hotel_brand"].iloc[0] or "")
        months_list = sorted(
            int(m)
            for m in pd.to_numeric(g.get("mois"), errors="coerce").dropna().unique()
        )
        hotel_rows.append(
            {
                "hotel_code": str(code),
                "hotel_name": name,
                "hotel_brand": brand,
                "n_months": n_m,
                "months": months_list,
                "sum_true": round(s_true, 4),
                "sum_pred": round(s_pred, 4),
                "avg_monthly_true": round(avg_true, 4),
                "avg_monthly_pred": round(avg_pred, 4),
                "error_avg": round(avg_pred - avg_true, 4),
                "abs_error_avg": round(abs(avg_pred - avg_true), 4),
                "pct_error": (
                    round(100.0 * (avg_pred - avg_true) / avg_true, 2)
                    if abs(avg_true) > 1e-9
                    else None
                ),
            }
        )

    hotel_rows.sort(key=lambda r: (-(r["abs_error_avg"] or 0), r["hotel_code"]))

    yt_h = np.array([r["avg_monthly_true"] for r in hotel_rows], dtype=float)
    yp_h = np.array([r["avg_monthly_pred"] for r in hotel_rows], dtype=float)
    metrics_hotel = _metrics_1d(yt_h, yp_h)
    metrics_month = _metrics_1d(y_true, y_pred)

    months_present = sorted(
        int(m)
        for m in pd.to_numeric(eval_df.get("mois"), errors="coerce").dropna().unique()
    )
    n_m_global = max(len(months_present), 1)

    return {
        "ok": True,
        "tier": tier,
        "model_id": str(model_id),
        "model_name": conf_meta.get("name") or bundle.get("name") or str(model_id),
        "target": main_t,
        "eval_year": eval_year,
        "divisor_months": "n_months_available",
        "months_present": months_present,
        "n_month_rows": int(len(eval_df)),
        "n_hotels": int(len(hotel_rows)),
        "method": (
            f"CA mensuel moyen = somme(mois dispo {months_present}) / n_mois_dispo "
            "(pas /12). Métriques : MAE et MSE uniquement."
            + (" Stacking final." if tier == "final" else "")
        ),
        "metrics_hotel_avg": metrics_hotel,
        "metrics_month_level": metrics_month,
        "hotels": hotel_rows,
        "months_detail": month_rows,
        "totals": {
            "sum_true": round(float(np.nansum(y_true)), 4),
            "sum_pred": round(float(np.nansum(y_pred)), 4),
            "avg_monthly_true_all": round(float(np.nansum(y_true)) / n_m_global, 4),
            "avg_monthly_pred_all": round(float(np.nansum(y_pred)) / n_m_global, 4),
        },
    }
