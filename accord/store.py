"""
Couche données Excel — Accord · Data & Model Studio.

Responsabilités
---------------
* Charger les fichiers ``data/*.xlsx`` en DataFrame (**cache** mémoire).
* Projeter sur le schéma UI (:func:`_project_to_schema`) pour que le fichier
  et l'affichage restent alignés.
* Paginer / filtrer pour l'UI (:func:`page_payload`).
* Coercer les types saisis (nombres, booléens 0/1, arrays JSON).
* Réécrire l'Excel après mutation (update / add / delete).
* Cas spéciaux :

  - **all_data** : fill nulls numériques ; rebuild via ``join_data``.
  - **model_data** : readonly ; stats + ``column_roles`` pour couleurs UI ;
    lignes ``_is_eval`` marquées pour le gras.

Thread-safety
-------------
Un ``RLock`` protège le cache : lectures/écritures concurrentes (plusieurs
requêtes Flask) ne corrompent pas le DataFrame ni le fichier disque.
"""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

import pandas as pd

from schemas import DatasetSchema, get_schema

# Verrou partagé pour le cache et les écritures disque
_lock = threading.RLock()

# Cache : dataset_id → DataFrame complet (toutes les colonnes du fichier,
# y compris celles non éditables — on ne les affiche pas mais on les conserve
# à la sauvegarde pour ne pas perdre de données calculées).
_cache: dict[str, pd.DataFrame] = {}

# Identifiant de l'onglet jointure (spécial : reconstruct possible)
JOINED_DATASET_ID = "all_data"


# ---------------------------------------------------------------------------
# Sérialisation cellules → JSON (pour le front)
# ---------------------------------------------------------------------------

def _cell_to_json(value: Any, *, numeric_null_as_zero: bool = False) -> Any:
    """
    Convertit une cellule pandas en type JSON-serializable.

    Gère NaN, numpy scalars, timestamps, listes, et chaînes JSON d'arrays
    (ex. listes de dates stockées comme ``'["2024-01-01"]'`` dans Excel).

    Si ``numeric_null_as_zero`` : les NaN numériques deviennent ``0`` (All Data).
    """
    # NaN / NA
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0 if numeric_null_as_zero else None
        if pd.isna(value):
            return 0 if numeric_null_as_zero else None
    except (TypeError, ValueError):
        pass

    if isinstance(value, (list, tuple)):
        return list(value)
    # numpy.int64 / float64 → type Python natif
    if hasattr(value, "item") and not isinstance(value, (bytes, str)):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip().replace("\u00a0", " ").strip()
        if text.lower() in {"", "nan", "none", "<na>"}:
            return "" if not numeric_null_as_zero else ""
        # Array stocké en texte Excel → liste pour l'UI
        if text.startswith("[") and text.endswith("]"):
            try:
                return json.loads(text.replace("'", '"'))
            except json.JSONDecodeError:
                return value
        return text
    return value


# ---------------------------------------------------------------------------
# Chargement
# ---------------------------------------------------------------------------

def _project_to_schema(frame: pd.DataFrame, schema: DatasetSchema) -> pd.DataFrame:
    """
    Aligne le DataFrame sur les colonnes affichées / éditables du schéma.

    - Onglet ``data`` (jointure) : toutes les colonnes du fichier.
    - Autres : uniquement ``editable_columns`` (ordre du schéma), colonnes
      manquantes créées à ``None``.
    """
    if schema.id == JOINED_DATASET_ID or not schema.editable_columns:
        return frame.copy() if frame is not None else pd.DataFrame()
    cols = list(schema.editable_columns)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=cols)
    data: dict[str, Any] = {}
    n = len(frame)
    for col in cols:
        if col in frame.columns:
            data[col] = frame[col].to_numpy()
        else:
            data[col] = [None] * n
    return pd.DataFrame(data)


