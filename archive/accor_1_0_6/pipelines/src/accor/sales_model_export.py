#!/usr/bin/env python3
"""
Export des indicateurs pilotes (main.ipynb / DuckDB) vers Excel pour run_user / run_admin.

Sources (lecture **read-only** quand possible) :
  - duckdb/pilotes/base/base.duckdb
  - duckdb/pilotes/sim/sim.duckdb  (si non verrouillé)

Sorties (data/) :
  - hotel_sales_model_hotel.xlsx
      sheet ``hotel_summary``  : 1 ligne / hôtel (métriques globales + m_lin + solution)
      sheet ``hotel_line``     : 1 ligne / hôtel (pivot large produit__/gamme__/type__*)
      sheet ``meta``           : provenance, timestamp, n_hotels
  - hotel_sales_model_scenarios.xlsx  (si sim dispo)
      même structure + colonne scenario_id / scenario_label

Ces fichiers se joignent à hotel_data / all_data sur hotel_code pour
alimenter model_data (cibles multi-output + main_target = montant_ventes).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.data_io import DATA_DIR, PROJECT_ROOT

BASE_DB = PROJECT_ROOT / "duckdb" / "pilotes" / "base" / "base.duckdb"
SIM_DB = PROJECT_ROOT / "duckdb" / "pilotes" / "sim" / "sim.duckdb"

HOTEL_MODEL_FILENAME = "hotel_sales_model_hotel.xlsx"
SCENARIOS_FILENAME = "hotel_sales_model_scenarios.xlsx"

# Métriques hôtelières compactes (grain 1 ligne / hôtel) — utiles au ML
SUMMARY_COLS = [
    "hotel_code",
    "hotel_name",
    "solution",
    "metres_lineaires",
    "nombre_mois",
    "nombre_ventes",
    "nombre_produits",
    "nombre_gammes",
    "nombre_types",
    "montant_ventes",
    "montant_achats",
    "montant_marge",
    "montant_par_vente",
    "montant_achat_par_vente",
    "montant_marge_par_vente",
    "nombre_ventes_par_produit",
    "montant_ventes_par_produit",
    "montant_achats_par_produit",
    "montant_marge_par_produit",
    "nombre_ventes_par_mois",
    "montant_ventes_par_mois",
    "montant_achats_par_mois",
    "montant_marge_par_mois",
    "nombre_metres_lineaires_par_produit",
    "nombre_produits_par_metre_lineaire",
    "nombre_ventes_par_metre_lineaire",
    "montant_ventes_par_metre_lineaire",
    "montant_achats_par_metre_lineaire",
    "montant_marge_par_metre_lineaire",
]


def _connect_ro(path: Path) -> duckdb.DuckDBPyConnection:
    if not path.exists():
        raise FileNotFoundError(f"DuckDB introuvable : {path}")
    return duckdb.connect(str(path), read_only=True)


def _table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    n = con.sql(
        f"""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_catalog = current_database()
          AND table_name = '{name}'
        """
    ).fetchone()[0]
    return bool(n)


def load_hotel_summary(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """1 ligne / hôtel depuis v_ventes_mois + v_refs."""
    if not _table_exists(con, "v_ventes_mois"):
        raise RuntimeError("Vue v_ventes_mois absente — lancer SalesPilBase.main() d'abord.")
    has_refs = _table_exists(con, "v_refs")
    if has_refs:
        sql = """
            SELECT
                r.hotel_code,
                r.hotel_name,
                r.solution,
                r.metres_lineaires,
                v.* EXCLUDE (hotel_code)
            FROM v_refs r
            INNER JOIN v_ventes_mois v USING (hotel_code)
            ORDER BY r.hotel_code
        """
        # DuckDB EXCLUDE may fail on older versions — fallback
        try:
            df = con.sql(sql).df()
        except Exception:
            df = con.sql(
                """
                SELECT r.hotel_code, r.hotel_name, r.solution, r.metres_lineaires, v.*
                FROM v_refs r
                INNER JOIN v_ventes_mois v ON r.hotel_code = v.hotel_code
                ORDER BY r.hotel_code
                """
            ).df()
            # drop duplicate hotel_code if present twice
            if df.columns.duplicated().any():
                df = df.loc[:, ~df.columns.duplicated()]
    else:
        df = con.sql("SELECT * FROM v_ventes_mois ORDER BY hotel_code").df()

    # keep known cols first
    keep = [c for c in SUMMARY_COLS if c in df.columns]
    extra = [c for c in df.columns if c not in keep]
    return df[keep + extra]


def load_hotel_line(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Pivot large 1 ligne / hôtel si déjà matérialisé."""
    if _table_exists(con, "t_sales_model_base_line"):
        return con.sql("SELECT * FROM t_sales_model_base_line ORDER BY hotel_code").df()
    return pd.DataFrame()


