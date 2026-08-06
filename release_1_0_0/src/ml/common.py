"""
Utilitaires communs ML : dataset, features descriptives, metriques.

Partages par CatBoost, XGBoost et le super-modele.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths
from src.pipeline.scope import is_excluded

CONTEXT_FEATURES = [
    "hotel_nb_chambres",
    "hotel_to_annuel",
    "hotel_guests_per_chambre",
    "metres_lineaires",
]

TARGETS = (
    ("montant_ventes_par_mois", "Montant des ventes mensuel"),
    ("montant_marge_par_mois", "Marge mensuelle selon prix marche"),
    ("montant_marge_selon_coef_par_mois", "Marge mensuelle selon coefficient fixe"),
)

# Cibles utilisees pour le stacking super-modele (comparaison commune = selon coef)
SUPER_TARGETS = (
    ("montant_ventes_par_mois", "Montant des ventes mensuel"),
    ("montant_marge_selon_coef_par_mois", "Marge mensuelle selon coefficient fixe"),
)


def mix_columns(df: pd.DataFrame) -> list[str]:
    return sorted(
        c
        for c in df.columns
        if (c.startswith("type_") or c.startswith("gamme_"))
        and c.endswith("_part_natures")
    )


def _attach_brand_features(df: pd.DataFrame, cp) -> pd.DataFrame:
    """
    Jointure brand (marque hotel → stats marque).
    Match exact hotel_brand = Marque (UPPER trim).
    """
    try:
        brands = cp.p_table_view("t_hotel_brand_data").df()
        hotels = cp.p_table_view("t_hotel_data").df()
    except Exception:
        return df

    if brands.empty or hotels.empty or "hotel_code" not in hotels.columns:
        return df

    h = hotels.copy()
    h["hotel_code"] = h["hotel_code"].astype(str)
    brand_col = "hotel_brand" if "hotel_brand" in h.columns else None
    if not brand_col:
        return df
    h["_brand_key"] = h[brand_col].astype(str).str.upper().str.strip()

    b = brands.copy()
    marque_col = "Marque" if "Marque" in b.columns else (
        "marque" if "marque" in b.columns else None
    )
    if not marque_col:
        return df
    b["_brand_key"] = b[marque_col].astype(str).str.upper().str.strip()

    num_cols = []
    for c in b.columns:
        if c in {marque_col, "_brand_key", "logo_path"}:
            continue
        coerced = pd.to_numeric(b[c], errors="coerce")
        if coerced.notna().any():
            b[c] = coerced
            num_cols.append(c)

    if not num_cols:
        return df

    br = b[["_brand_key", *num_cols]].drop_duplicates("_brand_key", keep="first")
    rename = {c: f"br_{str(c).lower().replace(' ', '_')}" for c in num_cols}
    br = br.rename(columns=rename)

    map_brand = h[["hotel_code", "_brand_key"]].drop_duplicates("hotel_code")
    feat = map_brand.merge(br, on="_brand_key", how="left").drop(columns=["_brand_key"])

    out = df.copy()
    out["hotel_code"] = out["hotel_code"].astype(str)
    # drop existing br_ if re-load
    drop_br = [c for c in out.columns if str(c).startswith("br_")]
    if drop_br:
        out = out.drop(columns=drop_br)
    out = out.merge(feat, on="hotel_code", how="left")
    return out


def load_ml_dataset(
    paths: Paths | None = None,
    factory: PipelineFactory | None = None,
    *,
    filter_excluded: bool = True,
    prefer_rich: bool = True,
    mode: str | None = None,
    attach_brand: bool = False,
) -> pd.DataFrame:
    """
    Charge le dataset ML.

    Modes:
      - mode=\"sim_v2\" / prefer_rich=False : liste simulations sim_v2
        (v_ml_training_dataset / pivot) — ml1
      - mode=\"rich\" / prefer_rich=True : t_rich_data
        (sim_v2 + hotel_data + proximity + weather moyennee + holidays)
      - attach_brand=True : ajoute features marque (br_*) — ml2

    Weather/holidays sont deja moyennees par hotel dans le pipeline rich
    (multi-lignes mensuelles → AVG).
    """
    paths = (paths or Paths()).ensure()
    factory = factory or PipelineFactory(paths)

    if mode is not None:
        m = str(mode).lower().strip()
        if m in {"sim_v2", "ml1", "skinny", "v_ml"}:
            prefer_rich = False
            attach_brand = False
        elif m in {"rich", "ml2"}:
            prefer_rich = True
            if m == "ml2":
                attach_brand = True

    cp = factory.open(read_only=False)
    try:
        source = "v_ml_training_dataset"
        if prefer_rich:
            try:
                df = cp.p_table_view("t_rich_data").df()
                source = "t_rich_data"
            except Exception:
                df = cp.p_table_view("v_ml_training_dataset").df()
        else:
            df = cp.p_table_view("v_ml_training_dataset").df()

        if attach_brand:
            df = _attach_brand_features(df, cp)
            if any(str(c).startswith("br_") for c in df.columns):
                source = f"{source}+brand"
    finally:
        cp.close()

    if df.empty:
        raise ValueError(
            "Dataset ML vide — construire le dataset pivot sim_v2 / t_rich_data."
        )

    df = df.copy()
    df.attrs["ml_source"] = source
    df["hotel_code"] = df["hotel_code"].astype(str)
    df["solution"] = df["solution"].astype(str)
    if "is_observation" in df.columns:
        df["is_observation"] = df["is_observation"].astype(bool)

    if filter_excluded:
        df = df.loc[~df["hotel_code"].map(is_excluded)].reset_index(drop=True)

    # coerce numeriques (features + cibles)
    exclude_txt = {
        "scenario_id",
        "hotel_code",
        "solution",
        "is_observation",
        "scenario_removed_natures",
    }
    for col in df.columns:
        if col in exclude_txt:
            continue
        if col in {t for t, _ in TARGETS} or col.startswith(
            ("type_", "gamme_", "categorie_", "hd_", "px_", "wx_", "hol_", "br_")
        ) or col in CONTEXT_FEATURES:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in CONTEXT_FEATURES:
        if col in df.columns:
            series = df[col]
            med = series.median()
            df[col] = series.fillna(0.0 if pd.isna(med) else float(med))

    for col in mix_columns(df):
        df[col] = df[col].fillna(0.0)

    for name, _ in TARGETS:
        if name in df.columns:
            df[name] = df[name].fillna(0.0)

    # enrichissements : mediane par colonne puis 0
    for col in df.columns:
        if col in exclude_txt or col in {t for t, _ in TARGETS}:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            med = df[col].median()
            df[col] = df[col].fillna(0.0 if pd.isna(med) else float(med))

    return df


def feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Variables descriptives :
    - contexte + mix (toujours)
    - toutes colonnes numeriques supplementaires (hd_/px_/wx_/hol_/…)
    - dummies solution
    """
    exclude = {
        "scenario_id",
        "hotel_code",
        "solution",
        "is_observation",
        "scenario_removed_natures",
    } | {t for t, _ in TARGETS}

    numeric_cols = [
        c
        for c in df.columns
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c])
    ]
    # priorite contexte + mix en tete (lisibilite meta)
    mix_cols = mix_columns(df)
    ordered = []
    for c in [*CONTEXT_FEATURES, *mix_cols]:
        if c in numeric_cols and c not in ordered:
            ordered.append(c)
    for c in sorted(numeric_cols):
        if c not in ordered:
            ordered.append(c)

    base = df[ordered].astype(float).fillna(0.0)
    dummies = pd.get_dummies(df["solution"], prefix="solution", dtype=float)
    features = pd.concat([base, dummies], axis=1)
    features = features.reindex(sorted(features.columns), axis=1)
    return features, features.columns.tolist()


