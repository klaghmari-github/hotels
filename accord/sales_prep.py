#!/usr/bin/env python3
"""
Pipeline Sales — reconstruit ``hotel_sales_data.xlsx`` depuis les ventes brutes.

Indépendant de l'archive : s'inspire de l'ancien SalesPrep (agrégats mensuels,
mix F_B / N_F_B, % sous-catégories) mais vit entièrement sous ``accord/``.

Entrées
-------
* ``data/hotel_sales_raw_data.xlsx`` — tickets bruts (ou import CSV historique)
* ``data/hotel_data.xlsx`` — référentiel hôtels (``hotel_code``, ``hotel_name``)

Sortie
------
* ``data/hotel_sales_data.xlsx`` — grain hôtel × année × mois + indicateurs

Normalisations critiques
------------------------
1. **Hôtels** : ``NOM BOUTIQUE`` → ``hotel_code`` via matching flou sur
   ``hotel_name`` (référentiel hotel_data).
2. **Catégories** : TYPE ``F&B`` / ``NON-F&B`` → ``f_b`` / ``n_f_b``.
3. **Sous-catégories** : GAMME (ex. ``FOOD SALEE``, ``SANS ALCOOL``) → slug
   stable (``food_salee``, ``sans_alcool``…).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_FILENAME = "hotel_sales_raw_data.xlsx"
RAW_SHEET = "sales_raw"
SALES_FILENAME = "hotel_sales_data.xlsx"
SALES_SHEET = "hotel_sales"

# Colonnes brutes attendues (noms source ou normalisés)
RAW_COLUMN_MAP = {
    "nom boutique": "nom_boutique",
    "nom_boutique": "nom_boutique",
    "operateur": "operateur",
    "machine": "machine",
    "date": "date",
    "heure": "heure",
    "statut": "statut",
    "code ean": "code_ean",
    "nom du produit": "nom_produit",
    "quantite": "quantite",
    "prix ht": "prix_ht",
    "vat": "vat",
    "prix ttc": "prix_ttc",
    "type": "type_raw",
    "gamme": "gamme_raw",
    "marque": "marque_produit",
    "fournisseur": "fournisseur",
    "order id (ticket de caisse)": "order_id",
    "order_id": "order_id",
}

# TYPE → catégorie modèle
TYPE_MAP = {
    "f&b": "f_b",
    "f_b": "f_b",
    "fb": "f_b",
    "food": "f_b",
    "non-f&b": "n_f_b",
    "non_f&b": "n_f_b",
    "n-f&b": "n_f_b",
    "n_f_b": "n_f_b",
    "non fb": "n_f_b",
    "non_fb": "n_f_b",
}

# GAMME → slug sous-catégorie (clés normalisées)
GAMME_MAP = {
    "sans alcool": "sans_alcool",
    "food sucree": "food_sucree",
    "food sucrée": "food_sucree",
    "food salee": "food_salee",
    "food salée": "food_salee",
    "sos": "sos",
    "alcool": "alcool",
    "accessoires": "accessoires",
    "jeux / enfants": "jeux_enfants",
    "jeux enfants": "jeux_enfants",
    "cosmetique": "cosmetique",
    "cosmétique": "cosmetique",
    "pap": "pap",
    "souvenirs": "souvenirs",
    "ref": "ref",
}

MEASURES = ("nombre_ventes", "montant_ventes", "nombre_paniers", "nombre_produits")
SOUS_CAT_SLUGS = (
    "ref",
    "accessoires",
    "alcool",
    "cosmetique",
    "food_salee",
    "food_sucree",
    "jeux_enfants",
    "pap",
    "sans_alcool",
    "sos",
    "souvenirs",
)


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_label(value: Any) -> str:
    """Normalise un libellé libre → minuscules sans accents, espaces simples."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text or text.upper() in {"#REF!", "#N/A", "N/A", "NAN", "NONE", "?", "NULL"}:
        return ""
    if text.upper().startswith("#"):
        return ""
    text = _strip_accents(text).lower()
    text = re.sub(r"\s+", " ", text)
    return text


def slugify(value: str) -> str:
    text = normalize_label(value)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "autre"


def normalize_type(value: Any) -> str:
    key = normalize_label(value).replace(" ", "_")
    # variantes
    key2 = normalize_label(value)
    if key in TYPE_MAP:
        return TYPE_MAP[key]
    if key2 in TYPE_MAP:
        return TYPE_MAP[key2]
    if "non" in key2 and "f" in key2:
        return "n_f_b"
    if "f&b" in key2 or key2 in {"fb", "f_b"}:
        return "f_b"
    return "n_f_b" if key2 else "n_f_b"


