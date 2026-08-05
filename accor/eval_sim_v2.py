#!/usr/bin/env python3
"""
Evaluation leave-one-out du simulateur v2 (simulations d'assortiment).

Principe
--------
Pour un hotel cible H laisse de cote :
  1. On lit son mix de gammes (scenario vide = baseline observee).
  2. Pour chaque solution S (simply, liberty, connected) :
     - hotels pairs = hotels de S sans H
     - pour chaque pair P, on retient la simulation de P dont le mix gammes
       est le plus proche du mix de H (distance L2)
     - on moyenne CA et marge de ces simulations retenues
  3. On compare la prediction de la solution reelle de H au CA / marge reels.

Source : table DuckDB t_dataset_pivot (sim_v2).
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"

SOLUTIONS = ("simply", "liberty", "connected")
DEFAULT_DB = PROJECT_ROOT / "duckdb" / "pilotes" / "sim_v2" / "sim_v2.duckdb"
EXCEL_OUT = DATA_DIR / "eval_sim_v2_loo.xlsx"

CORE_TARGETS = (
    "montant_ventes_par_mois",
    "montant_marge_par_mois",
    "nombre_ventes_par_mois",
)


def _connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Connexion lecture seule (copie si lock concurrent)."""
    db_path = Path(db_path).expanduser().resolve()
    try:
        return duckdb.connect(str(db_path), read_only=True)
    except Exception:
        tmp = Path("/tmp") / f"sim_v2_eval_{hashlib.md5(str(db_path).encode()).hexdigest()[:8]}.duckdb"
        shutil.copy2(db_path, tmp)
        return duckdb.connect(str(tmp), read_only=True)


def load_pivot(db_path: Path | None = None) -> pd.DataFrame:
    con = _connect(db_path or DEFAULT_DB)
    try:
        df = con.sql("SELECT * FROM t_dataset_pivot").df()
    finally:
        con.close()
    df["hotel_code"] = df["hotel_code"].astype(str).str.strip()
    df["solution"] = df["solution"].astype(str).str.strip().str.lower()
    df["scenario_id"] = df["scenario_id"].astype(str)
    return df


def gamme_part_columns(df: pd.DataFrame) -> list[str]:
    return sorted(
        c
        for c in df.columns
        if c.startswith("gamme_") and c.endswith("_part_natures")
    )


def is_baseline_mask(df: pd.DataFrame) -> pd.Series:
    """Scenario sans nature retiree."""
    col = df["scenario_removed_natures"]
    # DuckDB / pandas : liste vide ou longueur 0
    def _empty(v: Any) -> bool:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return True
        if isinstance(v, (list, tuple, np.ndarray)):
            return len(v) == 0
        if hasattr(v, "__len__") and not isinstance(v, str):
            try:
                return len(v) == 0
            except Exception:
                return False
        s = str(v).strip()
        return s in {"", "[]", "None", "nan"}

    return col.map(_empty)


def mix_matrix(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    if not cols:
        return np.zeros((len(df), 0), dtype=float)
    return df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=float)


def closest_scenario_index(
    target_vec: np.ndarray,
    peer_matrix: np.ndarray,
) -> tuple[int, float]:
    """Index de la ligne peer la plus proche (L2) et distance."""
    if peer_matrix.size == 0:
        return 0, float("inf")
    diff = peer_matrix - target_vec.reshape(1, -1)
    dist = np.sqrt(np.sum(diff * diff, axis=1))
    idx = int(np.argmin(dist))
    return idx, float(dist[idx])


def build_baselines(pivot: pd.DataFrame, gcols: list[str]) -> pd.DataFrame:
    base = pivot.loc[is_baseline_mask(pivot)].copy()
    if base.empty:
        # fallback : min nombre de natures retirees
        pivot = pivot.copy()
        pivot["_n_rem"] = pivot["scenario_removed_natures"].map(
            lambda v: 0 if v is None else (len(v) if hasattr(v, "__len__") and not isinstance(v, str) else 999)
        )
        base = pivot.sort_values("_n_rem").groupby("hotel_code", as_index=False).first()
    base = base.drop_duplicates("hotel_code", keep="first")
    return base