def metrics_frame(
    predictions: pd.DataFrame,
    targets: tuple[tuple[str, str], ...] = TARGETS,
) -> pd.DataFrame:
    rows = []
    for target, label in targets:
        col_r = f"{target}_reel"
        col_p = f"{target}_predit"
        if col_r not in predictions.columns or col_p not in predictions.columns:
            continue
        y_true = predictions[col_r].to_numpy(dtype=float)
        y_pred = predictions[col_p].to_numpy(dtype=float)
        err = y_pred - y_true
        nz = np.abs(y_true) > 1e-9
        rows.append(
            {
                "target": target,
                "target_label": label,
                "nombre_hotels": len(predictions),
                "mae": float(mean_absolute_error(y_true, y_pred)),
                "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
                "mape": (
                    float(np.mean(np.abs(err[nz] / y_true[nz])) * 100.0)
                    if nz.any()
                    else float("nan")
                ),
                "biais": float(np.mean(err)),
            }
        )
    return pd.DataFrame(rows)


def build_feature_row(
    feature_names: list[str],
    feature_row: dict[str, float],
    solution: str,
) -> pd.DataFrame:
    row = {name: 0.0 for name in feature_names}
    for k, v in feature_row.items():
        if k in row:
            row[k] = float(v)
    sol = str(solution or "simply").lower()
    sol_col = f"solution_{sol}"
    for name in feature_names:
        if name.startswith("solution_"):
            row[name] = (
                1.0
                if name == sol_col or name.endswith(f"_{sol}") or name == f"solution_{sol}"
                else 0.0
            )
    return pd.DataFrame([row])[feature_names].astype(float)
