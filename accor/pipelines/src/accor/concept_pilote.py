#!/usr/bin/env python3
"""
Construction de concept_pilote.xlsx — indicateurs annuels par hôtel.

Grain : hotel_code × annee

Colonnes principales
--------------------
  Identité     hotel_code, hotel_name, hotel_brand
  Exploitation nb_chambres, TO, guests_per_chambre, clients_jour/mois
               (hotel_data + défauts marque si besoin)
  CA           ca_mensuel_moyen = moyenne des montant_ventes mensuels
               sur les mois renseignés de l'année
  Mix          produits distincts F&B / non-F&B (raw prioritaire)

Sources : hotel_data, hotel_sales_data, hotel_sales_raw_data
  (prepare_lines pour le TYPE produit).

UI admin : onglet concept_pilote (rebuild). Côté user : référence
marque via /api/concept_pilote/brand/<marque> et règles de simu.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from accor.data_io import DATA_DIR
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
        from accor.sales_prep import load_hotel_lookup, load_raw_sales, prepare_lines

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

# Échelle de gamme croissante (Accor) :
# IBIS BUDGET < IBIS STYLES < MERCURE < NOVOTEL
# Si une marque n'a pas de pilote, on moyenne les voisins immédiats
# (ex. IBIS STYLES absent → IBIS BUDGET + MERCURE).
BRAND_LADDER: tuple[str, ...] = (
    "IBIS BUDGET",
    "IBIS STYLES",
    "MERCURE",
    "NOVOTEL",
)

# Alias de libellés UI / hotel_data → clé d'échelle
BRAND_ALIASES: dict[str, str] = {
    "IBIS BUDGET": "IBIS BUDGET",
    "IBB": "IBIS BUDGET",
    "IBIS STYLES": "IBIS STYLES",
    "IBIS STYLE": "IBIS STYLES",
    "IBS": "IBIS STYLES",
    "MERCURE": "MERCURE",
    "MER": "MERCURE",
    "NOVOTEL": "NOVOTEL",
    "NOV": "NOVOTEL",
    # IBIS « classic » : entre budget et styles (voisinage budget+styles)
    "IBIS": "IBIS STYLES",
}


def _normalize_brand_key(brand: str) -> str:
    """Normalise un libellé marque vers une clé d'échelle (ou upper brute)."""
    raw = str(brand or "").strip().upper().replace("_", " ")
    raw = " ".join(raw.split())
    if raw in BRAND_ALIASES:
        return BRAND_ALIASES[raw]
    # contains soft match
    for alias, key in BRAND_ALIASES.items():
        if alias in raw or raw in alias:
            return key
    return raw