def predict_for_hotel(
    hotel_code: str,
    pivot: pd.DataFrame,
    baselines: pd.DataFrame,
    gcols: list[str],
) -> dict[str, Any]:
    code = str(hotel_code).strip()
    row_b = baselines[baselines["hotel_code"] == code]
    if row_b.empty:
        raise KeyError(f"Baseline absente pour {code}")
    target = row_b.iloc[0]
    target_vec = mix_matrix(row_b, gcols)[0]
    true_solution = str(target["solution"]).lower()

    true_vals = {
        "montant_ventes_par_mois": float(target.get("montant_ventes_par_mois") or 0),
        "montant_marge_par_mois": float(target.get("montant_marge_par_mois") or 0),
        "nombre_ventes_par_mois": float(target.get("nombre_ventes_par_mois") or 0),
        "nombre_natures": float(target.get("nombre_natures") or 0),
        "metres_lineaires": float(target["metres_lineaires"])
        if pd.notna(target.get("metres_lineaires"))
        else None,
        "nombre_guests_par_mois": float(target.get("nombre_guests_par_mois") or 0),
    }
    true_mix = {c: float(target[c]) if pd.notna(target.get(c)) else 0.0 for c in gcols}

    by_solution: dict[str, Any] = {}
    detail_rows: list[dict[str, Any]] = []

    for sol in SOLUTIONS:
        peers = sorted(
            baselines.loc[
                (baselines["solution"] == sol) & (baselines["hotel_code"] != code),
                "hotel_code",
            ].unique()
        )
        peer_picks: list[dict[str, Any]] = []
        ca_list: list[float] = []
        marge_list: list[float] = []
        ventes_list: list[float] = []

        for peer in peers:
            peer_sims = pivot[pivot["hotel_code"] == peer]
            if peer_sims.empty:
                continue
            mat = mix_matrix(peer_sims, gcols)
            idx, dist = closest_scenario_index(target_vec, mat)
            pick = peer_sims.iloc[idx]
            ca = float(pick.get("montant_ventes_par_mois") or 0)
            marge = float(pick.get("montant_marge_par_mois") or 0)
            nv = float(pick.get("nombre_ventes_par_mois") or 0)
            ca_list.append(ca)
            marge_list.append(marge)
            ventes_list.append(nv)
            rem = pick.get("scenario_removed_natures")
            if hasattr(rem, "tolist"):
                rem = rem.tolist()
            peer_picks.append(
                {
                    "peer_hotel": peer,
                    "peer_solution": sol,
                    "scenario_id": str(pick.get("scenario_id") or ""),
                    "distance_mix_l2": round(dist, 6),
                    "montant_ventes_par_mois": round(ca, 2),
                    "montant_marge_par_mois": round(marge, 2),
                    "nombre_ventes_par_mois": round(nv, 2),
                    "natures_retirees": rem if isinstance(rem, list) else [],
                    "n_natures_retirees": len(rem) if isinstance(rem, list) else 0,
                }
            )
            detail_rows.append(
                {
                    "etape": f"Pair {sol}",
                    "variable": f"{peer}_scenario",
                    "valeur": str(pick.get("scenario_id") or "")[:16],
                    "source": f"distance L2 mix gammes = {dist:.6f}",
                }
            )
            detail_rows.append(
                {
                    "etape": f"Pair {sol}",
                    "variable": f"{peer}_ca",
                    "valeur": round(ca, 2),
                    "source": "simulation la plus proche",
                }
            )
            detail_rows.append(
                {
                    "etape": f"Pair {sol}",
                    "variable": f"{peer}_marge",
                    "valeur": round(marge, 2),
                    "source": "simulation la plus proche",
                }
            )

        pred_ca = float(np.mean(ca_list)) if ca_list else None
        pred_marge = float(np.mean(marge_list)) if marge_list else None
        pred_ventes = float(np.mean(ventes_list)) if ventes_list else None
        by_solution[sol] = {
            "n_peers": len(peers),
            "n_used": len(peer_picks),
            "pred_montant_ventes_par_mois": None if pred_ca is None else round(pred_ca, 2),
            "pred_montant_marge_par_mois": None if pred_marge is None else round(pred_marge, 2),
            "pred_nombre_ventes_par_mois": None if pred_ventes is None else round(pred_ventes, 2),
            "peers": peer_picks,
        }

    # prediction retenue = solution reelle de l'hotel
    pred_sol = by_solution.get(true_solution) or {}
    pred_ca = pred_sol.get("pred_montant_ventes_par_mois")
    pred_marge = pred_sol.get("pred_montant_marge_par_mois")
    err_ca = (
        abs(pred_ca - true_vals["montant_ventes_par_mois"])
        if pred_ca is not None
        else None
    )
    err_marge = (
        abs(pred_marge - true_vals["montant_marge_par_mois"])
        if pred_marge is not None
        else None
    )

    # detail resume
    inputs: list[dict[str, Any]] = [
        {"etape": "Hotel cible", "variable": "hotel_code", "valeur": code, "source": "leave-one-out"},
        {
            "etape": "Hotel cible",
            "variable": "solution_reelle",
            "valeur": true_solution,
            "source": "baseline scenario vide",
        },
        {
            "etape": "Hotel cible",
            "variable": "ca_reel_mensuel",
            "valeur": round(true_vals["montant_ventes_par_mois"], 2),
            "source": "baseline",
        },
        {
            "etape": "Hotel cible",
            "variable": "marge_reelle_mensuelle",
            "valeur": round(true_vals["montant_marge_par_mois"], 2),
            "source": "baseline (MARGE marche)",
        },
    ]
    for c, v in true_mix.items():
        short = c.replace("gamme_", "").replace("_part_natures", "")
        inputs.append(
            {
                "etape": "Mix gammes cible",
                "variable": short,
                "valeur": round(v, 4),
                "source": "part natures baseline",
            }
        )
    inputs.extend(detail_rows)
    for sol, block in by_solution.items():
        inputs.append(
            {
                "etape": "Prediction",
                "variable": f"{sol}_ca",
                "valeur": block.get("pred_montant_ventes_par_mois"),
                "source": f"moyenne des {block.get('n_used')} pairs",
            }
        )
        inputs.append(
            {
                "etape": "Prediction",
                "variable": f"{sol}_marge",
                "valeur": block.get("pred_montant_marge_par_mois"),
                "source": f"moyenne des {block.get('n_used')} pairs",
            }
        )
    inputs.append(
        {
            "etape": "Controle",
            "variable": "erreur_abs_ca",
            "valeur": None if err_ca is None else round(err_ca, 2),
            "source": f"solution {true_solution}",
        }
    )
    inputs.append(
        {
            "etape": "Controle",
            "variable": "erreur_abs_marge",
            "valeur": None if err_marge is None else round(err_marge, 2),
            "source": f"solution {true_solution}",
        }
    )

    return {
        "hotel_code": code,
        "solution": true_solution,
        "true": true_vals,
        "true_mix": true_mix,
        "by_solution": by_solution,
        "pred_ca": pred_ca,
        "pred_marge": pred_marge,
        "err_ca": None if err_ca is None else round(err_ca, 2),
        "err_marge": None if err_marge is None else round(err_marge, 2),
        "inputs": inputs,
    }


