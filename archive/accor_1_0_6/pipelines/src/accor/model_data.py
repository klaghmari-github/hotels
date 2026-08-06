"""
Construction de model_data.xlsx pour l'apprentissage XGBoost.

Entrée : all_data.xlsx (jointure hotel × année × mois).

Règles
------
1. Filtrer les hôtels sans aucune vente > 0.
2. Supprimer les colonnes constantes (inutiles au modèle).
3. Rôles de colonnes (couleurs UI) :
   - id_detail (jaune) : code, nom, marque, adresse, lat/lon, annee, mois…
   - descriptive : météo, équipements, brand, holidays, et le mix
     « saisi directeur » en *nombre de ventes* seulement
     (pct_categories_mois_*, pct_cat_*_nombre_ventes, …)
   - target (vert) : nombre_ventes, montant_ventes, nombre_paniers,
     nombre_produits + les autres pct ventes (montant, paniers, …)
4. Ordre des colonnes : id_detail | descriptive | target.
5. Tri : année → mois → marque → hôtel.
6. Dernière année calendaire → _is_eval=1 (hold-out) ; le reste = train.
7. Imputation uniquement ici (impute_model) : moyennes pilotes par
   catégorie de marque, sinon catégories adjacentes ; counts/flags → 0.
8. Cible principale de ranking / modèle final : **montant_ventes** (MAIN_TARGET).
   La marge n'est plus une cible IA : on applique la règle métier fixe
   ``montant_ventes = VENTES_SUR_ACHATS × montant_achats`` (défaut 2,5),
   donc ``montant_marge = montant_ventes × (1 − 1/2,5)``.

Sorties
-------
  data/model_data.xlsx
  data/model_data_meta.json   rôles, n_train / n_eval, listes de colonnes

Consommateurs : model_train, model_eval, model_explore, store (couleurs UI).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.impute_model import impute_for_model
from archive.accor_1_0_6.pipelines.src.accor.join_data import DATA_DIR
from archive.accor_1_0_6.pipelines.src.accor.schemas import get_schema

MODEL_DATA_FILENAME = "model_data.xlsx"
MODEL_DATA_SHEET = "model_data"
META_FILENAME = "model_data_meta.json"
HOTEL_SALES_MODEL_FILENAME = "hotel_sales_model_hotel.xlsx"

# Identifiants / detail (en-tetes jaunes) — pas des features du modele
ID_DETAIL_CANDIDATES = [
    "hotel_code",
    "hotel_name",
    "nom_hotel",
    "hotel_brand",
    "brand_category",
    "Marque",
    "logo_path",
    # NB : hotel_solution_* sont des **features descriptives** (pas id_detail)
    # pour que le modèle conditionne le CA à la solution installée.
    "hotel_adresse_postale_1",
    "hotel_adresse_postale_2",
    "hotel_code_postal",
    "hotel_city",
    "hotel_lat",
    "hotel_lon",
    "annee",
    "mois",
    "departement",
    "commune",
    "localisation",
]

# Colonnes non exploitables (arrays texte long / listes de jours)
DROP_ALWAYS = {
    "jours_feries",
    "jours_weekend",
    "jours_vacances_scolaires",
    "jours_vacances_hors_feries",
    "jours_holidays",
    "hotel_geo_source",
}

# Cible finale du stacking (modèle final + ranking) : CA / montant des ventes.
MAIN_TARGET = "montant_ventes"

# Règle métier IA : le prix / montant des ventes = k × montant d'achat.
# Marge produit = ventes − achats = ventes × (1 − 1/k).
VENTES_SUR_ACHATS = 2.5


def achats_from_ventes(montant_ventes: float, k: float = VENTES_SUR_ACHATS) -> float:
    """montant_achats tel que ventes = k × achats."""
    try:
        v = float(montant_ventes)
        kk = float(k) if k else VENTES_SUR_ACHATS
        if kk <= 0:
            return 0.0
        return v / kk
    except (TypeError, ValueError):
        return 0.0


def marge_from_ventes(montant_ventes: float, k: float = VENTES_SUR_ACHATS) -> float:
    """Marge produit = ventes − ventes/k."""
    try:
        v = float(montant_ventes)
        return v - achats_from_ventes(v, k)
    except (TypeError, ValueError):
        return 0.0


def ventes_from_marge(montant_marge: float, k: float = VENTES_SUR_ACHATS) -> float:
    """Inverse (modèles legacy entraînés sur la marge) : ventes = marge / (1 − 1/k)."""
    try:
        m = float(montant_marge)
        kk = float(k) if k else VENTES_SUR_ACHATS
        factor = 1.0 - (1.0 / kk) if kk else 0.0
        if factor <= 0:
            return 0.0
        return m / factor
    except (TypeError, ValueError):
        return 0.0

# Préfixe pour les indicateurs hôteliers exportés depuis DuckDB / main.ipynb
HOTEL_INDICATOR_PREFIX = "pilote_"

# Colonnes du sheet hotel_summary à joindre (hors clés)
HOTEL_SUMMARY_JOIN_COLS = (
    "solution",
    "metres_lineaires",
    "nombre_mois",
    "nombre_produits",
    "nombre_gammes",
    "nombre_types",
    "montant_achats",
    "montant_marge",
    "montant_ventes",
    "nombre_ventes",
    "montant_marge_par_mois",
    "montant_ventes_par_mois",
    "nombre_ventes_par_mois",
    "nombre_produits_par_metre_lineaire",
    "montant_marge_par_metre_lineaire",
    "montant_ventes_par_metre_lineaire",
)


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


def _is_mix_descriptive(col: str) -> bool:
    """
    Seuls les % en *nombre* (mix saisi par le directeur) sont descriptifs :

    - ``pct_categories_mois_f_b`` / ``n_f_b`` : part F_B vs N_F_B (nb sous-cat)
    - ``nombre_categories_mois_*`` : effectifs de sous-cat par type
    - ``pct_cat_*_nombre_ventes`` : part de la catégorie en nombre de ventes
    - ``pct_sous_cat_*_nombre_ventes`` : part de la sous-cat en nombre de ventes

    Tout autre pct (montant, paniers, produits…) est une **cible**.
    """
    if col in (
        "nombre_categories_mois_f_b",
        "nombre_categories_mois_n_f_b",
        "pct_categories_mois_f_b",
        "pct_categories_mois_n_f_b",
    ):
        return True
    # uniquement les pct en nombre de ventes pour cat / sous-cat
    if col.startswith("pct_cat_") and col.endswith("_nombre_ventes"):
        return True
    if col.startswith("pct_sous_cat_") and col.endswith("_nombre_ventes"):
        return True
    return False


def _is_sales_numeric_target(col: str, sales_cols: set[str]) -> bool:
    """
    Cibles = toutes les variables de ventes numériques intégrées depuis
    hotel_sales_data, **sauf** les pct_nombre cat/sous-cat (descriptives).
    """
    if col not in sales_cols:
        return False
    if col in ("hotel_code", "nom_hotel", "annee", "mois"):
        return False
    if _is_mix_descriptive(col):
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


def _filter_base_scenario(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne / hôtel : privilégie scenario_id=base si multi-scénarios."""
    if df is None or df.empty or "hotel_code" not in df.columns:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    out["hotel_code"] = out["hotel_code"].astype(str).str.strip()
    if "scenario_id" in out.columns:
        base = out[out["scenario_id"].astype(str).eq("base")]
        if not base.empty:
            out = base
    return out.drop_duplicates("hotel_code", keep="first")


