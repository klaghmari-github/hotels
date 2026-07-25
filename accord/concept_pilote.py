#!/usr/bin/env python3
"""
Construction de ``concept_pilote.xlsx`` — indicateurs annuels par hôtel.

Grain
-----
``hotel_code`` × ``annee``

Colonnes
--------
* Identité : hotel_code, hotel_name, hotel_brand
* Exploitation (hotel_data + défauts marque) :
  nb_chambres, taux_occupation, guests_per_chambre,
  clients_jour, clients_mois
* CA : ca_mensuel_moyen = moyenne des ``montant_ventes`` mensuels
  (hotel_sales_data) sur les mois renseignés de l'année
* Mix produits distincts (detail raw prioritaire) :
  n_produits_distincts_f_b / n_f_b / total,
  mix_f_b, mix_n_f_b = parts en nombre de produits distincts

Sources
-------
* hotel_data.xlsx — chambres, TO, marque
* hotel_sales_data.xlsx — CA mensuel
* hotel_sales_raw_data.xlsx — TYPE produit (F&B / NON-F&B) + code EAN
  (via ``sales_prep.prepare_lines``)

UI admin : onglet ``concept_pilote`` (rebuild + reload).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
FILENAME = "concept_pilote.xlsx"
SHEET = "concept_pilote"

# Défauts guests / chambre par marque (alignés simulateur ROD)
BRAND_GUESTS_DEFAULT: dict[str, float] = {
    "IBIS BUDGET": 1.7,
    "IBIS STYLES": 2.0,
    "NOVOTEL": 1.8,
    "MERCURE": 2.0,
    "IBIS": 1.8,
}

JOURS_MOIS = 30.5

CONCEPT_PILOTE_COLUMNS = [
    "hotel_code",
    "hotel_name",
    "hotel_brand",
    "annee",
    "nb_chambres",
    "taux_occupation",
    "guests_per_chambre",
    "clients_jour",
    "clients_mois",
    "n_mois_renseignes",
    "ca_mensuel_moyen",
    "n_produits_distincts_f_b",
    "n_produits_distincts_n_f_b",
    "n_produits_distincts_total",
    "mix_f_b",
    "mix_n_f_b",
]


def concept_pilote_path() -> Path:
    return DATA_DIR / FILENAME


def _norm_brand(brand: Any) -> str:
    return str(brand or "").strip().upper().replace("_", " ")


def _as_rate(value: Any, default: float = 0.70) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v > 1.0:
        v /= 100.0
    return min(max(v, 0.0), 1.0)


def _guests_for_brand(brand: Any) -> float:
    return float(BRAND_GUESTS_DEFAULT.get(_norm_brand(brand), 1.7))


def _load_hotels() -> pd.DataFrame:
    path = DATA_DIR / "hotel_data.xlsx"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_excel(path, sheet_name=0)


def _load_sales_monthly() -> pd.DataFrame:
    path = DATA_DIR / "hotel_sales_data.xlsx"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name="hotel_sales")
    except ValueError:
        return pd.read_excel(path, sheet_name=0)


def _product_key(row: pd.Series) -> str:
    ean = str(row.get("code_ean") or "").strip()
    if ean and ean.lower() not in {"nan", "none", ""}:
        return f"ean:{ean}"
    name = str(row.get("nom_produit") or "").strip()
    return f"name:{name}" if name else ""


def _mix_from_raw_lines(lines: pd.DataFrame) -> pd.DataFrame:
    """
    Par (hotel_code, annee) : produits distincts F_B / N_F_B et mix.

    Un produit = code_ean (sinon nom_produit). Catégorie = ``categorie``
    normalisée (f_b / n_f_b).
    """
    if lines is None or lines.empty:
        return pd.DataFrame(
            columns=[
                "hotel_code",
                "annee",
                "n_produits_distincts_f_b",
                "n_produits_distincts_n_f_b",
                "n_produits_distincts_total",
                "mix_f_b",
                "mix_n_f_b",
            ]
        )

    work = lines.loc[lines["hotel_code"].notna()].copy()
    if work.empty:
        return _mix_from_raw_lines(pd.DataFrame())

    work["hotel_code"] = work["hotel_code"].astype(str).str.strip()
    work["annee"] = pd.to_numeric(work["annee"], errors="coerce")
    work = work.dropna(subset=["annee"])
    work["annee"] = work["annee"].astype(int)
    work["product_key"] = work.apply(_product_key, axis=1)
    work = work.loc[work["product_key"] != ""]
    cat = work["categorie"].astype(str).str.lower().str.strip()
    work["is_fb"] = cat.isin({"f_b", "fb", "f&b"})
    work["is_nfb"] = ~work["is_fb"]

    rows: list[dict[str, Any]] = []
    for (code, year), grp in work.groupby(["hotel_code", "annee"], dropna=False):
        fb_keys = set(grp.loc[grp["is_fb"], "product_key"])
        nfb_keys = set(grp.loc[grp["is_nfb"], "product_key"])
        # Un même EAN ne doit pas être compté deux fois si catégorisé une seule fois
        # (produit unique = union)
        all_keys = fb_keys | nfb_keys
        n_fb = len(fb_keys)
        n_nfb = len(nfb_keys)
        n_tot = len(all_keys)
        # Si un produit apparaît dans les deux (rare), l'union < somme
        # Mix = part des distincts de chaque catégorie / total distincts année
        mix_fb = (n_fb / n_tot) if n_tot else 0.0
        mix_nfb = (n_nfb / n_tot) if n_tot else 0.0
        # renormalise si overlap a fait sum > 1
        s = mix_fb + mix_nfb
        if s > 1.0 and s > 0:
            mix_fb, mix_nfb = mix_fb / s, mix_nfb / s
        rows.append(
            {
                "hotel_code": code,
                "annee": int(year),
                "n_produits_distincts_f_b": n_fb,
                "n_produits_distincts_n_f_b": n_nfb,
                "n_produits_distincts_total": n_tot,
                "mix_f_b": round(mix_fb, 6),
                "mix_n_f_b": round(mix_nfb, 6),
            }
        )
    return pd.DataFrame(rows)


def _mix_from_sales_monthly(sales: pd.DataFrame) -> pd.DataFrame:
    """
    Fallback si raw indisponible : moyenne des mix mensuels
    ``pct_cat_*_nombre_produits`` ou ``nombre_categories_mois_*``.
    """
    if sales is None or sales.empty:
        return pd.DataFrame()

    work = sales.copy()
    if "hotel_code" not in work.columns or "annee" not in work.columns:
        return pd.DataFrame()

    # Préfère les effectifs de catégories distinctes mensuelles si présents
    fb_col = None
    nfb_col = None
    if "nombre_categories_mois_f_b" in work.columns:
        fb_col = "nombre_categories_mois_f_b"
        nfb_col = "nombre_categories_mois_n_f_b"
    elif "pct_cat_f_b_nombre_produits" in work.columns:
        # pas de distincts → on moyennisera les %
        fb_col = "pct_cat_f_b_nombre_produits"
        nfb_col = "pct_cat_n_f_b_nombre_produits"

    rows: list[dict[str, Any]] = []
    for (code, year), grp in work.groupby(
        [work["hotel_code"].astype(str), pd.to_numeric(work["annee"], errors="coerce")],
        dropna=False,
    ):
        if pd.isna(year):
            continue
        if fb_col and fb_col.startswith("nombre_categories"):
            # approx : max mensuel comme proxy de richesse assortiment
            n_fb = float(pd.to_numeric(grp[fb_col], errors="coerce").fillna(0).max())
            n_nfb = float(
                pd.to_numeric(grp.get(nfb_col, 0), errors="coerce").fillna(0).max()
            )
            n_tot = n_fb + n_nfb
            mix_fb = n_fb / n_tot if n_tot else 0.0
            mix_nfb = n_nfb / n_tot if n_tot else 0.0
        elif fb_col:
            mix_fb = float(pd.to_numeric(grp[fb_col], errors="coerce").fillna(0).mean())
            mix_nfb = float(
                pd.to_numeric(grp.get(nfb_col, 0), errors="coerce").fillna(0).mean()
            )
            s = mix_fb + mix_nfb
            if s > 0:
                mix_fb, mix_nfb = mix_fb / s, mix_nfb / s
            n_fb = n_nfb = n_tot = 0
        else:
            continue
        rows.append(
            {
                "hotel_code": str(code),
                "annee": int(year),
                "n_produits_distincts_f_b": int(n_fb),
                "n_produits_distincts_n_f_b": int(n_nfb),
                "n_produits_distincts_total": int(n_tot),
                "mix_f_b": round(mix_fb, 6),
                "mix_n_f_b": round(mix_nfb, 6),
            }
        )
    return pd.DataFrame(rows)


def _ca_mensuel_par_annee(sales: pd.DataFrame) -> pd.DataFrame:
    if sales is None or sales.empty or "montant_ventes" not in sales.columns:
        return pd.DataFrame(
            columns=["hotel_code", "annee", "ca_mensuel_moyen", "n_mois_renseignes"]
        )
    work = sales.copy()
    work["hotel_code"] = work["hotel_code"].astype(str).str.strip()
    work["annee"] = pd.to_numeric(work["annee"], errors="coerce")
    work["montant_ventes"] = pd.to_numeric(work["montant_ventes"], errors="coerce")
    work = work.dropna(subset=["annee"])
    # mois renseigné = montant non null (0 est un mois renseigné)
    work = work.loc[work["montant_ventes"].notna()]
    if work.empty:
        return pd.DataFrame(
            columns=["hotel_code", "annee", "ca_mensuel_moyen", "n_mois_renseignes"]
        )
    work["annee"] = work["annee"].astype(int)
    agg = (
        work.groupby(["hotel_code", "annee"], dropna=False)["montant_ventes"]
        .agg(ca_mensuel_moyen="mean", n_mois_renseignes="count")
        .reset_index()
    )
    agg["ca_mensuel_moyen"] = agg["ca_mensuel_moyen"].round(4)
    return agg


def rebuild_concept_pilote() -> dict[str, Any]:
    """
    Recalcule et écrit ``data/concept_pilote.xlsx``.

    Returns
    -------
    dict avec ok, path, rows, columns, n_hotels, years
    """
    hotels = _load_hotels()
    if hotels.empty:
        raise ValueError("hotel_data.xlsx vide ou introuvable.")

    sales = _load_sales_monthly()
    ca_year = _ca_mensuel_par_annee(sales)

    # Mix depuis raw (prioritaire)
    mix = pd.DataFrame()
    mix_source = "none"
    try:
        from sales_prep import load_hotel_lookup, load_raw_sales, prepare_lines

        raw = load_raw_sales()
        if raw is not None and not raw.empty:
            lines = prepare_lines(raw, load_hotel_lookup())
            if "hotel_code" in lines.columns:
                lines = lines.loc[lines["hotel_code"].notna()].copy()
            mix = _mix_from_raw_lines(lines)
            mix_source = "hotel_sales_raw_data"
    except Exception:
        mix = pd.DataFrame()

    if mix is None or mix.empty:
        mix = _mix_from_sales_monthly(sales)
        mix_source = "hotel_sales_data_fallback" if not mix.empty else "none"

    # Années à couvrir = union sales + raw mix
    years: set[int] = set()
    if not ca_year.empty:
        years |= set(int(y) for y in ca_year["annee"].unique())
    if not mix.empty:
        years |= set(int(y) for y in mix["annee"].unique())
    if not years and not sales.empty and "annee" in sales.columns:
        years |= {
            int(y)
            for y in pd.to_numeric(sales["annee"], errors="coerce").dropna().unique()
        }
    if not years:
        raise ValueError(
            "Aucune année de ventes trouvée (hotel_sales_data / sales_raw)."
        )

    hotel_rows = []
    for _, h in hotels.iterrows():
        code = str(h.get("hotel_code") or "").strip()
        if not code:
            continue
        name = str(h.get("hotel_name") or "").strip()
        brand = str(h.get("hotel_brand") or "").strip()
        try:
            nb_ch = int(float(h.get("hotel_nb_chambres") or 0))
        except (TypeError, ValueError):
            nb_ch = 0
        to = _as_rate(h.get("hotel_to_annuel"), 0.70)
        guests = _guests_for_brand(brand)
        clients_jour = nb_ch * to * guests
        clients_mois = clients_jour * JOURS_MOIS
        hotel_rows.append(
            {
                "hotel_code": code,
                "hotel_name": name,
                "hotel_brand": brand,
                "nb_chambres": nb_ch,
                "taux_occupation": round(to, 6),
                "guests_per_chambre": guests,
                "clients_jour": round(clients_jour, 4),
                "clients_mois": round(clients_mois, 4),
            }
        )
    hotel_base = pd.DataFrame(hotel_rows)
    if hotel_base.empty:
        raise ValueError("Aucun hôtel valide dans hotel_data.")

    # Grille hotel × année
    years_sorted = sorted(years)
    grid = hotel_base.assign(_k=1).merge(
        pd.DataFrame({"annee": years_sorted, "_k": 1}), on="_k"
    ).drop(columns=["_k"])

    if not ca_year.empty:
        grid = grid.merge(ca_year, on=["hotel_code", "annee"], how="left")
    else:
        grid["ca_mensuel_moyen"] = 0.0
        grid["n_mois_renseignes"] = 0

    if not mix.empty:
        grid = grid.merge(mix, on=["hotel_code", "annee"], how="left")
    for c in (
        "n_produits_distincts_f_b",
        "n_produits_distincts_n_f_b",
        "n_produits_distincts_total",
        "mix_f_b",
        "mix_n_f_b",
        "ca_mensuel_moyen",
        "n_mois_renseignes",
    ):
        if c not in grid.columns:
            grid[c] = 0
        grid[c] = pd.to_numeric(grid[c], errors="coerce").fillna(0)

    # Ne garder que les lignes avec au moins un mois de CA ou des produits
    mask = (grid["n_mois_renseignes"] > 0) | (grid["n_produits_distincts_total"] > 0)
    grid = grid.loc[mask].copy()

    grid = grid.sort_values(["hotel_code", "annee"]).reset_index(drop=True)
    # ordre colonnes
    cols = [c for c in CONCEPT_PILOTE_COLUMNS if c in grid.columns]
    extra = [c for c in grid.columns if c not in cols]
    grid = grid[cols + extra]

    path = concept_pilote_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    grid.to_excel(path, index=False, sheet_name=SHEET)

    return {
        "ok": True,
        "path": str(path),
        "filename": FILENAME,
        "rows": len(grid),
        "columns": list(grid.columns),
        "n_columns": len(grid.columns),
        "n_hotels": int(grid["hotel_code"].nunique()) if len(grid) else 0,
        "years": years_sorted,
        "mix_source": mix_source,
    }


def ensure_concept_pilote() -> Path:
    """Crée le fichier s'il n'existe pas."""
    path = concept_pilote_path()
    if not path.exists():
        rebuild_concept_pilote()
    return path


def load_concept_pilote() -> pd.DataFrame:
    """Charge ``concept_pilote.xlsx`` (vide si absent)."""
    path = concept_pilote_path()
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=SHEET)
    except ValueError:
        return pd.read_excel(path, sheet_name=0)


# Champs d'exploitation pour l'étape 1 run_user (pas de mix F_B / N_F_B)
STEP1_AVG_FIELDS = (
    "nb_chambres",
    "taux_occupation",
    "guests_per_chambre",
    "clients_jour",
    "clients_mois",
    "ca_mensuel_moyen",
    "n_mois_renseignes",
)


def brand_step1_averages(brand: str) -> dict[str, Any]:
    """
    Moyennes des indicateurs d'exploitation pour une marque.

    * Lit ``concept_pilote.xlsx``
    * Filtre les lignes de la marque
    * **Exclut l'année la plus récente** du fichier (holdout, ex. 2026)
    * Moyenne arithmétique des champs utiles (étape 1 — sans mix produits)

    Returns
    -------
    dict
        ok, brand, excluded_year, n_rows, n_hotels, years_used, averages, …
    """
    brand_clean = str(brand or "").strip()
    if not brand_clean:
        return {
            "ok": False,
            "error": "Marque non renseignée",
            "brand": "",
            "averages": {},
        }

    frame = load_concept_pilote()
    if frame.empty:
        return {
            "ok": False,
            "error": "concept_pilote.xlsx vide ou introuvable — reconstruisez-le dans l'admin.",
            "brand": brand_clean,
            "averages": {},
        }

    if "hotel_brand" not in frame.columns or "annee" not in frame.columns:
        return {
            "ok": False,
            "error": "Colonnes hotel_brand / annee manquantes dans concept_pilote.",
            "brand": brand_clean,
            "averages": {},
        }

    work = frame.copy()
    work["hotel_brand"] = work["hotel_brand"].astype(str).str.strip()
    work["annee"] = pd.to_numeric(work["annee"], errors="coerce")
    work = work.dropna(subset=["annee"])
    work["annee"] = work["annee"].astype(int)

    # Match marque insensible à la casse
    brand_key = brand_clean.upper().replace("_", " ")
    mask = work["hotel_brand"].str.upper().str.replace("_", " ", regex=False) == brand_key
    subset = work.loc[mask].copy()
    if subset.empty:
        # partial contains
        mask2 = work["hotel_brand"].str.upper().str.contains(
            brand_key, regex=False, na=False
        )
        subset = work.loc[mask2].copy()
    if subset.empty:
        return {
            "ok": False,
            "error": f"Aucune ligne concept_pilote pour la marque « {brand_clean} ».",
            "brand": brand_clean,
            "averages": {},
            "available_brands": sorted(
                work["hotel_brand"].dropna().astype(str).unique().tolist()
            ),
        }

    # Exclure l'année la plus récente **globale** du fichier (pas seulement de la marque)
    max_year_global = int(work["annee"].max())
    before = len(subset)
    subset = subset.loc[subset["annee"] < max_year_global].copy()
    if subset.empty:
        return {
            "ok": False,
            "error": (
                f"Aucune année hors holdout ({max_year_global}) pour « {brand_clean} »."
            ),
            "brand": brand_clean,
            "excluded_year": max_year_global,
            "averages": {},
            "n_rows_before_exclude": before,
        }

    averages: dict[str, float] = {}
    for col in STEP1_AVG_FIELDS:
        if col not in subset.columns:
            continue
        s = pd.to_numeric(subset[col], errors="coerce").dropna()
        if s.empty:
            continue
        averages[col] = float(s.mean())

    # Arrondis d'affichage
    if "nb_chambres" in averages:
        averages["nb_chambres"] = round(averages["nb_chambres"], 1)
    if "taux_occupation" in averages:
        averages["taux_occupation"] = round(averages["taux_occupation"], 6)
    if "guests_per_chambre" in averages:
        averages["guests_per_chambre"] = round(averages["guests_per_chambre"], 3)
    if "clients_jour" in averages:
        averages["clients_jour"] = round(averages["clients_jour"], 2)
    if "clients_mois" in averages:
        averages["clients_mois"] = round(averages["clients_mois"], 2)
    if "ca_mensuel_moyen" in averages:
        averages["ca_mensuel_moyen"] = round(averages["ca_mensuel_moyen"], 2)
    if "n_mois_renseignes" in averages:
        averages["n_mois_renseignes"] = round(averages["n_mois_renseignes"], 2)

    years_used = sorted(int(y) for y in subset["annee"].unique())
    n_hotels = (
        int(subset["hotel_code"].nunique()) if "hotel_code" in subset.columns else 0
    )

    return {
        "ok": True,
        "brand": brand_clean,
        "excluded_year": max_year_global,
        "years_used": years_used,
        "n_rows": len(subset),
        "n_hotels": n_hotels,
        "averages": averages,
    }