def evaluate_loo_sim_v2(db_path: Path | None = None) -> dict[str, Any]:
    pivot = load_pivot(db_path)
    gcols = gamme_part_columns(pivot)
    baselines = build_baselines(pivot, gcols)
    hotels = sorted(baselines["hotel_code"].unique())

    data_rows = []
    for _, r in baselines.iterrows():
        row = {
            "hotel_code": r["hotel_code"],
            "solution": r["solution"],
            "metres_lineaires": r.get("metres_lineaires"),
            "nombre_mois": r.get("nombre_mois"),
            "nombre_guests_par_mois": r.get("nombre_guests_par_mois"),
            "nombre_ventes_par_mois": r.get("nombre_ventes_par_mois"),
            "montant_ventes_par_mois": r.get("montant_ventes_par_mois"),
            "montant_marge_par_mois": r.get("montant_marge_par_mois"),
            "nombre_natures": r.get("nombre_natures"),
            "nombre_gammes": r.get("nombre_gammes"),
        }
        for c in gcols:
            row[c] = r.get(c)
        data_rows.append(row)
    data = pd.DataFrame(data_rows)

    per_hotel = []
    for code in hotels:
        per_hotel.append(predict_for_hotel(code, pivot, baselines, gcols))

    err_ca = [h["err_ca"] for h in per_hotel if h.get("err_ca") is not None]
    err_marge = [h["err_marge"] for h in per_hotel if h.get("err_marge") is not None]
    mae_ca = float(np.mean(err_ca)) if err_ca else None
    mae_marge = float(np.mean(err_marge)) if err_marge else None
    mape_vals = []
    for h in per_hotel:
        t = h["true"]["montant_ventes_par_mois"]
        e = h.get("err_ca")
        if e is not None and t and abs(t) > 1e-6:
            mape_vals.append(100.0 * e / abs(t))

    by_sol: dict[str, Any] = {}
    for sol in SOLUTIONS:
        sub = [h for h in per_hotel if h["solution"] == sol]
        by_sol[sol] = {
            "n": len(sub),
            "mae_ca": float(np.mean([h["err_ca"] for h in sub if h["err_ca"] is not None]))
            if sub
            else None,
            "mae_marge": float(
                np.mean([h["err_marge"] for h in sub if h["err_marge"] is not None])
            )
            if sub
            else None,
        }

    return {
        "ok": True,
        "method": "leave-one-out",
        "simulator": "v2_assortiment_mix_gammes",
        "gamme_columns": gcols,
        "data": data,
        "per_hotel": per_hotel,
        "metrics": {
            "mae_ca_mensuel": None if mae_ca is None else round(mae_ca, 2),
            "mae_marge_mensuel": None if mae_marge is None else round(mae_marge, 2),
            "mape_ca_pct": round(float(np.mean(mape_vals)), 1) if mape_vals else None,
            "n_hotels": len(per_hotel),
            "n_scenarios_total": int(pivot["scenario_id"].nunique()),
        },
        "by_solution": by_sol,
    }