def normalize_gamme(value: Any) -> str:
    key = normalize_label(value)
    if key in GAMME_MAP:
        return GAMME_MAP[key]
    # fallback slug
    return slugify(value) if key else "autre"


def raw_path() -> Path:
    return DATA_DIR / RAW_FILENAME


def sales_path() -> Path:
    return DATA_DIR / SALES_FILENAME


def load_hotel_lookup() -> pd.DataFrame:
    """Référentiel hotel_data → colonnes nom_hotel, hotel_code, hotel_name."""
    path = DATA_DIR / "hotel_data.xlsx"
    if not path.exists():
        return pd.DataFrame(columns=["hotel_code", "hotel_name", "nom_key"])
    hotels = pd.read_excel(path, sheet_name=0)
    if "hotel_code" not in hotels.columns or "hotel_name" not in hotels.columns:
        return pd.DataFrame(columns=["hotel_code", "hotel_name", "nom_key"])
    out = hotels[["hotel_code", "hotel_name"]].drop_duplicates().copy()
    out["nom_key"] = out["hotel_name"].map(normalize_label)
    return out


def match_hotel_code(nom_boutique: str, lookup: pd.DataFrame) -> tuple[str | None, str | None]:
    """
    Lie un nom de boutique brut au code Accor.

    Stratégie :
    1. égalité exacte sur clé normalisée
    2. containment (boutique ⊂ name ou name ⊂ boutique)
    3. score de tokens en commun (meilleur score ≥ 2 tokens)
    """
    key = normalize_label(nom_boutique)
    if not key or lookup.empty:
        return None, None

    # exact
    hit = lookup.loc[lookup["nom_key"] == key]
    if len(hit):
        row = hit.iloc[0]
        return str(row["hotel_code"]), str(row["hotel_name"])

    # containment
    for _, row in lookup.iterrows():
        nk = row["nom_key"]
        if not nk:
            continue
        if key in nk or nk in key:
            return str(row["hotel_code"]), str(row["hotel_name"])

    # token overlap
    tokens = set(key.split())
    best_score, best = 0, None
    for _, row in lookup.iterrows():
        nk = row["nom_key"]
        if not nk:
            continue
        score = len(tokens & set(nk.split()))
        # bonus si premier token (marque) match
        if tokens and nk.split() and list(tokens)[0] == nk.split()[0]:
            score += 0.5
        if score > best_score:
            best_score = score
            best = row
    if best is not None and best_score >= 2:
        return str(best["hotel_code"]), str(best["hotel_name"])
    return None, None


def _normalize_raw_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for c in frame.columns:
        key = normalize_label(c)
        if key in RAW_COLUMN_MAP:
            rename[c] = RAW_COLUMN_MAP[key]
        else:
            # already normalized?
            slug = slugify(c)
            if slug in RAW_COLUMN_MAP.values():
                rename[c] = slug
    out = frame.rename(columns=rename)
    return out


def load_raw_sales(path: Path | None = None) -> pd.DataFrame:
    """Charge le fichier raw (xlsx ou legacy csv copié)."""
    path = path or raw_path()
    if not path.exists():
        # tentative CSV historique monorepo
        legacy = (
            Path(__file__).resolve().parent.parent
            / "archive"
            / "sources"
            / "raw"
            / "001.queryVentes.csv"
        )
        if legacy.exists():
            frame = pd.read_csv(legacy, dtype=str, low_memory=False)
            return _normalize_raw_columns(frame)
        return pd.DataFrame()
    try:
        frame = pd.read_excel(path, sheet_name=RAW_SHEET, dtype=str)
    except ValueError:
        frame = pd.read_excel(path, sheet_name=0, dtype=str)
    return _normalize_raw_columns(frame)


def import_raw_from_csv(csv_path: Path, dest: Path | None = None) -> Path:
    """Importe le CSV brut vers hotel_sales_raw_data.xlsx."""
    dest = dest or raw_path()
    frame = pd.read_csv(csv_path, low_memory=False)
    frame = _normalize_raw_columns(frame)
    dest.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(dest, index=False, sheet_name=RAW_SHEET)
    return dest