def _load_raw(schema: DatasetSchema) -> pd.DataFrame:
    """Lit le fichier Excel du schéma (ou DataFrame vide si absent)."""
    # Onglet All Data : s'assurer que all_data.xlsx existe (jointure)
    if schema.id == JOINED_DATASET_ID:
        from join_data import ensure_data_xlsx

        ensure_data_xlsx(force_rebuild=False)
    if schema.id == "model_data":
        from model_data import ensure_model_data

        ensure_model_data(force=False)
    if schema.id == "proximity":
        # Crée hotel_proximity_data.xlsx si absent (calcul Overpass ou vide)
        try:
            from geo_proximity import ensure_hotel_proximity_data

            ensure_hotel_proximity_data(force_refresh=False)
        except Exception:
            pass
    if schema.id == "holidays":
        try:
            from geo_holidays import ensure_hotel_holidays_data

            ensure_hotel_holidays_data(force_refresh=False)
        except Exception:
            pass
    if schema.id == "sales_raw":
        # Importe le CSV archive une fois si le xlsx raw n'existe pas
        try:
            from sales_prep import ensure_raw_sales_from_archive

            ensure_raw_sales_from_archive()
        except Exception:
            pass

    path = schema.path
    if not path.exists():
        # Fichier manquant : squelette avec colonnes éditables pour permettre la saisie
        return pd.DataFrame(columns=list(schema.editable_columns or []))
    read_kwargs: dict[str, Any] = {}
    if schema.id == JOINED_DATASET_ID:
        # Codes texte forcés en str pour ne pas retomber en float NaN
        from join_data import _NON_NUMERIC_COLS

        read_kwargs["dtype"] = {c: str for c in _NON_NUMERIC_COLS}
    try:
        frame = pd.read_excel(path, sheet_name=schema.sheet, **read_kwargs)
    except ValueError:
        # Nom de feuille introuvable → première feuille
        frame = pd.read_excel(path, sheet_name=0, **read_kwargs)
    # All Data : Excel peut réintroduire des NaN numériques → re-fill 0
    if schema.id == JOINED_DATASET_ID:
        from join_data import fill_numeric_nulls

        # dtype=str peut produire "nan" littéral
        for c in frame.columns:
            if c in getattr(frame, "columns", []) and frame[c].dtype == object:
                frame[c] = frame[c].replace({"nan": "", "None": "", "<NA>": ""})
        frame = fill_numeric_nulls(frame)
    return _project_to_schema(frame, schema)


def get_frame(dataset_id: str, *, reload: bool = False) -> pd.DataFrame:
    """
    Retourne une **copie** du DataFrame en cache (ou recharge depuis le disque).

    On renvoie une copie pour éviter qu'un appelant mute le cache par accident
    hors des fonctions ``update_*`` protégées par le lock.
    """
    with _lock:
        if reload or dataset_id not in _cache:
            schema = get_schema(dataset_id)
            _cache[dataset_id] = _load_raw(schema)
        return _cache[dataset_id].copy()


def rebuild_joined_data(
    *,
    fill_weather: bool = False,
    fill_proximity: bool = False,
) -> dict[str, Any]:
    """
    Recalcule la jointure de **tous** les onglets et écrit ``all_data.xlsx``.

    Sources : brand, hotel, weather, sales, holidays.
    Invalide le cache de l'onglet ``all_data`` puis charge le nouveau fichier.
    """
    from join_data import build_joined_dataframe, save_joined_excel

    with _lock:
        # Invalider les caches sources pour lire les Excel à jour
        for src_id in (
            "brand",
            "hotel",
            "weather",
            "proximity",
            "sales",
            "holidays",
            JOINED_DATASET_ID,
            "model_data",
        ):
            _cache.pop(src_id, None)
        frame = build_joined_dataframe(
            fill_weather=fill_weather,
            fill_proximity=fill_proximity,
        )
        path = save_joined_excel(frame)
        _cache[JOINED_DATASET_ID] = frame
    return {
        "ok": True,
        "path": str(path),
        "filename": path.name,
        "rows": len(frame),
        "columns": list(frame.columns),
        "n_columns": len(frame.columns),
    }