def _brand_col_key(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.upper()
        .str.replace("_", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
    )


def _filter_brands(work: pd.DataFrame, brand_keys: list[str]) -> pd.DataFrame:
    """Lignes dont hotel_brand matche une des clés (exact ou contains)."""
    if work.empty or not brand_keys:
        return work.iloc[0:0].copy()
    col = _brand_col_key(work["hotel_brand"])
    keys_norm = [_normalize_brand_key(k) for k in brand_keys]
    # aussi les libellés originaux upper
    keys_all = set(keys_norm) | {k.upper().replace("_", " ") for k in brand_keys}

    def row_match(val: str) -> bool:
        v = _normalize_brand_key(val)
        if v in keys_all:
            return True
        vu = str(val).upper().replace("_", " ")
        for k in keys_all:
            if k in vu or vu in k:
                return True
        return False

    mask = col.map(row_match)
    return work.loc[mask].copy()


def _ladder_neighbor_keys(brand_key: str) -> list[str]:
    """
    Voisins immédiats sur l'échelle de gamme.

    * milieu : gauche + droite
    * extrémité : seul voisin disponible
    * hors échelle : []
    """
    if brand_key not in BRAND_LADDER:
        return []
    i = BRAND_LADDER.index(brand_key)
    neighbors: list[str] = []
    if i > 0:
        neighbors.append(BRAND_LADDER[i - 1])
    if i < len(BRAND_LADDER) - 1:
        neighbors.append(BRAND_LADDER[i + 1])
    return neighbors


def _expand_neighbor_keys(
    brand_key: str, available_ladder: set[str]
) -> list[str]:
    """
    Étend le voisinage jusqu'à trouver au moins une marque présente dans
    ``available_ladder`` (clés d'échelle présentes dans les données).
    """
    if brand_key not in BRAND_LADDER:
        return []
    i = BRAND_LADDER.index(brand_key)
    found: list[str] = []
    # gauche
    for j in range(i - 1, -1, -1):
        if BRAND_LADDER[j] in available_ladder:
            found.append(BRAND_LADDER[j])
            break
    # droite
    for j in range(i + 1, len(BRAND_LADDER)):
        if BRAND_LADDER[j] in available_ladder:
            found.append(BRAND_LADDER[j])
            break
    return found


def _round_averages(averages: dict[str, float]) -> dict[str, float]:
    out = dict(averages)
    if "nb_chambres" in out:
        out["nb_chambres"] = round(out["nb_chambres"], 1)
    if "taux_occupation" in out:
        out["taux_occupation"] = round(out["taux_occupation"], 6)
    if "guests_per_chambre" in out:
        out["guests_per_chambre"] = round(out["guests_per_chambre"], 3)
    if "clients_jour" in out:
        out["clients_jour"] = round(out["clients_jour"], 2)
    if "clients_mois" in out:
        out["clients_mois"] = round(out["clients_mois"], 2)
    if "ca_mensuel_moyen" in out:
        out["ca_mensuel_moyen"] = round(out["ca_mensuel_moyen"], 2)
    if "n_mois_renseignes" in out:
        out["n_mois_renseignes"] = round(out["n_mois_renseignes"], 2)
    return out


def _mean_fields(subset: pd.DataFrame) -> dict[str, float]:
    averages: dict[str, float] = {}
    for col in STEP1_AVG_FIELDS:
        if col not in subset.columns:
            continue
        s = pd.to_numeric(subset[col], errors="coerce").dropna()
        if s.empty:
            continue
        averages[col] = float(s.mean())
    return _round_averages(averages)


def rule1_ca_by_concept(
    *,
    nb_chambres: float,
    taux_occupation: float,
    guests_per_chambre: float,
) -> dict[str, Any]:
    """
    Applique **impact TO + Règle 1** (scaling clients) pour chaque concept.

    Formule (alignée ``user.rules.revenue.RevenueRules``) :
    * clients_hôtel  = n × TO × guests × 30,5
    * clients_pilote = pivot_n × pivot_to × pivot_guests × 30,5
    * CA F&B/N-F&B après impact TO (écart TO × ~9,23 €/pt)
    * CA projeté     = (CA F&B + CA N-F&B) × (clients_hôtel / clients_pilote)

    Ne fait **pas** encore R2 mix / R3 catégories / R4 m_lin (étapes suivantes).
    """
    from accor.user.reference import RodReference
    from accor.user.rules.revenue import RevenueRules

    to = float(taux_occupation)
    if to > 1.0:
        to /= 100.0
    to = min(max(to, 0.0), 1.0)
    n = max(float(nb_chambres), 0.0)
    g = max(float(guests_per_chambre), 0.0)
    clients_hotel = n * to * g * JOURS_MOIS

    ref = RodReference()
    impact = float(ref.get("impact_to.ht_per_0_01_to", 9.233974) or 9.233974)

    by_concept: dict[str, Any] = {}
    for concept in ("SIMPLY", "LIBERTY", "CONNECTED"):
        key = f"concepts.{concept}"
        pivot_n = float(ref.get(f"{key}.pivot_nb_chambres", 129) or 129)
        pivot_g = float(ref.get(f"{key}.pivot_guests_per_chambre", 1.7) or 1.7)
        pivot_to = float(ref.get(f"{key}.pivot_to", 0.75) or 0.75)
        ca_fb_ref = float(ref.get(f"{key}.base_monthly_ca_fb", 0) or 0)
        ca_nf_ref = float(ref.get(f"{key}.base_monthly_ca_nf", 0) or 0)
        ca_ht_ref = ca_fb_ref + ca_nf_ref
        ventes_ref = float(ref.get(f"{key}.base_monthly_sales", 0) or 0)

        clients_pilote = pivot_n * pivot_to * pivot_g * JOURS_MOIS
        to_delta = to - pivot_to

        ca_fb, ca_nf = RevenueRules.apply_to_impact(
            ca_fb_ref, ca_nf_ref, to_delta, impact
        )
        ca_fb, ca_nf, factor = RevenueRules.rule1_clients(
            ca_fb, ca_nf, clients_hotel, clients_pilote
        )
        ca_ht = max(ca_fb + ca_nf, 0.0)
        taux_acheteur = ventes_ref / clients_pilote if clients_pilote else 0.0
        ventes = taux_acheteur * clients_hotel

        by_concept[concept] = {
            "ca_ht_mensuel": round(ca_ht, 2),
            "ca_fb_mensuel": round(ca_fb, 2),
            "ca_nf_mensuel": round(ca_nf, 2),
            "ca_ht_pilote": round(ca_ht_ref, 2),
            "clients_pilote": round(clients_pilote, 2),
            "client_factor": round(factor, 4),
            "to_delta": round(to_delta, 4),
            "nbr_ventes_mensuel": round(ventes, 2),
            "pivot_nb_chambres": pivot_n,
            "pivot_to": pivot_to,
            "pivot_guests": pivot_g,
        }

    return {
        "ok": True,
        "nb_chambres": n,
        "taux_occupation": to,
        "guests_per_chambre": g,
        "clients_jour": round(n * to * g, 2),
        "clients_mois": round(clients_hotel, 2),
        "by_concept": by_concept,
        "formula": (
            "CA_mensuel = (CA_pilote_F&B + CA_pilote_N-F&B + impact_TO) "
            "× (clients_hôtel / clients_pilote)"
        ),
    }


def brand_step1_averages(brand: str) -> dict[str, Any]:
    """
    Moyennes des indicateurs d'exploitation pour une marque.

    * Lit ``concept_pilote.xlsx``
    * **Exclut l'année la plus récente** du fichier (holdout, ex. 2026)
    * Filtre la marque demandée
    * Si aucune ligne : **échelle de gamme**
      ``IBIS BUDGET < IBIS STYLES < MERCURE < NOVOTEL`` —
      moyenne des **voisins** présents (ex. STYLES → BUDGET + MERCURE)
    * Moyenne arithmétique des champs utiles (étape 1 — sans mix produits)

    Returns
    -------
    dict
        ok, brand, excluded_year, n_rows, n_hotels, years_used, averages,
        strategy (``direct`` | ``neighbors``), source_brands, …
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

    # Exclure l'année la plus récente **globale** du fichier
    max_year_global = int(work["annee"].max())
    work_holdout = work.loc[work["annee"] < max_year_global].copy()
    if work_holdout.empty:
        return {
            "ok": False,
            "error": f"Aucune année hors holdout ({max_year_global}).",
            "brand": brand_clean,
            "excluded_year": max_year_global,
            "averages": {},
        }

    brand_key = _normalize_brand_key(brand_clean)

    # --- 1) Direct : lignes de la marque ---
    subset = _filter_brands(work_holdout, [brand_clean, brand_key])
    strategy = "direct"
    source_brands: list[str] = []

    if not subset.empty:
        source_brands = sorted(
            subset["hotel_brand"].dropna().astype(str).str.strip().unique().tolist()
        )
    else:
        # --- 2) Voisins sur l'échelle de gamme ---
        # Marques d'échelle effectivement présentes dans le holdout
        present_raw = (
            work_holdout["hotel_brand"].dropna().astype(str).str.strip().unique().tolist()
        )
        available_ladder: set[str] = set()
        for p in present_raw:
            k = _normalize_brand_key(p)
            if k in BRAND_LADDER:
                available_ladder.add(k)

        neighbor_keys = _ladder_neighbor_keys(brand_key)
        # Ne garder que les voisins qui ont des données ; sinon élargir
        neighbor_keys = [k for k in neighbor_keys if k in available_ladder]
        if not neighbor_keys:
            neighbor_keys = _expand_neighbor_keys(brand_key, available_ladder)

        if not neighbor_keys:
            return {
                "ok": False,
                "error": (
                    f"Aucune ligne concept_pilote pour « {brand_clean} » "
                    f"et aucun voisin d'échelle disponible "
                    f"({' < '.join(BRAND_LADDER)})."
                ),
                "brand": brand_clean,
                "brand_key": brand_key,
                "excluded_year": max_year_global,
                "averages": {},
                "available_brands": sorted(present_raw),
                "ladder": list(BRAND_LADDER),
            }

        subset = _filter_brands(work_holdout, neighbor_keys)
        strategy = "neighbors"
        source_brands = neighbor_keys
        if subset.empty:
            return {
                "ok": False,
                "error": (
                    f"Voisins {neighbor_keys} sans lignes hors {max_year_global}."
                ),
                "brand": brand_clean,
                "brand_key": brand_key,
                "excluded_year": max_year_global,
                "source_brands": neighbor_keys,
                "averages": {},
            }

    averages = _mean_fields(subset)
    years_used = sorted(int(y) for y in subset["annee"].unique())
    n_hotels = (
        int(subset["hotel_code"].nunique()) if "hotel_code" in subset.columns else 0
    )

    # Libellés réellement présents dans le subset
    brands_in_subset = sorted(
        subset["hotel_brand"].dropna().astype(str).str.strip().unique().tolist()
    )

    # Règle 1 : CA mensuel attendu par concept (impact TO + scaling clients)
    rule1: dict[str, Any] = {}
    if averages:
        rule1 = rule1_ca_by_concept(
            nb_chambres=float(averages.get("nb_chambres") or 0),
            taux_occupation=float(averages.get("taux_occupation") or 0.7),
            guests_per_chambre=float(averages.get("guests_per_chambre") or 1.7),
        )

    return {
        "ok": True,
        "brand": brand_clean,
        "brand_key": brand_key,
        "excluded_year": max_year_global,
        "years_used": years_used,
        "n_rows": len(subset),
        "n_hotels": n_hotels,
        "averages": averages,
        "strategy": strategy,
        "source_brands": brands_in_subset if strategy == "direct" else source_brands,
        "ladder": list(BRAND_LADDER),
        "rule1": rule1,
        "note": (
            None
            if strategy == "direct"
            else (
                f"Marque « {brand_clean} » absente des pilotes : "
                f"moyenne des voisins d'échelle "
                f"{' + '.join(source_brands)} "
                f"(ordre : {' < '.join(BRAND_LADDER)})."
            )
        ),
    }