def prepare_lines(raw: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    """Normalise les lignes brutes + attache hotel_code."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    # statut DONE uniquement si la colonne existe
    if "statut" in df.columns:
        st = df["statut"].astype(str).str.strip().str.upper()
        # garder DONE + valeurs vides/NA (exports partiels)
        keep = st.eq("DONE") | st.isin(["", "NAN", "NONE", "NAT"]) | df["statut"].isna()
        df = df.loc[keep].copy()

    # dates
    if "date" not in df.columns:
        raise ValueError("Colonne DATE / date manquante dans les ventes brutes.")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["annee"] = df["date"].dt.year.astype(int)
    df["mois"] = df["date"].dt.month.astype(int)

    # quantités / montants ligne = prix unitaire × quantité (HT prioritaire, sinon TTC)
    q = pd.to_numeric(df["quantite"] if "quantite" in df.columns else 1, errors="coerce").fillna(1.0).clip(lower=0)
    ht = pd.to_numeric(df["prix_ht"], errors="coerce") if "prix_ht" in df.columns else pd.Series(pd.NA, index=df.index)
    ttc = pd.to_numeric(df["prix_ttc"], errors="coerce") if "prix_ttc" in df.columns else pd.Series(pd.NA, index=df.index)
    unit = ht.fillna(ttc).fillna(0.0)
    df["nombre_ventes"] = q
    df["montant_ventes"] = (unit * q).astype(float)
    if "order_id" in df.columns:
        df["order_id"] = df["order_id"].astype(str)
    else:
        df["order_id"] = [f"row_{i}" for i in range(len(df))]
    if "code_ean" in df.columns:
        df["code_ean"] = df["code_ean"].astype(str)
    else:
        df["code_ean"] = df["nom_produit"].astype(str) if "nom_produit" in df.columns else ""
    type_src = df["type_raw"] if "type_raw" in df.columns else pd.Series("", index=df.index)
    gamme_src = df["gamme_raw"] if "gamme_raw" in df.columns else pd.Series("", index=df.index)
    df["categorie"] = type_src.map(normalize_type)
    df["sous_categorie"] = gamme_src.map(normalize_gamme)

    # mapping hôtel
    if "nom_boutique" not in df.columns:
        raise ValueError("Colonne NOM BOUTIQUE / nom_boutique manquante.")
    codes = []
    names = []
    cache: dict[str, tuple[str | None, str | None]] = {}
    for nom in df["nom_boutique"].astype(str):
        if nom not in cache:
            cache[nom] = match_hotel_code(nom, lookup)
        code, hname = cache[nom]
        codes.append(code)
        names.append(hname or nom)
    df["hotel_code"] = codes
    df["nom_hotel"] = df["nom_boutique"].astype(str)
    df["hotel_name_ref"] = names

    # drop lines without hotel match? keep with NA code for audit
    return df


def _agg_group(g: pd.DataFrame) -> pd.Series:
    return pd.Series(
        {
            "nombre_ventes": g["nombre_ventes"].sum(),
            "montant_ventes": g["montant_ventes"].sum(),
            "nombre_paniers": g["order_id"].nunique(),
            "nombre_produits": g["code_ean"].nunique(),
        }
    )



def build_monthly_sales(lines: pd.DataFrame) -> pd.DataFrame:
    """Agrège hotel × année × mois + mix cat / sous-cat (pct)."""
    if lines is None or lines.empty:
        return pd.DataFrame()

    keys = ["hotel_code", "nom_hotel", "annee", "mois"]
    base = (
        lines.groupby(keys, dropna=False)
        .agg(
            nombre_ventes=("nombre_ventes", "sum"),
            montant_ventes=("montant_ventes", "sum"),
            nombre_paniers=("order_id", "nunique"),
            nombre_produits=("code_ean", "nunique"),
        )
        .reset_index()
    )

    cat_counts = (
        lines.groupby(keys + ["categorie"], dropna=False)["sous_categorie"]
        .nunique()
        .reset_index(name="n_sous")
    )
    n_fb = cat_counts[cat_counts["categorie"] == "f_b"][keys + ["n_sous"]].rename(
        columns={"n_sous": "nombre_categories_mois_f_b"}
    )
    n_nfb = cat_counts[cat_counts["categorie"] == "n_f_b"][keys + ["n_sous"]].rename(
        columns={"n_sous": "nombre_categories_mois_n_f_b"}
    )
    base = base.merge(n_fb, on=keys, how="left").merge(n_nfb, on=keys, how="left")
    base["nombre_categories_mois_f_b"] = base["nombre_categories_mois_f_b"].fillna(0)
    base["nombre_categories_mois_n_f_b"] = base["nombre_categories_mois_n_f_b"].fillna(0)
    tot_n = base["nombre_categories_mois_f_b"] + base["nombre_categories_mois_n_f_b"]
    base["pct_categories_mois_f_b"] = (
        base["nombre_categories_mois_f_b"] / tot_n.replace(0, pd.NA)
    ).fillna(0.0)
    base["pct_categories_mois_n_f_b"] = (
        base["nombre_categories_mois_n_f_b"] / tot_n.replace(0, pd.NA)
    ).fillna(0.0)

    by_cat = (
        lines.groupby(keys + ["categorie"], dropna=False)
        .agg(
            nombre_ventes=("nombre_ventes", "sum"),
            montant_ventes=("montant_ventes", "sum"),
            nombre_paniers=("order_id", "nunique"),
            nombre_produits=("code_ean", "nunique"),
        )
        .reset_index()
    )
    for measure in MEASURES:
        for cat in ("f_b", "n_f_b"):
            col = f"pct_cat_{cat}_{measure}"
            sub = by_cat.loc[by_cat["categorie"] == cat, keys + [measure]].rename(
                columns={measure: "_v"}
            )
            base = base.merge(sub, on=keys, how="left")
            base["_v"] = base["_v"].fillna(0.0)
            base[col] = (base["_v"] / base[measure].replace(0, pd.NA)).fillna(0.0)
            base = base.drop(columns=["_v"])

    by_sub = (
        lines.groupby(keys + ["categorie", "sous_categorie"], dropna=False)
        .agg(
            nombre_ventes=("nombre_ventes", "sum"),
            montant_ventes=("montant_ventes", "sum"),
            nombre_paniers=("order_id", "nunique"),
            nombre_produits=("code_ean", "nunique"),
        )
        .reset_index()
    )
    cat_tot = by_sub.groupby(keys + ["categorie"], dropna=False)[list(MEASURES)].transform(
        "sum"
    )
    for measure in MEASURES:
        by_sub[f"_pct_{measure}"] = (
            by_sub[measure] / cat_tot[measure].replace(0, pd.NA)
        ).fillna(0.0)

    for measure in MEASURES:
        for slug in SOUS_CAT_SLUGS:
            col = f"pct_sous_cat_{slug}_{measure}"
            sub = (
                by_sub.loc[by_sub["sous_categorie"] == slug, keys + [f"_pct_{measure}"]]
                .groupby(keys, dropna=False)[f"_pct_{measure}"]
                .sum()
                .reset_index()
                .rename(columns={f"_pct_{measure}": col})
            )
            base = base.merge(sub, on=keys, how="left")
            base[col] = base[col].fillna(0.0)

    base["hotel_code"] = base["hotel_code"].astype(str)
    sort_cols = [c for c in ("hotel_code", "annee", "mois") if c in base.columns]
    if sort_cols:
        base = base.sort_values(sort_cols).reset_index(drop=True)
    return base


def rebuild_hotel_sales_data(
    *,
    raw: pd.DataFrame | None = None,
    drop_unmatched: bool = True,
) -> dict[str, Any]:
    """
    Pipeline complet raw → hotel_sales_data.xlsx.

    Parameters
    ----------
    drop_unmatched :
        Si True, ignore les lignes dont le nom boutique ne matche aucun hôtel.
    """
    lookup = load_hotel_lookup()
    if raw is None:
        raw = load_raw_sales()
    if raw is None or raw.empty:
        raise ValueError(
            "Ventes brutes introuvables. Placez hotel_sales_raw_data.xlsx "
            "ou importez archive/sources/raw/001.queryVentes.csv."
        )

    lines = prepare_lines(raw, lookup)
    n_raw = len(lines)
    unmatched = int(lines["hotel_code"].isna().sum()) if "hotel_code" in lines.columns else n_raw
    if drop_unmatched and "hotel_code" in lines.columns:
        lines = lines.loc[lines["hotel_code"].notna()].copy()

    if lines.empty:
        raise ValueError(
            f"Aucune ligne matchée sur hotel_data ({unmatched}/{n_raw} non liées)."
        )

    monthly = build_monthly_sales(lines)
    path = sales_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_excel(path, index=False, sheet_name=SALES_SHEET)

    return {
        "ok": True,
        "path": str(path),
        "rows": len(monthly),
        "columns": list(monthly.columns),
        "n_columns": len(monthly.columns),
        "n_raw_lines": n_raw,
        "n_unmatched": unmatched,
        "n_hotels": int(monthly["hotel_code"].nunique()) if "hotel_code" in monthly.columns else 0,
        "years": sorted(monthly["annee"].dropna().unique().tolist()) if "annee" in monthly.columns else [],
    }


def ensure_raw_sales_from_archive() -> Path | None:
    """Copie le CSV archive vers hotel_sales_raw_data.xlsx s'il manque."""
    dest = raw_path()
    if dest.exists():
        return dest
    legacy = (
        Path(__file__).resolve().parent.parent
        / "archive"
        / "sources"
        / "raw"
        / "001.queryVentes.csv"
    )
    if legacy.exists():
        return import_raw_from_csv(legacy, dest)
    return None