def _ensure_editable_cols(frame: pd.DataFrame, schema: DatasetSchema) -> list[str]:
    """
    Colonnes exposées à l'UI (= schéma éditable, ou tout pour All Data).

    Les DataFrames sont déjà projetés sur le schéma à la charge / sauvegarde :
    fichier Excel ↔ colonnes affichées.
    """
    if schema.id == JOINED_DATASET_ID or not schema.editable_columns:
        # Clés en tête si présentes, puis le reste dans l'ordre du fichier
        keys = [c for c in schema.key_columns if c in frame.columns]
        rest = [c for c in frame.columns if c not in keys]
        return keys + rest
    # Toujours l'ordre du schéma (colonnes créées vides si absentes)
    return list(schema.editable_columns)


# ---------------------------------------------------------------------------
# Pagination / filtre (lecture UI)
# ---------------------------------------------------------------------------

def page_payload(
    dataset_id: str,
    *,
    page: int = 1,
    page_size: int | None = None,
    q: str = "",
) -> dict[str, Any]:
    """
    Construit la charge utile d'une page pour le front.

    Étapes
    ------
    1. Charger le DataFrame complet (cache).
    2. Ne garder que les colonnes éditables.
    3. Filtrer éventuellement par texte ``q`` (toutes colonnes).
    4. Découper [start:end] selon page / page_size.
    5. Annoter chaque ligne avec ``_index`` (index pandas pour les updates).
    """
    schema = get_schema(dataset_id)
    frame = get_frame(dataset_id)
    # All Data : jamais de null numériques dans l'UI
    if dataset_id == JOINED_DATASET_ID:
        from join_data import fill_numeric_nulls

        frame = fill_numeric_nulls(frame)
        with _lock:
            _cache[JOINED_DATASET_ID] = frame
    cols = _ensure_editable_cols(frame, schema)
    view = frame[cols].copy() if cols else frame.copy()

    # Filtre plein-texte (insensible à la casse) sur toutes les colonnes affichées
    if q and not view.empty:
        mask = pd.Series(False, index=view.index)
        for c in view.columns:
            mask = mask | view[c].astype(str).str.contains(q, case=False, na=False)
        view = view[mask]

    total = len(view)
    size = page_size or schema.page_size
    size = max(1, min(int(size), 200))  # borne pour éviter de charger trop d'UI
    pages = max(1, math.ceil(total / size)) if total else 1
    page = max(1, min(int(page), pages))
    start = (page - 1) * size
    end = start + size
    chunk = view.iloc[start:end]

    # Index absolus dans le DataFrame d'origine (pas 0..n de la page)
    abs_indices = [int(i) for i in chunk.index.tolist()]

    num_zero = dataset_id in (JOINED_DATASET_ID, "model_data")
    # Rôles de colonnes (model_data)
    column_roles: dict[str, str] = {}
    model_stats: dict[str, Any] = {}
    if dataset_id == "model_data":
        from model_data import load_model_data_meta

        md_meta = load_model_data_meta()
        column_roles = dict(md_meta.get("column_roles") or {})
        if "_is_eval" not in column_roles and "_is_eval" in cols:
            column_roles["_is_eval"] = "meta"
        model_stats = {
            "n_id_detail": md_meta.get("n_id_detail"),
            "n_descriptive": md_meta.get("n_descriptive"),
            "n_target": md_meta.get("n_target"),
            "n_train": md_meta.get("n_train"),
            "n_eval": md_meta.get("n_eval"),
            "eval_year": md_meta.get("eval_year"),
            "main_target": md_meta.get("main_target"),
            "id_detail_columns": md_meta.get("id_detail_columns") or [],
            "descriptive_columns": md_meta.get("descriptive_columns") or [],
            "target_columns": md_meta.get("target_columns") or [],
        }
        # colonnes affichées : cacher _is_eval en en-tête data mais garder pour bold
        display_cols = [c for c in cols if c != "_is_eval"]
    else:
        display_cols = cols

    rows = []
    for pos, (idx, series) in enumerate(chunk.iterrows()):
        is_eval_row = False
        if "_is_eval" in series.index:
            try:
                is_eval_row = int(series["_is_eval"]) == 1
            except Exception:
                is_eval_row = bool(series["_is_eval"])
        row_dict: dict[str, Any] = {
            "_index": int(idx),          # clé de mise à jour côté serveur
            "_row": start + pos + 1,     # numéro humain 1-based (affichage)
            "_is_eval": is_eval_row,
        }
        for c in display_cols:
            val = _cell_to_json(series[c], numeric_null_as_zero=num_zero)
            # All Data / model_data : si colonne numérique encore null → 0
            if num_zero and val is None:
                # texte / arrays restent None → ""
                if c in (
                    "hotel_code",
                    "hotel_name",
                    "nom_hotel",
                    "hotel_brand",
                    "hotel_city",
                    "hotel_adresse_postale_1",
                    "hotel_adresse_postale_2",
                    "hotel_code_postal",
                    "departement",
                    "commune",
                    "jours_feries",
                    "jours_weekend",
                    "jours_vacances_scolaires",
                    "jours_vacances_hors_feries",
                    "jours_holidays",
                ):
                    val = "" if not str(c).startswith("jours_") else []
                else:
                    val = 0
            row_dict[c] = val
        rows.append(row_dict)

    return {
        "dataset_id": dataset_id,
        "label": schema.label,
        "description": schema.description,
        "filename": schema.filename,
        "columns": display_cols,
        "key_columns": [c for c in schema.key_columns if c in display_cols],
        "boolean_columns": [c for c in schema.boolean_columns if c in display_cols],
        "array_columns": [c for c in schema.array_columns if c in display_cols],
        "column_roles": column_roles,
        "model_stats": model_stats,
        "readonly": bool(schema.readonly),
        "page": page,
        "page_size": size,
        "total_rows": total,
        "total_pages": pages,
        "rows": rows,
        "abs_indices": abs_indices,
    }