def write_eval_excel(result: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    path = path or EXCEL_OUT
    result = result or evaluate_loo_sim_v2()
    data: pd.DataFrame = result["data"]
    per_hotel: list[dict[str, Any]] = result["per_hotel"]
    metrics = result["metrics"]
    by_sol = result["by_solution"]

    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        data.to_excel(w, index=False, sheet_name="data")

        for h in per_hotel:
            code = h["hotel_code"]
            sheet = f"eval_{code}"[:31]
            head = pd.DataFrame(
                [
                    {"etape": "RESUME", "variable": k, "valeur": v, "source": ""}
                    for k, v in {
                        "hotel_code": h["hotel_code"],
                        "solution": h["solution"],
                        "ca_ht_reel": h["true"]["montant_ventes_par_mois"],
                        "ca_ht_pred": h.get("pred_ca"),
                        "erreur_abs_ca": h.get("err_ca"),
                        "marge_reel": h["true"]["montant_marge_par_mois"],
                        "marge_pred": h.get("pred_marge"),
                        "erreur_abs_marge": h.get("err_marge"),
                    }.items()
                ]
            )
            # predictions par solution
            for sol, block in (h.get("by_solution") or {}).items():
                head = pd.concat(
                    [
                        head,
                        pd.DataFrame(
                            [
                                {
                                    "etape": "RESUME",
                                    "variable": f"pred_{sol}_ca",
                                    "valeur": block.get("pred_montant_ventes_par_mois"),
                                    "source": f"n_peers={block.get('n_used')}",
                                },
                                {
                                    "etape": "RESUME",
                                    "variable": f"pred_{sol}_marge",
                                    "valeur": block.get("pred_montant_marge_par_mois"),
                                    "source": f"n_peers={block.get('n_used')}",
                                },
                            ]
                        ),
                    ],
                    ignore_index=True,
                )
            detail = pd.DataFrame(h.get("inputs") or [])
            pd.concat([head, detail], ignore_index=True).to_excel(
                w, index=False, sheet_name=sheet
            )

        eval_rows = []
        for h in per_hotel:
            eval_rows.append(
                {
                    "hotel_code": h["hotel_code"],
                    "solution": h["solution"],
                    "ca_ht_reel": h["true"]["montant_ventes_par_mois"],
                    "ca_ht_pred": h.get("pred_ca"),
                    "erreur_abs_ca": h.get("err_ca"),
                    "marge_reel": h["true"]["montant_marge_par_mois"],
                    "marge_pred": h.get("pred_marge"),
                    "erreur_abs_marge": h.get("err_marge"),
                    "pred_simply_ca": (h.get("by_solution") or {})
                    .get("simply", {})
                    .get("pred_montant_ventes_par_mois"),
                    "pred_liberty_ca": (h.get("by_solution") or {})
                    .get("liberty", {})
                    .get("pred_montant_ventes_par_mois"),
                    "pred_connected_ca": (h.get("by_solution") or {})
                    .get("connected", {})
                    .get("pred_montant_ventes_par_mois"),
                }
            )
        df_eval = pd.DataFrame(eval_rows)
        metrics_df = pd.DataFrame(
            [
                {
                    "hotel_code": "MAE_GLOBAL",
                    "erreur_abs_ca": metrics.get("mae_ca_mensuel"),
                    "erreur_abs_marge": metrics.get("mae_marge_mensuel"),
                },
                {
                    "hotel_code": "MAPE_CA_PCT",
                    "erreur_abs_ca": metrics.get("mape_ca_pct"),
                },
            ]
        )
        for sol, v in by_sol.items():
            metrics_df = pd.concat(
                [
                    metrics_df,
                    pd.DataFrame(
                        [
                            {
                                "hotel_code": f"MAE_{sol.upper()}",
                                "solution": sol,
                                "erreur_abs_ca": None
                                if v.get("mae_ca") is None
                                else round(v["mae_ca"], 2),
                                "erreur_abs_marge": None
                                if v.get("mae_marge") is None
                                else round(v["mae_marge"], 2),
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        pd.concat([df_eval, metrics_df], ignore_index=True).to_excel(
            w, index=False, sheet_name="eval"
        )

    return path


def metrics_summary(result: dict[str, Any]) -> str:
    m = result.get("metrics") or {}
    lines = [
        f"Simulateur v2 leave-one-out — {m.get('n_hotels')} hotels",
        f"  scenarios dispo   : {m.get('n_scenarios_total')}",
        f"  MAE CA mensuel    : {m.get('mae_ca_mensuel')} EUR",
        f"  MAE marge mensuel : {m.get('mae_marge_mensuel')} EUR",
        f"  MAPE CA           : {m.get('mape_ca_pct')} %",
    ]
    for sol, v in (result.get("by_solution") or {}).items():
        ca = None if v.get("mae_ca") is None else round(v["mae_ca"], 2)
        mg = None if v.get("mae_marge") is None else round(v["mae_marge"], 2)
        lines.append(f"  [{sol}] n={v.get('n')} MAE_CA={ca} MAE_marge={mg}")
    return "\n".join(lines)