def _attach_hotel_sales_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Joint les indicateurs pilotes 1-ligne/hôtel (DuckDB / main.ipynb)
    en features **descriptives** :

    - résumé ``hotel_summary`` → préfixe ``pilote_*`` (m_lin, solution, densités)
    - pivot large ``hotel_line`` → uniquement ``gamme__*`` et ``type__*``
      (assortiment agrégé ; les 12k ``produit__*`` restent hors modèle)

    Grain jointure : hotel_code (répliqué sur chaque mois de l'hôtel).
    La cible mensuelle principale est ``montant_ventes`` (pas rejointe depuis le résumé).
    """
    path = DATA_DIR / HOTEL_SALES_MODEL_FILENAME
    if not path.exists() or "hotel_code" not in frame.columns:
        return frame

    out = frame.copy()
    out["hotel_code"] = out["hotel_code"].astype(str).str.strip()

    # --- hotel_summary → pilote_* structurel ---
    try:
        summary = pd.read_excel(path, sheet_name="hotel_summary")
    except Exception:
        summary = pd.DataFrame()
    if not summary.empty and "hotel_code" in summary.columns:
        summary = _filter_base_scenario(summary)
        structural = [
            "solution",
            "metres_lineaires",
            "nombre_mois",
            "nombre_produits",
            "nombre_gammes",
            "nombre_types",
            "nombre_produits_par_metre_lineaire",
            "nombre_metres_lineaires_par_produit",
            "nombre_ventes_par_metre_lineaire",
            "montant_ventes_par_metre_lineaire",
            "montant_marge_par_metre_lineaire",
            "montant_achats_par_metre_lineaire",
        ]
        use = ["hotel_code"] + [c for c in structural if c in summary.columns]
        right = summary[use].copy()
        rename = {
            c: f"{HOTEL_INDICATOR_PREFIX}{c}"
            for c in use
            if c != "hotel_code"
        }
        right = right.rename(columns=rename)
        drop_existing = [
            c for c in right.columns if c != "hotel_code" and c in out.columns
        ]
        right = right.drop(columns=drop_existing, errors="ignore")
        out = out.merge(right, on="hotel_code", how="left")

    # --- hotel_line → gamme__* + type__* (pas produit__) ---
    try:
        line = pd.read_excel(path, sheet_name="hotel_line")
    except Exception:
        line = pd.DataFrame()
    if not line.empty and "hotel_code" in line.columns:
        line = _filter_base_scenario(line)
        keep = ["hotel_code"] + [
            c
            for c in line.columns
            if str(c).startswith("gamme__") or str(c).startswith("type__")
        ]
        # Dédupliquer noms de colonnes au cas où
        keep = list(dict.fromkeys(keep))
        right = line[[c for c in keep if c in line.columns]].copy()
        # Préfixe pilote_ pour clarté UI / rôles (descriptives)
        rename = {
            c: f"{HOTEL_INDICATOR_PREFIX}{c}"
            for c in right.columns
            if c != "hotel_code"
        }
        right = right.rename(columns=rename)
        drop_existing = [
            c for c in right.columns if c != "hotel_code" and c in out.columns
        ]
        right = right.drop(columns=drop_existing, errors="ignore")
        # Numériques : Excel peut lire des objets
        for c in right.columns:
            if c == "hotel_code":
                continue
            right[c] = pd.to_numeric(right[c], errors="coerce")
        out = out.merge(right, on="hotel_code", how="left")

    # Aligne hotel_solution_* sur la solution pilote (sales model / DuckDB).
    # Sinon H3546/H5586 (connected) restaient à 0 et le modèle CONNECTED
    # n'apprenait que sur H0373 → prédictions IA trop basses / R² catastrophique.
    sol_col = None
    if f"{HOTEL_INDICATOR_PREFIX}solution" in out.columns:
        sol_col = f"{HOTEL_INDICATOR_PREFIX}solution"
    elif "pilote_solution" in out.columns:
        sol_col = "pilote_solution"
    if sol_col is not None:
        sol = out[sol_col].astype(str).str.strip().str.lower()
        flag_map = {
            "simply": "hotel_solution_simply",
            "liberty": "hotel_solution_liberty",
            "connected": "hotel_solution_connected",
        }
        for key, flag in flag_map.items():
            if flag not in out.columns:
                out[flag] = 0
            mask = sol.eq(key)
            if mask.any():
                out.loc[mask, flag] = 1
        # un seul flag actif par ligne pilote
        for key, flag in flag_map.items():
            others = [f for k, f in flag_map.items() if k != key]
            mask = sol.eq(key)
            for o in others:
                if o in out.columns:
                    out.loc[mask, o] = 0

    return out


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

    # all_data peut contenir des nulls (sources non saisies) — on ne fill pas encore
    frame = all_data.copy()

    # 0. Indicateurs pilotes (main.ipynb) — jointure hôtel
    frame = _attach_hotel_sales_indicators(frame)

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
    protect = {
        "hotel_code",
        "annee",
        "mois",
        "hotel_brand",
        "nombre_ventes",
        "montant_ventes",
        "montant_marge",
        # Flags solution ROD (0/1) — ne pas drop même si quasi-constants
        "hotel_solution_simply",
        "hotel_solution_liberty",
        "hotel_solution_connected",
    }
    const = [c for c in const if c not in protect]
    frame = frame.drop(columns=const, errors="ignore")

    # 4. Classification + ordre (avant impute pour rôles stables)
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

    # 7. Imputation **uniquement ici** (moyenne marque / globale, 0 pour counts)
    #    Les fichiers sources et all_data restent avec des vides.
    frame, impute_report = impute_for_model(frame)

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
        "impute": {
            "n_filled": impute_report.get("n_filled"),
            "n_columns_touched": len(impute_report.get("columns") or {}),
        },
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