# ---------------------------------------------------------------------------
# Coercion des valeurs saisies (front → type Excel)
# ---------------------------------------------------------------------------

def _coerce_value(col: str, value: Any, schema: DatasetSchema) -> Any:
    """
    Normalise une valeur envoyée par l'UI avant écriture dans le DataFrame.

    - Arrays → JSON string (compatible cellule Excel)
    - Booléens → 0 / 1
    - Nombres en string → int / float si possible
    - Chaîne vide → None (cellule vide)
    """
    if value is None or value == "":
        return None

    # --- Listes de jours (holidays) ---
    if col in schema.array_columns:
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return "[]"
            if text.startswith("["):
                # Déjà du JSON
                return text
            # Saisie libre "2024-01-01, 2024-05-01"
            parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
            return json.dumps(parts, ensure_ascii=False)
        return "[]"

    # --- Flags 0/1 ---
    if col in schema.boolean_columns:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip().lower()
        if s in {"1", "true", "oui", "yes", "x"}:
            return 1
        if s in {"0", "false", "non", "no", ""}:
            return 0
        try:
            return int(float(s))
        except ValueError:
            return 0

    # --- Numérique ou texte ---
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        try:
            # float si décimal / notation scientifique, sinon int
            if "." in text or "e" in text.lower():
                return float(text)
            return int(text)
        except ValueError:
            return text
    return value


# ---------------------------------------------------------------------------
# Mutations + sauvegarde
# ---------------------------------------------------------------------------

