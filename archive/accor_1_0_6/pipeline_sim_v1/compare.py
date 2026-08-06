"""
Compare LOO old (RevenueRules) vs new (formules pures).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .constants import EXCEL_COMPARE, EXCEL_NEW, EXCEL_OLD


def _load_or_run(engine: str) -> dict[str, Any]:
    if engine == "old":
        from .sim_v1_old import evaluate_loo, write_excel

        r = evaluate_loo()
        write_excel(r, EXCEL_OLD)
        return r
    from .sim_v1_new import evaluate_loo, write_excel

    r = evaluate_loo()
    write_excel(r, EXCEL_NEW)
    return r


def _read_excel_engine(path: Path) -> dict[str, pd.DataFrame] | None:
    if not path.exists():
        return None
    return {
        "data": pd.read_excel(path, sheet_name="data"),
        "predictions": pd.read_excel(path, sheet_name="predictions"),
        "metrics": pd.read_excel(path, sheet_name="metrics"),
    }


def _normalize_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    """Unifie scope / perimetre et ALL → GLOBAL."""
    m = metrics.copy()
    if "scope" not in m.columns and "perimetre" in m.columns:
        m = m.rename(columns={"perimetre": "scope"})
    if "scope" in m.columns:
        m["scope"] = m["scope"].astype(str).replace({"ALL": "GLOBAL"})
    if "mape_ca" in m.columns and "mape_ca_pct" not in m.columns:
        m["mape_ca_pct"] = m["mape_ca"]
    return m


def _normalize_predictions(pred: pd.DataFrame) -> pd.DataFrame:
    p = pred.copy()
    if "peers" not in p.columns:
        p["peers"] = ""
    return p


def compare(
    *,
    rerun: bool = True,
    old_path: Path | None = None,
    new_path: Path | None = None,
) -> dict[str, Any]:
    """
    Produit metrics_side_by_side, predictions_merged, delta_mae.
    Par defaut recalcule les deux moteurs (ne pas faire confiance aux Excel caches).
    """
    old_path = old_path or EXCEL_OLD
    new_path = new_path or EXCEL_NEW

    if rerun:
        old_r = _load_or_run("old")
        new_r = _load_or_run("new")
        pred_old = old_r["predictions"]
        pred_new = new_r["predictions"]
        met_old = old_r["metrics"]
        met_new = new_r["metrics"]
    else:
        o = _read_excel_engine(old_path)
        n = _read_excel_engine(new_path)
        if o is None or n is None:
            return compare(rerun=True, old_path=old_path, new_path=new_path)
        pred_old, pred_new = o["predictions"], n["predictions"]
        met_old, met_new = o["metrics"], n["metrics"]

    met_old = _normalize_metrics(met_old)
    met_new = _normalize_metrics(met_new)
    pred_old = _normalize_predictions(pred_old)
    pred_new = _normalize_predictions(pred_new)

    # metrics cote a cote
    m_old = met_old.set_index("scope") if "scope" in met_old.columns else met_old
    m_new = met_new.set_index("scope") if "scope" in met_new.columns else met_new
    scopes = list(dict.fromkeys(list(m_old.index) + list(m_new.index)))
    side_rows: list[dict[str, Any]] = []
    for sc in scopes:
        ro = m_old.loc[sc] if sc in m_old.index else None
        rn = m_new.loc[sc] if sc in m_new.index else None
        if isinstance(ro, pd.DataFrame):
            ro = ro.iloc[0]
        if isinstance(rn, pd.DataFrame):
            rn = rn.iloc[0]
        mae_ca_o = float(ro["mae_ca"]) if ro is not None else None
        mae_ca_n = float(rn["mae_ca"]) if rn is not None else None
        mae_m_o = float(ro["mae_marge"]) if ro is not None else None
        mae_m_n = float(rn["mae_marge"]) if rn is not None else None
        side_rows.append(
            {
                "scope": sc,
                "n_hotels_old": int(ro["n_hotels"]) if ro is not None else None,
                "n_hotels_new": int(rn["n_hotels"]) if rn is not None else None,
                "mae_ca_old": mae_ca_o,
                "mae_ca_new": mae_ca_n,
                "delta_mae_ca": (
                    round(mae_ca_n - mae_ca_o, 2)
                    if mae_ca_o is not None and mae_ca_n is not None
                    else None
                ),
                "mae_marge_old": mae_m_o,
                "mae_marge_new": mae_m_n,
                "delta_mae_marge": (
                    round(mae_m_n - mae_m_o, 2)
                    if mae_m_o is not None and mae_m_n is not None
                    else None
                ),
                "mape_ca_old": float(ro["mape_ca_pct"]) if ro is not None and pd.notna(ro.get("mape_ca_pct")) else None,
                "mape_ca_new": float(rn["mape_ca_pct"]) if rn is not None and pd.notna(rn.get("mape_ca_pct")) else None,
            }
        )
    metrics_side = pd.DataFrame(side_rows)

    # predictions mergees
    left = pred_old.rename(
        columns={
            "ca_pred": "ca_pred_old",
            "ca_err_abs": "ca_err_old",
            "marge_pred": "marge_pred_old",
            "marge_err_abs": "marge_err_old",
            "peers": "peers_old",
        }
    )
    right = pred_new.rename(
        columns={
            "ca_pred": "ca_pred_new",
            "ca_err_abs": "ca_err_new",
            "marge_pred": "marge_pred_new",
            "marge_err_abs": "marge_err_new",
            "peers": "peers_new",
        }
    )
    keep_r = [
        c
        for c in (
            "hotel_code",
            "ca_pred_new",
            "ca_err_new",
            "marge_pred_new",
            "marge_err_new",
            "peers_new",
        )
        if c in right.columns
    ]
    merged = left.merge(right[keep_r], on="hotel_code", how="outer")
    if "ca_err_old" in merged.columns and "ca_err_new" in merged.columns:
        merged["delta_ca_err"] = (
            merged["ca_err_new"].astype(float) - merged["ca_err_old"].astype(float)
        ).round(2)
    if "marge_err_old" in merged.columns and "marge_err_new" in merged.columns:
        merged["delta_marge_err"] = (
            merged["marge_err_new"].astype(float) - merged["marge_err_old"].astype(float)
        ).round(2)

    # delta MAE resume
    g = metrics_side[metrics_side["scope"] == "GLOBAL"]
    if not g.empty:
        delta_mae = pd.DataFrame(
            [
                {
                    "metric": "mae_ca",
                    "old": g.iloc[0]["mae_ca_old"],
                    "new": g.iloc[0]["mae_ca_new"],
                    "delta_new_minus_old": g.iloc[0]["delta_mae_ca"],
                },
                {
                    "metric": "mae_marge",
                    "old": g.iloc[0]["mae_marge_old"],
                    "new": g.iloc[0]["mae_marge_new"],
                    "delta_new_minus_old": g.iloc[0]["delta_mae_marge"],
                },
            ]
        )
    else:
        delta_mae = pd.DataFrame()

    return {
        "ok": True,
        "metrics_side_by_side": metrics_side,
        "predictions_merged": merged,
        "delta_mae": delta_mae,
    }


def write_excel(result: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    path = path or EXCEL_COMPARE
    result = result or compare(rerun=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        result["metrics_side_by_side"].to_excel(w, index=False, sheet_name="metrics_side_by_side")
        result["predictions_merged"].to_excel(w, index=False, sheet_name="predictions_merged")
        result["delta_mae"].to_excel(w, index=False, sheet_name="delta_mae")
    return path


def run(*, rerun: bool = True) -> dict[str, Any]:
    result = compare(rerun=rerun)
    out = write_excel(result)
    result["excel_path"] = str(out)
    return result


if __name__ == "__main__":
    r = run()
    print(r["metrics_side_by_side"].to_string(index=False))
    print(f"Excel → {r['excel_path']}")