def pivot_sales_model_base(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transforme v_sales_model_base (grain produit) → lignes hôtel (× scénario).

    Pour chaque (hôtel [, scénario]) :
      1. ligne ``mlin_source=hotel`` — m_lin **déclaré** corner (données d'origine)
      2. ligne ``mlin_source=sum_produits`` — m_lin **exposé** =
         Σ ``produit_metres_lineaires`` des produits encore présents

    Les ``produit_metres_lineaires`` doivent être **figés sur l'assortiment de
    base** (pas re-répartis 1/N après retrait). Ainsi, quand on retire des
    produits, Σ m_lin produits < m_lin hôtel : on montre la réduction du
    corner réellement exposé.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    def sanitize(name: object) -> str:
        s = str(name).strip().lower()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        return re.sub(r"_+", "_", s).strip("_")

    work = df.copy()
    # Ne pas recalculer 1/N_courant ici : ça re-remplit le corner.
    # Seulement si la colonne est absente (export base sans sim).
    if "produit_metres_lineaires" not in work.columns:
        if "produit_part_metres_lineaires" in work.columns and "metres_lineaires" in work.columns:
            work["produit_metres_lineaires"] = pd.to_numeric(
                work["metres_lineaires"], errors="coerce"
            ) * pd.to_numeric(work["produit_part_metres_lineaires"], errors="coerce")
        elif "produit_part_des_produits" in work.columns and "metres_lineaires" in work.columns:
            # fallback base seule (assortiment complet → somme ≈ m_lin hôtel)
            work["produit_metres_lineaires"] = pd.to_numeric(
                work["metres_lineaires"], errors="coerce"
            ) * pd.to_numeric(work["produit_part_des_produits"], errors="coerce")
        else:
            work["produit_metres_lineaires"] = pd.NA
    if "produit_part_metres_lineaires" not in work.columns and "produit_part_des_produits" in work.columns:
        work["produit_part_metres_lineaires"] = work["produit_part_des_produits"]

    scenario_cols = [
        c
        for c in (
            "scenario_id",
            "scenario_label",
            "scenario_kind",
            "scenario_rank",
            "n_removed",
            "removed_items",
        )
        if c in work.columns
    ]
    id_cols = scenario_cols + [
        c
        for c in ("hotel_code", "hotel_name", "solution", "metres_lineaires")
        if c in work.columns
    ]
    product_metrics = [c for c in work.columns if c.startswith("produit_") and c not in id_cols]
    for extra in ("produit_metres_lineaires", "produit_part_metres_lineaires"):
        if extra in work.columns and extra not in product_metrics:
            product_metrics.append(extra)
    gamme_metrics = [c for c in work.columns if c.startswith("gamme_") and c not in id_cols]
    type_metrics = [c for c in work.columns if c.startswith("type_") and c not in id_cols]
    global_metrics = [
        c
        for c in work.columns
        if not c.startswith(("produit_", "gamme_", "type_"))
        and c not in id_cols
        and c not in ("type", "gamme", "produit", "nombre_mois")
        and c not in scenario_cols
    ]

    if "scenario_id" in work.columns:
        group_keys = ["scenario_id", "hotel_code"]
    elif "scenario_label" in work.columns:
        group_keys = ["scenario_label", "hotel_code"]
    else:
        group_keys = ["hotel_code"]

    rows: list[dict[str, Any]] = []
    for _, g in work.groupby(group_keys, sort=False, dropna=False):
        row: dict[str, Any] = {}
        first = g.iloc[0]
        for col in id_cols:
            row[col] = first[col]
        for _, r in g.iterrows():
            prefix = f"produit__{sanitize(r['produit'])}__"
            for m in product_metrics:
                if m in r.index:
                    row[prefix + m] = r[m]
        subset_g = ["type", "gamme"] if "type" in g.columns else ["gamme"]
        for _, r in g.drop_duplicates(subset=subset_g).iterrows():
            prefix = f"gamme__{sanitize(r['gamme'])}__"
            for m in gamme_metrics:
                if m in r.index:
                    row[prefix + m] = r[m]
        if "type" in g.columns:
            for _, r in g.drop_duplicates(subset=["type"]).iterrows():
                prefix = f"type__{sanitize(r['type'])}__"
                for m in type_metrics:
                    if m in r.index:
                        row[prefix + m] = r[m]
        for m in global_metrics:
            row[f"global__{m}"] = first[m]

        row_hotel = dict(row)
        row_hotel["mlin_source"] = "hotel"
        rows.append(row_hotel)

        sum_prod_mlin = float(
            pd.to_numeric(g["produit_metres_lineaires"], errors="coerce").fillna(0).sum()
        )
        row_sum = dict(row)
        row_sum["metres_lineaires"] = sum_prod_mlin
        row_sum["mlin_source"] = "sum_produits"
        if row_sum.get("scenario_id") is not None:
            sid = str(row_sum["scenario_id"])
            if not sid.endswith("__mlin_sum"):
                row_sum["scenario_id"] = f"{sid}__mlin_sum"
        if row_sum.get("scenario_label") is not None:
            row_sum["scenario_label"] = f"{row_sum['scenario_label']} [m_lin=Σ produits]"
        rows.append(row_sum)

    return pd.DataFrame(rows).fillna(0)


def export_from_connection(
    con: duckdb.DuckDBPyConnection,
    *,
    scenario_id: str = "base",
    scenario_label: str = "base (pas de retrait)",
) -> dict[str, pd.DataFrame]:
    summary = load_hotel_summary(con)
    summary.insert(0, "scenario_id", scenario_id)
    summary.insert(1, "scenario_label", scenario_label)

    line = load_hotel_line(con)
    if line.empty and _table_exists(con, "v_sales_model_base"):
        long_df = con.sql("SELECT * FROM v_sales_model_base").df()
        line = pivot_sales_model_base(long_df)
    if not line.empty:
        line.insert(0, "scenario_id", scenario_id)
        line.insert(1, "scenario_label", scenario_label)

    meta = pd.DataFrame(
        [
            {"key": "scenario_id", "value": scenario_id},
            {"key": "scenario_label", "value": scenario_label},
            {"key": "exported_at", "value": datetime.now(timezone.utc).isoformat()},
            {"key": "n_hotels_summary", "value": len(summary)},
            {"key": "n_hotels_line", "value": len(line)},
            {"key": "n_cols_line", "value": len(line.columns) if not line.empty else 0},
            {"key": "main_target_intended", "value": "montant_ventes"},
        ]
    )
    return {"hotel_summary": summary, "hotel_line": line, "meta": meta}


def write_workbook(sheets: dict[str, pd.DataFrame], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            if frame is None:
                frame = pd.DataFrame()
            # Excel ~16k col limit — truncate line sheet with note if needed
            if name == "hotel_line" and frame.shape[1] > 16000:
                keep = list(frame.columns[:15990])
                frame = frame[keep]
            sheet = name[:31]
            frame.to_excel(writer, index=False, sheet_name=sheet)
    return path


def export_base(*, out: Path | None = None) -> dict[str, Any]:
    """Exporte la base pilote (read-only)."""
    out = out or (DATA_DIR / HOTEL_MODEL_FILENAME)
    con = _connect_ro(BASE_DB)
    try:
        sheets = export_from_connection(con, scenario_id="base", scenario_label="base")
    finally:
        con.close()
    write_workbook(sheets, out)
    return {
        "ok": True,
        "path": str(out),
        "n_hotels": len(sheets["hotel_summary"]),
        "n_line_cols": int(sheets["hotel_line"].shape[1]) if not sheets["hotel_line"].empty else 0,
        "scenario_id": "base",
    }


def export_sim_if_available(*, out: Path | None = None) -> dict[str, Any]:
    """Tente un export sim (échoue proprement si DB verrouillée)."""
    out = out or (DATA_DIR / SCENARIOS_FILENAME)
    try:
        con = _connect_ro(SIM_DB)
    except Exception as e:
        return {"ok": False, "error": f"sim.duckdb inaccessible (lock?) : {e}", "path": str(out)}
    try:
        sheets = export_from_connection(
            con,
            scenario_id="sim_current",
            scenario_label="simulation courante (état DuckDB sim)",
        )
    finally:
        con.close()
    write_workbook(sheets, out)
    return {
        "ok": True,
        "path": str(out),
        "n_hotels": len(sheets["hotel_summary"]),
        "n_line_cols": int(sheets["hotel_line"].shape[1]) if not sheets["hotel_line"].empty else 0,
    }


def export_all() -> dict[str, Any]:
    base = export_base()
    sim = export_sim_if_available()
    return {"base": base, "sim": sim}


def load_hotel_summary_excel(path: Path | None = None) -> pd.DataFrame:
    path = path or (DATA_DIR / HOTEL_MODEL_FILENAME)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name="hotel_summary")
    except ValueError:
        return pd.read_excel(path, sheet_name=0)


if __name__ == "__main__":
    import pprint

    pprint.pp(export_all())