def update_rows(dataset_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Applique les modifications de lignes (par ``_index``) puis écrit l'Excel.

    Les clés techniques ``_index``, ``_row``, etc. sont ignorées.
    Les colonnes hors schéma éditable sont ignorées (sécurité).
    """
    schema = get_schema(dataset_id)
    with _lock:
        # Travail sur le cache réel (pas une copie) pour persister les changements
        if dataset_id not in _cache:
            _cache[dataset_id] = _load_raw(schema)
        frame = _cache[dataset_id]
        editable = set(_ensure_editable_cols(frame, schema))

        for row in rows:
            if "_index" not in row:
                continue
            idx = int(row["_index"])
            if idx not in frame.index:
                continue
            for col, val in row.items():
                if col.startswith("_"):
                    continue
                if col not in editable:
                    continue
                if col not in frame.columns:
                    # Colonne déclarée éditable mais absente → on la crée
                    frame[col] = None
                frame.at[idx, col] = _coerce_value(col, val, schema)

        _cache[dataset_id] = frame
        path = _save_excel(dataset_id, frame, schema)
    return {"ok": True, "saved_to": str(path), "updated": len(rows)}


def add_row(dataset_id: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ajoute une ligne en fin de table (valeurs optionnelles) et sauvegarde."""
    schema = get_schema(dataset_id)
    values = values or {}
    with _lock:
        if dataset_id not in _cache:
            _cache[dataset_id] = _load_raw(schema)
        frame = _cache[dataset_id]
        editable = _ensure_editable_cols(frame, schema) or list(schema.editable_columns)

        # Construire la nouvelle ligne : toutes les colonnes existantes + éditables
        new: dict[str, Any] = {}
        for col in frame.columns:
            if col in values:
                new[col] = _coerce_value(col, values[col], schema)
            else:
                new[col] = None
        for col in editable:
            if col not in new:
                new[col] = (
                    _coerce_value(col, values.get(col), schema)
                    if col in values
                    else None
                )

        frame = pd.concat([frame, pd.DataFrame([new])], ignore_index=True)
        _cache[dataset_id] = frame
        path = _save_excel(dataset_id, frame, schema)
        new_index = int(frame.index[-1])
    return {"ok": True, "index": new_index, "saved_to": str(path)}


def delete_rows(dataset_id: str, indices: list[int]) -> dict[str, Any]:
    """Supprime les lignes aux index donnés, réindexe, sauvegarde."""
    schema = get_schema(dataset_id)
    with _lock:
        if dataset_id not in _cache:
            _cache[dataset_id] = _load_raw(schema)
        frame = _cache[dataset_id]
        drop = [i for i in indices if i in frame.index]
        frame = frame.drop(index=drop).reset_index(drop=True)
        _cache[dataset_id] = frame
        path = _save_excel(dataset_id, frame, schema)
    return {"ok": True, "deleted": len(drop), "saved_to": str(path)}


def reload_dataset(dataset_id: str) -> dict[str, Any]:
    """Force le rechargement depuis le disque (ignore le cache)."""
    frame = get_frame(dataset_id, reload=True)
    schema = get_schema(dataset_id)
    return {
        "ok": True,
        "rows": len(frame),
        "columns": list(frame.columns),
        "editable": _ensure_editable_cols(frame, schema),
    }


def _save_excel(dataset_id: str, frame: pd.DataFrame, schema: DatasetSchema) -> Path:
    """
    Écrit le DataFrame dans le fichier Excel du schéma.

    Les datasets éditables sont **projetés** sur ``editable_columns`` pour que
    le fichier Excel corresponde exactement à l'UI. Les feuilles secondaires
    (ex. ``resume_annuel``) sont préservées.
    """
    path = schema.path
    path.parent.mkdir(parents=True, exist_ok=True)

    # Préserver les feuilles secondaires (non éditées par l'UI)
    other_sheets: dict[str, pd.DataFrame] = {}
    if path.exists():
        try:
            xl = pd.ExcelFile(path)
            for name in xl.sheet_names:
                if name != schema.sheet and name != str(schema.sheet):
                    other_sheets[name] = pd.read_excel(path, sheet_name=name)
        except Exception:
            # Fichier corrompu / verrouillé : on écrase au mieux la feuille principale
            pass

    to_write = _project_to_schema(frame, schema)
    sheet_name = schema.sheet if isinstance(schema.sheet, str) else "Sheet1"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        to_write.to_excel(writer, index=False, sheet_name=sheet_name)
        for name, df in other_sheets.items():
            # Excel limite les noms de feuille à 31 caractères
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return path
