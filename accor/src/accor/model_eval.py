"""
Evaluation modele sur l annee incomplete (ex. 2026).

Metrique metier
---------------
Sur les mois **disponibles** pour chaque hotel :

* somme_reelle  = Σ y_true (mois presents)
* somme_predite = Σ y_pred (memes mois)
* revenu_mensuel_moyen = somme / 12

(On divise par 12 et non par le nombre de mois, car l annee est incomplete
mais le referentiel metier reste le « revenu mensuel moyen » = annuel/12.)

On compare ensuite ces moyennes par hotel (MAE, RMSE, R2, MAPE, biais)
et on fournit le detail hotel + les metriques mois a mois.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from accor.model_data import MAIN_TARGET
from accor.model_train import (
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
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    n = int(mask.sum())
    if n == 0:
        return {
            "n": 0,
            "rmse": float("nan"),
            "mae": float("nan"),
            "r2": float("nan"),
            "mape": float("nan"),
            "bias": float("nan"),
            "mean_true": float("nan"),
            "mean_pred": float("nan"),
        }
    yt, yp = y_true[mask], y_pred[mask]
    mape = float("nan")
    nz = np.abs(yt) > 1e-9
    if nz.any():
        mape = float(np.mean(np.abs((yt[nz] - yp[nz]) / yt[nz])) * 100.0)
    r2 = float("nan")
    if n >= 2 and float(np.std(yt)) > 1e-12:
        try:
            r2 = float(r2_score(yt, yp))
        except Exception:
            r2 = float("nan")
    return {
        "n": n,
        "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
        "mae": float(mean_absolute_error(yt, yp)),
        "r2": r2,
        "mape": mape,
        "bias": float(np.mean(yp - yt)),
        "mean_true": float(np.mean(yt)),
        "mean_pred": float(np.mean(yp)),
    }


def eval_meta() -> dict[str, Any]:
    """Payload UI : cibles, modeles, annee d eval par defaut."""
    try:
        _, meta = _load_model_frame()
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "target_cols": [],
            "main_target": MAIN_TARGET,
            "eval_year": 2026,
            "models": list_design_models(),
        }
    return {
        "ok": True,
        "target_cols": meta.get("target_columns") or [],
        "main_target": meta.get("main_target") or MAIN_TARGET,
        "eval_year": int(meta.get("eval_year") or 2026),
        "n_eval_rows": meta.get("n_eval"),
        "n_train_rows": meta.get("n_train"),
        "models": list_design_models(),
        "top_model": get_top_model(),
        "divisor_months": 12,
        "method": (
            "Pour chaque hotel : moyenne_mensuelle = somme(mois disponibles) / 12. "
            "Compare moyenne predite vs moyenne reelle."
        ),
    }


def evaluate_model(
    model_id: str | None = None,
    *,
    target: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """
    Evalue un modele design sur l annee ``year`` (defaut meta.eval_year / 2026).
    """
    models = list_design_models()
    if not model_id:
        top = get_top_model()
        model_id = (top or {}).get("id") or (top or {}).get("name")
    if not model_id and models:
        model_id = models[0].get("id") or models[0].get("name")
    if not model_id:
        return {"ok": False, "error": "Aucun modele design disponible."}

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
    if model is None or not feature_cols or not target_cols:
        return {"ok": False, "error": "Bundle modele incomplet (features/cibles)."}

    frame, meta = _load_model_frame()
    eval_year = int(year if year is not None else (meta.get("eval_year") or 2026))
    main_t = (target or meta.get("main_target") or MAIN_TARGET or target_cols[0]).strip()
    if main_t not in target_cols:
        if main_t not in frame.columns:
            return {
                "ok": False,
                "error": f"Cible inconnue : {main_t}",
                "target_cols": target_cols,
            }
        # autoriser cible presente dans frame meme si hors bundle (rare)
        target_cols = list(target_cols)
        if main_t not in target_cols:
            return {
                "ok": False,
                "error": (
                    f"La cible {main_t} n est pas dans le modele "
                    f"(cibles modele : {len(target_cols)})."
                ),
                "target_cols": target_cols,
            }

    target_idx = target_cols.index(main_t)

    # Features manquantes → 0 (meme convention train)
    work = frame.copy()
    for c in feature_cols:
        if c not in work.columns:
            work[c] = 0.0
        work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0.0)
    if main_t not in work.columns:
        return {"ok": False, "error": f"Colonne cible absente de model_data : {main_t}"}
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
        }

    X = eval_df[feature_cols].to_numpy(dtype=float)
    try:
        y_pred_all = model.predict(X)
    except Exception as exc:
        return {"ok": False, "error": f"Prediction echouee : {exc}"}

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

    # Aggregation hotel : somme / 12
    DIV = 12.0
    hotel_rows: list[dict[str, Any]] = []
    group_cols = ["hotel_code"]
    for code, g in eval_df.groupby(eval_df["hotel_code"].astype(str).str.strip()):
        n_m = int(len(g))
        s_true = float(pd.to_numeric(g["_y_true"], errors="coerce").fillna(0).sum())
        s_pred = float(pd.to_numeric(g["_y_pred"], errors="coerce").fillna(0).sum())
        avg_true = s_true / DIV
        avg_pred = s_pred / DIV
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

    return {
        "ok": True,
        "model_id": str(model_id),
        "model_name": conf_meta.get("name") or bundle.get("name") or str(model_id),
        "target": main_t,
        "eval_year": eval_year,
        "divisor_months": int(DIV),
        "months_present": months_present,
        "n_month_rows": int(len(eval_df)),
        "n_hotels": int(len(hotel_rows)),
        "method": (
            f"avg_monthly = sum(cible sur mois disponibles {months_present}) / {int(DIV)}. "
            "Comparaison hotel par hotel puis metriques globales."
        ),
        "metrics_hotel_avg": metrics_hotel,
        "metrics_month_level": metrics_month,
        "hotels": hotel_rows,
        "months_detail": month_rows,
        "totals": {
            "sum_true": round(float(np.nansum(y_true)), 4),
            "sum_pred": round(float(np.nansum(y_pred)), 4),
            "avg_monthly_true_all": round(float(np.nansum(y_true)) / DIV, 4),
            "avg_monthly_pred_all": round(float(np.nansum(y_pred)) / DIV, 4),
        },
    }
