"""
Construction de ``model_data.xlsx`` pour l'apprentissage.

Règles
------
1. Partir de ``all_data.xlsx``
2. Garder uniquement les hôtels ayant au moins une ligne avec ventes > 0
3. Supprimer les colonnes constantes (une seule valeur)
4. Rôles de colonnes :
   - **id_detail** (jaune) : identifiants + détail hôtel + année + mois
   - **descriptive** : features numériques / contextuelles
   - **target** : variables de vente numériques (sauf pct nombre_ventes cat/sous-cat)
5. Ordre : id_detail | descriptive | target
6. Tri : année, mois, marque, hôtel
7. Dernière année = évaluation ; reste = apprentissage
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from join_data import DATA_DIR, fill_numeric_nulls
from schemas import get_schema

MODEL_DATA_FILENAME = "model_data.xlsx"
MODEL_DATA_SHEET = "model_data"
META_FILENAME = "model_data_meta.json"

# Identifiants / détail (en-têtes jaunes)
ID_DETAIL_CANDIDATES = [
    "hotel_code",
    "hotel_name",
    "nom_hotel",
    "hotel_brand",
    "Marque",
    "hotel_adresse_postale_1",
    "hotel_adresse_postale_2",
    "hotel_code_postal",
    "hotel_city",
    "hotel_lat",
    "hotel_lon",
    "annee",
    "mois",
    "zone_scolaire",
    "departement",
    "commune",
    "localisation",
]

# Colonnes non exploitables (arrays texte long)
DROP_ALWAYS = {
    "jours_feries",
    "jours_vacances_scolaires",
    "jours_vacances_hors_feries",
    "hotel_geo_source",
}

MAIN_TARGET = "montant_ventes"


def _sales_columns() -> list[str]:
    """Colonnes présentes dans hotel_sales_data (hors clés pures)."""
    sales_path = DATA_DIR / "hotel_sales_data.xlsx"
    if not sales_path.exists():
        return []
    try:
        frame = pd.read_excel(sales_path, sheet_name="hotel_sales", nrows=0)
    except ValueError:
        frame = pd.read_excel(sales_path, sheet_name=0, nrows=0)
    return list(frame.columns)


def _is_excluded_target_pct(col: str) -> bool:
    """
    Pct en *nombre de ventes* pour catégories / sous-catégories :
    exclus des cibles (restent descriptives si présentes).
    """
    if col in ("pct_categories_mois_f_b", "pct_categories_mois_n_f_b"):
        return False  # mix nb sous-cat distinctes, pas pct volume ventes
    if col.startswith("pct_cat_") and col.endswith("_nombre_ventes"):
        return True
    if col.startswith("pct_sous_cat_") and col.endswith("_nombre_ventes"):
        return True
    return False


def _is_sales_numeric_target(col: str, sales_cols: set[str]) -> bool:
    if col not in sales_cols:
        return False
    if col in ("hotel_code", "nom_hotel", "annee", "mois"):
        return False
    if _is_excluded_target_pct(col):
        return False
    return True


def _hotel_has_sales(frame: pd.DataFrame) -> pd.Series:
    """True pour les hotel_code ayant au moins une vente > 0."""
    if "hotel_code" not in frame.columns:
        return pd.Series(dtype=bool)
    if "nombre_ventes" in frame.columns:
        sales = pd.to_numeric(frame["nombre_ventes"], errors="coerce").fillna(0)
    elif "montant_ventes" in frame.columns:
        sales = pd.to_numeric(frame["montant_ventes"], errors="coerce").fillna(0)
    else:
        return frame["hotel_code"].notna()
    has = frame.assign(_s=sales).groupby("hotel_code")["_s"].transform(lambda s: (s > 0).any())
    return has.astype(bool)


def _constant_columns(frame: pd.DataFrame) -> list[str]:
    out = []
    for col in frame.columns:
        n = frame[col].nunique(dropna=False)
        if n <= 1:
            out.append(col)
    return out


def classify_columns(frame: pd.DataFrame) -> dict[str, list[str]]:
    """Classe les colonnes en id_detail / descriptive / target."""
    sales_cols = set(_sales_columns())
    id_detail = [c for c in ID_DETAIL_CANDIDATES if c in frame.columns]
    targets: list[str] = []
    for c in frame.columns:
        if c in id_detail or c in DROP_ALWAYS or c.startswith("_"):
            continue
        if not _is_sales_numeric_target(c, sales_cols):
            continue
        if pd.api.types.is_numeric_dtype(frame[c]):
            targets.append(c)
        else:
            coerced = pd.to_numeric(frame[c], errors="coerce")
            if coerced.notna().mean() > 0.5:
                targets.append(c)

    used = set(id_detail) | set(targets)
    descriptive = [
        c
        for c in frame.columns
        if c not in used and c not in DROP_ALWAYS and not c.startswith("_")
    ]
    return {
        "id_detail": id_detail,
        "descriptive": descriptive,
        "target": targets,
    }


def build_model_dataframe(all_data: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Construit le DataFrame model_data + meta."""
    if all_data is None:
        path = DATA_DIR / "all_data.xlsx"
        if not path.exists():
            raise FileNotFoundError("all_data.xlsx introuvable — reconstruisez All Data d'abord.")
        try:
            all_data = pd.read_excel(path, sheet_name="all_data")
        except ValueError:
            all_data = pd.read_excel(path, sheet_name=0)

    frame = fill_numeric_nulls(all_data.copy())

    # 1. Hôtels avec ventes uniquement
    if "hotel_code" in frame.columns:
        mask = _hotel_has_sales(frame)
        frame = frame.loc[mask].copy()

    # 2. Drop arrays / inutiles
    drop = [c for c in DROP_ALWAYS if c in frame.columns]
    frame = frame.drop(columns=drop, errors="ignore")

    # 3. Colonnes constantes
    const = _constant_columns(frame)
    # ne pas dropper les clés minimales même si constantes (peu probable)
    protect = {"hotel_code", "annee", "mois", "hotel_brand", "nombre_ventes", "montant_ventes"}
    const = [c for c in const if c not in protect]
    frame = frame.drop(columns=const, errors="ignore")

    # 4. Classification + ordre
    roles = classify_columns(frame)
    ordered = roles["id_detail"] + roles["descriptive"] + roles["target"]
    # colonnes restantes éventuelles
    rest = [c for c in frame.columns if c not in ordered]
    ordered = ordered + rest
    frame = frame[[c for c in ordered if c in frame.columns]]

    # Re-class rest into descriptive
    roles = classify_columns(frame)

    # 5. Tri
    sort_cols = [c for c in ("annee", "mois", "hotel_brand", "hotel_code", "nom_hotel") if c in frame.columns]
    if sort_cols:
        frame = frame.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)
    else:
        frame = frame.reset_index(drop=True)

    # 6. Split année
    if "annee" in frame.columns:
        years = pd.to_numeric(frame["annee"], errors="coerce")
        eval_year = int(years.max()) if years.notna().any() else None
        is_eval = (years == eval_year) if eval_year is not None else pd.Series(False, index=frame.index)
    else:
        eval_year = None
        is_eval = pd.Series(False, index=frame.index)

    frame = frame.copy()
    frame["_is_eval"] = is_eval.astype(int)
    # _is_eval is meta for UI, not a feature — keep at end of id or as flag
    # Put flag after id block for sorting display but classify separately

    n_train = int((~is_eval).sum())
    n_eval = int(is_eval.sum())

    meta = {
        "id_detail_columns": roles["id_detail"],
        "descriptive_columns": roles["descriptive"],
        "target_columns": roles["target"],
        "n_id_detail": len(roles["id_detail"]),
        "n_descriptive": len(roles["descriptive"]),
        "n_target": len(roles["target"]),
        "n_rows": len(frame),
        "n_train": n_train,
        "n_eval": n_eval,
        "eval_year": eval_year,
        "dropped_constant": const,
        "dropped_no_sales_hotels": True,
        "main_target": MAIN_TARGET if MAIN_TARGET in roles["target"] else (
            roles["target"][0] if roles["target"] else None
        ),
        "column_roles": {
            c: (
                "id_detail"
                if c in roles["id_detail"]
                else "target"
                if c in roles["target"]
                else "descriptive"
                if c in roles["descriptive"]
                else "meta"
            )
            for c in frame.columns
        },
    }
    return frame, meta


