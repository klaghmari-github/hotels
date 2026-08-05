"""
Helpers partages pour les pages d evaluation leave-one-out et la prediction.

Garde le rendu web uniforme et les exports Excel dans un format simple a lire.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = PROJECT_ROOT / "duckdb" / "pilotes" / "sim_v2" / "sim_v2.duckdb"
CONFIG_PATH = PROJECT_ROOT / "config"

# Chemins Excel de restitution LOO
EXCEL_V1 = DATA_DIR / "eval_sim_v1_loo.xlsx"
EXCEL_V2 = DATA_DIR / "eval_sim_v2_loo.xlsx"
EXCEL_IA = DATA_DIR / "eval_ia_loo.xlsx"
EXCEL_DENSE = DATA_DIR / "eval_dense_loo.xlsx"
EXCEL_COMPARE = DATA_DIR / "eval_compare_loo.xlsx"

COMMON_CSS = """
:root {
  --bg: #0f1419; --card: #1a2332; --line: #2a3a4f;
  --text: #e7eef7; --muted: #8b9bb0; --accent: #3d8bfd;
  --tab: #141c28; --tab-on: #243044; --ok: #3dd68c; --warn: #f5a524;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.45;
}
header {
  padding: 1rem 1.25rem; border-bottom: 1px solid var(--line);
  display: flex; flex-wrap: wrap; gap: .75rem; align-items: center;
  justify-content: space-between;
}
h1 { font-size: 1.1rem; margin: 0; font-weight: 600; }
h1 span { color: var(--muted); font-weight: 400; font-size: .85rem; margin-left: .4rem; }
a.link, button.btn {
  color: var(--text); border: 1px solid var(--line); border-radius: 8px;
  padding: .4rem .85rem; text-decoration: none; font-size: .85rem; font-weight: 600;
  background: transparent; cursor: pointer;
}
a.link:hover, button.btn:hover { border-color: var(--accent); color: var(--accent); }
button.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
main { padding: 1.1rem 1.25rem 2.5rem; max-width: 1280px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .7rem; }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: .9rem 1rem;
}
.card .lbl { color: var(--muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; }
.card .val { font-size: 1.25rem; font-weight: 700; margin-top: .2rem; }
.card .sub { color: var(--muted); font-size: .78rem; margin-top: .15rem; }
h2 { font-size: 1rem; margin: 1.1rem 0 .5rem; font-weight: 600; }
h3 { font-size: .9rem; margin: .9rem 0 .4rem; color: var(--muted); font-weight: 600; }
table {
  width: 100%; border-collapse: collapse; font-size: .82rem;
  background: var(--card); border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
}
th, td { text-align: left; padding: .5rem .55rem; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: .72rem; text-transform: uppercase; background: #152030; }
tr:last-child td { border-bottom: 0; }
tr:hover td { background: rgba(61,139,253,.05); }
.num { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
.tag {
  display: inline-block; padding: .1rem .45rem; border-radius: 999px;
  font-size: .7rem; font-weight: 600; background: #243044; color: var(--muted);
}
.tag.simply, .tag.A { color: #7dd3fc; }
.tag.liberty, .tag.B { color: #c4b5fd; }
.tag.connected, .tag.ML, .tag.XGBoost { color: #86efac; }
.tag.v1 { color: #f5a524; }
.muted { color: var(--muted); font-size: .85rem; }
.errbox {
  margin: 1rem 0; padding: .8rem 1rem; border: 1px solid #5a2a35;
  background: #2a1520; border-radius: 8px; color: #f5a0b0;
}
.scroll { overflow: auto; max-width: 100%; }
#status { color: var(--muted); font-size: .82rem; }
form.card label { display: block; font-size: .78rem; color: var(--muted); margin-top: .55rem; }
form.card input, form.card select, form.card textarea {
  width: 100%; margin-top: .2rem; padding: .45rem .55rem; border-radius: 6px;
  border: 1px solid var(--line); background: #101820; color: var(--text);
}
form.card .row { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; }
@media (max-width: 700px) { form.card .row { grid-template-columns: 1fr; } }
"""


def fmt_num(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    try:
        return f"{float(value):,.{digits}f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def open_pipeline(read_only: bool = False):
    """
    Ouvre la base sim_v2 avec le gestionnaire de pipelines.

    Si la base principale est verrouillee (notebook ouvert), on travaille
    sur une copie locale dediee a l evaluation.
    """
    import shutil

    from main import ConnectionPipeline

    try:
        return ConnectionPipeline(DB_PATH, CONFIG_PATH, read_only=read_only)
    except Exception as first_error:
        if read_only:
            raise first_error
        snapshot = (
            PROJECT_ROOT
            / "duckdb"
            / "pilotes"
            / "sim_v2"
            / "sim_v2_eval_work.duckdb"
        )
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        # Copie meilleure effort de l etat disque (base partagee eventuellement ouverte).
        shutil.copy2(DB_PATH, snapshot)
        wal = Path(str(DB_PATH) + ".wal")
        if wal.exists():
            try:
                shutil.copy2(wal, Path(str(snapshot) + ".wal"))
            except Exception:
                pass
        return ConnectionPipeline(snapshot, CONFIG_PATH, read_only=False)


def export_v2_loo_excel(
    results: pd.DataFrame,
    metrics: pd.DataFrame,
    method_comparison: pd.DataFrame,
    path: Path | None = None,
) -> Path:
    """
    Ecrit les resultats LOO restitution v2 dans un Excel standard.
    Feuilles : predictions, metrics, method_comparison, resume.
    """
    path = path or EXCEL_V2
    path.parent.mkdir(parents=True, exist_ok=True)

    resume_rows = []
    if metrics is not None and not metrics.empty:
        for _, row in metrics.iterrows():
            resume_rows.append(
                {
                    "source": "sim_v2",
                    "methode": row.get("methode"),
                    "solution": row.get("solution"),
                    "nombre_hotels": row.get("nombre_hotels"),
                    "ca_mae": row.get("montant_ventes_mae"),
                    "ca_rmse": row.get("montant_ventes_rmse"),
                    "ca_mape": row.get("montant_ventes_mape"),
                    "marge_mae": row.get("marge_mae"),
                    "marge_coef_mae": row.get("marge_selon_coef_mae"),
                }
            )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        results.to_excel(writer, sheet_name="predictions", index=False)
        metrics.to_excel(writer, sheet_name="metrics", index=False)
        method_comparison.to_excel(
            writer, sheet_name="method_comparison", index=False
        )
        pd.DataFrame(resume_rows).to_excel(
            writer, sheet_name="resume", index=False
        )
    return path


def export_ia_loo_excel(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    comparison: pd.DataFrame | None = None,
    path: Path | None = None,
    source_label: str = "ia_xgboost",
) -> Path:
    """Ecrit les resultats LOO d un modele ML (XGBoost, dense, …) en Excel."""
    path = path or EXCEL_IA
    path.parent.mkdir(parents=True, exist_ok=True)

    resume = metrics.copy() if metrics is not None else pd.DataFrame()
    if not resume.empty:
        resume.insert(0, "source", source_label)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        predictions.to_excel(writer, sheet_name="predictions", index=False)
        metrics.to_excel(writer, sheet_name="metrics", index=False)
        if comparison is not None and not comparison.empty:
            comparison.to_excel(
                writer, sheet_name="vs_sim_v2", index=False
            )
        resume.to_excel(writer, sheet_name="resume", index=False)
    return path


def export_dense_loo_excel(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    path: Path | None = None,
) -> Path:
    """Export LOO du reseau dense (meme schema que l IA XGBoost)."""
    return export_ia_loo_excel(
        predictions,
        metrics,
        comparison=None,
        path=path or EXCEL_DENSE,
        source_label="ia_dense",
    )


def load_excel_sheets(path: Path) -> dict[str, pd.DataFrame]:
    if not path.exists():
        return {}
    xl = pd.ExcelFile(path)
    return {
        name: pd.read_excel(path, sheet_name=name)
        for name in xl.sheet_names
    }


def safe_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_compare_excel(
    v1_path: Path = EXCEL_V1,
    v2_path: Path = EXCEL_V2,
    ia_path: Path = EXCEL_IA,
    dense_path: Path = EXCEL_DENSE,
    out_path: Path = EXCEL_COMPARE,
) -> Path:
    """
    Agrege les MAE principales des approches disponibles pour une vue comparative.
    Les sources manquantes sont simplement ignorees.
    """
    rows: list[dict[str, Any]] = []

    # --- V2 restitution ---
    v2 = load_excel_sheets(v2_path)
    if "metrics" in v2 and not v2["metrics"].empty:
        m = v2["metrics"]
        # lignes globales : solution nulle
        global_rows = m[m["solution"].isna()] if "solution" in m.columns else m
        if global_rows.empty:
            global_rows = m
        for _, r in global_rows.iterrows():
            rows.append(
                {
                    "modele": "sim_v2",
                    "methode": r.get("methode"),
                    "cible": "montant_ventes_par_mois",
                    "mae": safe_float(r.get("montant_ventes_mae")),
                    "rmse": safe_float(r.get("montant_ventes_rmse")),
                    "mape": safe_float(r.get("montant_ventes_mape")),
                    "biais": safe_float(r.get("montant_ventes_biais")),
                }
            )
            rows.append(
                {
                    "modele": "sim_v2",
                    "methode": r.get("methode"),
                    "cible": "montant_marge_par_mois",
                    "mae": safe_float(r.get("marge_mae")),
                    "rmse": safe_float(r.get("marge_rmse")),
                    "mape": safe_float(r.get("marge_mape")),
                    "biais": None,
                }
            )
            rows.append(
                {
                    "modele": "sim_v2",
                    "methode": r.get("methode"),
                    "cible": "montant_marge_selon_coef_par_mois",
                    "mae": safe_float(r.get("marge_selon_coef_mae")),
                    "rmse": safe_float(r.get("marge_selon_coef_rmse")),
                    "mape": safe_float(r.get("marge_selon_coef_mape")),
                    "biais": None,
                }
            )

    # --- IA XGBoost ---
    ia = load_excel_sheets(ia_path)
    if "metrics" in ia and not ia["metrics"].empty:
        for _, r in ia["metrics"].iterrows():
            rows.append(
                {
                    "modele": "ia_xgboost",
                    "methode": "ML",
                    "cible": r.get("target"),
                    "mae": safe_float(r.get("mae")),
                    "rmse": safe_float(r.get("rmse")),
                    "mape": safe_float(r.get("mape")),
                    "biais": safe_float(r.get("biais")),
                    "nombre_hotels": r.get("nombre_hotels"),
                }
            )

    # --- Reseau dense ---
    dense = load_excel_sheets(dense_path)
    if "metrics" in dense and not dense["metrics"].empty:
        for _, r in dense["metrics"].iterrows():
            rows.append(
                {
                    "modele": "ia_dense",
                    "methode": "NN",
                    "cible": r.get("target"),
                    "mae": safe_float(r.get("mae")),
                    "rmse": safe_float(r.get("rmse")),
                    "mape": safe_float(r.get("mape")),
                    "biais": safe_float(r.get("biais")),
                    "nombre_hotels": r.get("nombre_hotels"),
                }
            )

    # --- V1 (format historique resume) ---
    v1 = load_excel_sheets(v1_path)
    if "eval" in v1 and not v1["eval"].empty:
        ev = v1["eval"]
        mae_global = ev[ev["hotel_code"].astype(str) == "MAE_GLOBAL"]
        if not mae_global.empty:
            r = mae_global.iloc[0]
            rows.append(
                {
                    "modele": "sim_v1",
                    "methode": "regles_excel",
                    "cible": "montant_ventes_par_mois",
                    "mae": safe_float(r.get("erreur_abs_ca")),
                    "rmse": None,
                    "mape": None,
                    "biais": None,
                }
            )
            rows.append(
                {
                    "modele": "sim_v1",
                    "methode": "regles_excel",
                    "cible": "montant_marge_par_mois",
                    "mae": safe_float(r.get("erreur_abs_marge")),
                    "rmse": None,
                    "mape": None,
                    "biais": None,
                }
            )
        mape = ev[ev["hotel_code"].astype(str) == "MAPE_CA_PCT"]
        if not mape.empty and rows:
            for row in rows:
                if row["modele"] == "sim_v1" and row["cible"] == "montant_ventes_par_mois":
                    row["mape"] = safe_float(mape.iloc[0].get("erreur_abs_ca"))

    # Predictions hotel si dispo pour detail
    detail_frames = []
    if "predictions" in v2 and not v2["predictions"].empty:
        d = v2["predictions"].copy()
        d.insert(0, "modele", "sim_v2")
        detail_frames.append(d)
    if "predictions" in ia and not ia["predictions"].empty:
        d = ia["predictions"].copy()
        d.insert(0, "modele", "ia_xgboost")
        detail_frames.append(d)
    if "predictions" in dense and not dense["predictions"].empty:
        d = dense["predictions"].copy()
        d.insert(0, "modele", "ia_dense")
        detail_frames.append(d)

    out_path = out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="metrics", index=False)
        if detail_frames:
            # ne pas concatener des schemas trop differents : ecrire separement
            for frame in detail_frames:
                name = str(frame["modele"].iloc[0])[:20]
                frame.to_excel(writer, sheet_name=f"detail_{name}", index=False)
    return out_path
