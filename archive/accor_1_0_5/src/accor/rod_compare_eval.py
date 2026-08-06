#!/usr/bin/env python3
"""
Évaluation pilotes 2026 : vrai CA vs simulateur Excel vs prédiction IA.

Pour chaque hôtel pilote (Simply / Liberty / Connected) :
  * vrai CA mensuel moyen = sum(montant_ventes) / n_mois dispo en année d'éval
  * CA simulé (Excel) pour les 3 solutions
  * CA prédit (modèle final de préférence) en 3 scénarios de flags solution

Métriques publiques : MAE, MSE (pas de R²).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from archive.accor_1_0_5.src.accor.data_io import DATA_DIR
from archive.accor_1_0_5.src.accor.hotel_solutions import SOLUTION_FLAG_COLS, load_pilot_solution_codes
from archive.accor_1_0_5.src.accor.model_data import MAIN_TARGET
from archive.accor_1_0_5.src.accor.model_eval import _metrics_1d

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")
FLAG_BY_SOL = {
    "SIMPLY": "hotel_solution_simply",
    "LIBERTY": "hotel_solution_liberty",
    "CONNECTED": "hotel_solution_connected",
}


def _load_sales() -> pd.DataFrame:
    path = DATA_DIR / "hotel_sales_data.xlsx"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name="hotel_sales")
    except Exception:
        return pd.read_excel(path, sheet_name=0)


def _true_avg_monthly(
    sales: pd.DataFrame, hotel_code: str, year: int
) -> dict[str, Any]:
    if sales is None or sales.empty:
        return {"avg_monthly": None, "n_months": 0, "sum_ca": 0.0, "months": []}
    df = sales.copy()
    df["hotel_code"] = df["hotel_code"].astype(str).str.strip()
    df["annee"] = pd.to_numeric(df["annee"], errors="coerce")
    sub = df.loc[(df["hotel_code"] == hotel_code) & (df["annee"] == int(year))]
    if sub.empty:
        return {"avg_monthly": None, "n_months": 0, "sum_ca": 0.0, "months": []}
    ca = pd.to_numeric(sub.get("montant_ventes"), errors="coerce").fillna(0.0)
    months = sorted(
        int(m)
        for m in pd.to_numeric(sub.get("mois"), errors="coerce").dropna().unique()
    )
    n = max(len(months), 1)
    s = float(ca.sum())
    return {
        "avg_monthly": round(s / n, 2),
        "n_months": n,
        "sum_ca": round(s, 2),
        "months": months,
    }


def _sim_avg_for_hotel(hotel_code: str) -> dict[str, float | None]:
    """CA HT mensuel projeté (colonne droite) pour chaque solution."""
    out: dict[str, float | None] = {c: None for c in CONCEPTS}
    try:
        from archive.accor_1_0_5.src.accor.rod_excel_sim import simulate_excel_dual

        res = simulate_excel_dual(hotel_code)
        if not res.get("ok"):
            return out
        for c in CONCEPTS:
            block = (res.get("concepts") or {}).get(c) or {}
            kpi = block.get("kpi") or {}
            v = kpi.get("right_ca_ht_num")
            if v is None:
                v = kpi.get("right_ca_ht")
            try:
                out[c] = round(float(v), 2) if v is not None and v != "Not profitable" else None
            except (TypeError, ValueError):
                out[c] = None
    except Exception:
        pass
    return out


def _predict_three_solutions(
    work_frame: pd.DataFrame,
    model: Any,
    feature_cols: list[str],
    hotel_code: str,
    year: int,
) -> dict[str, float | None]:
    """
    Pour les mois d'éval de l'hôtel : 3 scénarios (simply / liberty / connected = 1)
    → moyenne des prédictions par solution.
    ``work_frame`` doit déjà contenir toutes les features du modèle
    (stacking inclus pour le final).
    """
    out: dict[str, float | None] = {c: None for c in CONCEPTS}
    if work_frame is None or work_frame.empty or model is None or not feature_cols:
        return out
    work = work_frame.copy()
    work["hotel_code"] = work["hotel_code"].astype(str).str.strip()
    work["annee"] = pd.to_numeric(work.get("annee"), errors="coerce")
    sub = work.loc[
        (work["hotel_code"] == hotel_code) & (work["annee"] == int(year))
    ].copy()
    if sub.empty:
        return out

    for col in SOLUTION_FLAG_COLS:
        if col not in sub.columns:
            sub[col] = 0

    # colonnes absentes → 0
    for c in feature_cols:
        if c not in sub.columns:
            sub[c] = 0.0

    for sol in CONCEPTS:
        sc = sub.copy()
        for c in CONCEPTS:
            col = FLAG_BY_SOL[c]
            if col in sc.columns:
                sc[col] = 1 if c == sol else 0
            # si le modèle n'a pas encore hotel_solution_* (ancien training),
            # les preds seront identiques — c'est attendu jusqu'au retrain
        try:
            X = sc[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(
                dtype=float
            )
            pred = np.asarray(model.predict(X), dtype=float)
            if pred.ndim > 1:
                pred = pred[:, 0]
            out[sol] = round(float(np.nanmean(pred)), 2)
        except Exception:
            out[sol] = None
    return out


def _unpack_model_bundle(loaded: dict[str, Any], mid: str) -> tuple[Any, list[str], str]:
    """Normalise load_final_model / load_design_model → model, feats, name."""
    # final: {bundle, meta}  design: often {model, meta, config} or pickle dict
    if "bundle" in loaded and isinstance(loaded.get("bundle"), dict):
        inner = loaded["bundle"]
        meta = loaded.get("meta") or {}
        model = inner.get("model") or inner
        conf = meta if isinstance(meta, dict) else {}
        if isinstance(inner, dict):
            feats = list(
                inner.get("feature_cols")
                or conf.get("feature_cols")
                or conf.get("descriptive_columns")
                or []
            )
            name = conf.get("name") or inner.get("name") or str(mid)
            if model is inner and "model" not in inner:
                model = inner  # full sklearn pipeline object
            return model if not isinstance(model, dict) else inner.get("model"), feats, str(name)
    model = loaded.get("model")
    meta = loaded.get("meta") or loaded.get("config") or {}
    conf = loaded.get("config") or meta
    feats = list(
        meta.get("feature_cols")
        or meta.get("descriptive_columns")
        or conf.get("feature_cols")
        or []
    )
    name = conf.get("name") or meta.get("name") or str(mid)
    return model, feats, str(name)


def _load_ml_bundle(tier: str = "final") -> tuple[Any, list[str], str, str] | None:
    """(model, feature_cols, model_id, model_name) or None."""
    try:
        if tier == "final":
            from archive.accor_1_0_5.src.accor.model_final import get_final_top_model, list_final_models, load_final_model

            top = get_final_top_model()
            if not top:
                models = list_final_models()
                if not models:
                    return None
                top = models[0]
            mid = str(top.get("id") or top.get("name"))
            loaded = load_final_model(mid)
        else:
            from archive.accor_1_0_5.src.accor.model_train import get_top_model, list_design_models, load_design_model

            top = get_top_model()
            if not top:
                models = list_design_models()
                if not models:
                    return None
                top = models[0]
            mid = str(top.get("id") or top.get("name"))
            loaded = load_design_model(mid)
        model, feats, name = _unpack_model_bundle(loaded, mid)
        if model is None:
            return None
        return model, feats, mid, name
    except Exception:
        return None


def evaluate_pilots_sim_vs_ia(
    *,
    year: int = 2026,
    tier: str = "final",
    model_id: str | None = None,
) -> dict[str, Any]:
    """
    Comparaison pilotes : vrai / simulé / prédit pour SIMPLY · LIBERTY · CONNECTED.
    """
    pilots = load_pilot_solution_codes()
    if not pilots:
        return {"ok": False, "error": "Aucun pilote dans rod_pilot_concepts.json"}

    sales = _load_sales()
    # model frame + modèle
    frame = pd.DataFrame()
    meta_md: dict[str, Any] = {}
    try:
        from archive.accor_1_0_5.src.accor.model_train import _load_model_frame

        frame, meta_md = _load_model_frame()
    except Exception:
        path = DATA_DIR / "model_data.xlsx"
        if path.exists():
            try:
                frame = pd.read_excel(path, sheet_name="model_data")
            except Exception:
                frame = pd.read_excel(path, sheet_name=0)

    ml = None
    feature_cols: list[str] = []
    mid = model_id or ""
    mname = ""
    conf_meta: dict[str, Any] = {}
    bundle: dict[str, Any] = {}
    try:
        if model_id:
            if tier == "final":
                from archive.accor_1_0_5.src.accor.model_final import load_final_model

                loaded = load_final_model(model_id)
            else:
                from archive.accor_1_0_5.src.accor.model_train import load_design_model

                loaded = load_design_model(model_id)
            mid = str(model_id)
        else:
            if tier == "final":
                from archive.accor_1_0_5.src.accor.model_final import (
                    get_final_top_model,
                    list_final_models,
                    load_final_model,
                )

                top = get_final_top_model() or (list_final_models() or [None])[0]
                if not top:
                    loaded = None
                else:
                    mid = str(top.get("id") or top.get("name"))
                    loaded = load_final_model(mid)
            else:
                from archive.accor_1_0_5.src.accor.model_train import (
                    get_top_model,
                    list_design_models,
                    load_design_model,
                )

                top = get_top_model() or (list_design_models() or [None])[0]
                if not top:
                    loaded = None
                else:
                    mid = str(top.get("id") or top.get("name"))
                    loaded = load_design_model(mid)
        if loaded:
            bundle = loaded.get("bundle") or {}
            conf_meta = loaded.get("meta") or {}
            ml = bundle.get("model")
            feature_cols = list(
                bundle.get("feature_cols") or conf_meta.get("feature_cols") or []
            )
            mname = conf_meta.get("name") or mid
            # Final stacking : ajouter pred_* via modèle intermédiaire
            if tier == "final" and ml is not None and not frame.empty:
                from archive.accor_1_0_5.src.accor.model_final import build_stacked_features
                from archive.accor_1_0_5.src.accor.model_train import load_design_model as _load_inter

                imid = conf_meta.get("intermediate_model_id") or bundle.get(
                    "intermediate_model_id"
                )
                if imid:
                    try:
                        inter = _load_inter(str(imid))["bundle"]
                        frame, feature_cols, _, _ = build_stacked_features(
                            frame, meta_md or {}, inter
                        )
                    except Exception:
                        # model_data a évolué (ex. hotel_solution_*) → fallback intermédiaire
                        try:
                            loaded_i = _load_inter(str(imid))
                            ml = (loaded_i.get("bundle") or {}).get("model")
                            feature_cols = list(
                                (loaded_i.get("bundle") or {}).get("feature_cols")
                                or (loaded_i.get("meta") or {}).get("feature_cols")
                                or []
                            )
                            mname = f"{mname} (fallback intermédiaire {imid})"
                            tier = "intermediate"
                        except Exception:
                            ml = None
                            feature_cols = []
    except Exception as exc:
        return {"ok": False, "error": f"Chargement modèle : {exc}"}

    hotels_out: list[dict[str, Any]] = []
    # Collect for metrics per solution (pred vs true, sim vs true)
    true_list: list[float] = []
    pred_by_sol: dict[str, list[float]] = {c: [] for c in CONCEPTS}
    sim_by_sol: dict[str, list[float]] = {c: [] for c in CONCEPTS}
    true_for_pred: dict[str, list[float]] = {c: [] for c in CONCEPTS}
    true_for_sim: dict[str, list[float]] = {c: [] for c in CONCEPTS}

    for code, installed in sorted(pilots.items()):
        true_info = _true_avg_monthly(sales, code, year)
        sim = _sim_avg_for_hotel(code)
        pred = (
            _predict_three_solutions(frame, ml, feature_cols, code, year)
            if ml is not None and feature_cols
            else {c: None for c in CONCEPTS}
        )
        name = ""
        if not sales.empty and "hotel_code" in sales.columns:
            m = sales.loc[sales["hotel_code"].astype(str).str.strip() == code]
            if not m.empty and "nom_hotel" in m.columns:
                name = str(m["nom_hotel"].iloc[0] or "")
        row = {
            "hotel_code": code,
            "hotel_name": name,
            "installed_solution": installed,
            "n_months_eval": true_info["n_months"],
            "months_eval": true_info["months"],
            "true_avg_monthly_ca": true_info["avg_monthly"],
            "true_sum_ca": true_info["sum_ca"],
            "sim": {c: sim.get(c) for c in CONCEPTS},
            "pred": {c: pred.get(c) for c in CONCEPTS},
            "delta_sim": {
                c: (
                    round(sim[c] - true_info["avg_monthly"], 2)
                    if sim.get(c) is not None and true_info["avg_monthly"] is not None
                    else None
                )
                for c in CONCEPTS
            },
            "delta_pred": {
                c: (
                    round(pred[c] - true_info["avg_monthly"], 2)
                    if pred.get(c) is not None and true_info["avg_monthly"] is not None
                    else None
                )
                for c in CONCEPTS
            },
        }
        hotels_out.append(row)
        if true_info["avg_monthly"] is not None:
            t = float(true_info["avg_monthly"])
            true_list.append(t)
            for c in CONCEPTS:
                if sim.get(c) is not None:
                    sim_by_sol[c].append(float(sim[c]))
                    true_for_sim[c].append(t)
                if pred.get(c) is not None:
                    pred_by_sol[c].append(float(pred[c]))
                    true_for_pred[c].append(t)

    metrics_sim: dict[str, Any] = {}
    metrics_pred: dict[str, Any] = {}
    for c in CONCEPTS:
        if true_for_sim[c]:
            metrics_sim[c] = _metrics_1d(
                np.array(true_for_sim[c], dtype=float),
                np.array(sim_by_sol[c], dtype=float),
            )
        if true_for_pred[c]:
            metrics_pred[c] = _metrics_1d(
                np.array(true_for_pred[c], dtype=float),
                np.array(pred_by_sol[c], dtype=float),
            )

    return {
        "ok": True,
        "eval_year": int(year),
        "tier": tier,
        "model_id": mid or None,
        "model_name": mname or None,
        "has_ml": ml is not None and bool(feature_cols),
        "n_pilots": len(hotels_out),
        "method": (
            "CA mensuel moyen = somme CA mois dispo / n_mois_dispo "
            f"(année d'évaluation {year}). "
            "Simulateur = projection Excel dual-colonne (R1→R4). "
            "IA = 3 prédictions (solution simply|liberty|connected = 1). "
            "Métriques : MAE et MSE."
        ),
        "hotels": hotels_out,
        "metrics_sim_vs_true": metrics_sim,
        "metrics_pred_vs_true": metrics_pred,
        "feature_cols_n": len(feature_cols),
        "solution_flags": list(SOLUTION_FLAG_COLS),
    }