def save_model_data(frame: pd.DataFrame | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Écrit model_data.xlsx + meta json."""
    if frame is None or meta is None:
        frame, meta = build_model_dataframe()
    path = DATA_DIR / MODEL_DATA_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    # ne pas écrire _is_eval comme colonne d'apprentissage « feature » mais utile UI
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=MODEL_DATA_SHEET)
    meta_path = DATA_DIR / META_FILENAME
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "meta_path": str(meta_path),
        "rows": len(frame),
        "columns": list(frame.columns),
        "n_columns": len(frame.columns),
        **{k: meta[k] for k in (
            "n_id_detail", "n_descriptive", "n_target", "n_train", "n_eval", "eval_year",
            "id_detail_columns", "descriptive_columns", "target_columns", "main_target",
            "column_roles", "dropped_constant",
        ) if k in meta},
    }


def load_model_data_meta() -> dict[str, Any]:
    meta_path = DATA_DIR / META_FILENAME
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {}


def ensure_model_data(*, force: bool = False) -> Path:
    path = DATA_DIR / MODEL_DATA_FILENAME
    if force or not path.exists():
        save_model_data()
    return path


def rebuild_model_data() -> dict[str, Any]:
    """Reconstruit model_data depuis all_data à jour."""
    return save_model_data()
