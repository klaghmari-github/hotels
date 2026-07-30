#!/usr/bin/env python3
"""
Nettoyage du fichier de ventes hôtels Accor.

Entrées :
  - hotel_sales_raw_data.xlsx          (fichier brut ~130k lignes)
  - hotels_produits_nettoyes.xlsx      (mapping de référence)

Sortie :
  - hotel_sales_raw_clean.xlsx

Usage :
  python clean_hotel_sales.py
  python clean_hotel_sales.py \\
      --raw  data/hotel_sales_raw_data.xlsx \\
      --map  hotels_produits_nettoyes.xlsx \\
      --out  data/hotel_sales_raw_clean.xlsx
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


DEFAULT_RAW = Path("data/hotel_sales_raw_data.xlsx")
DEFAULT_MAP = Path("hotels_produits_nettoyes.xlsx")
DEFAULT_OUT = Path("data/hotel_sales_raw_clean.xlsx")

GAMME_MAP = {
    "FOOD SALEE": "SALTY FOOD",
    "FOOD SUCREE": "SUGARY FOOD",
    "SALTY FOOD (Fresh)": "SALTY FOOD",
    "SALTY FOOD (Dry)": "SALTY FOOD",
    "SUGARY FOOD (Fresh)": "SUGARY FOOD",
    "SUGARY FOOD (Dry)": "SUGARY FOOD",
    "FORMULE": "FORMULE",
    "SANS ALCOOL": "SANS ALCOOL",
    "ALCOOL": "ALCOOL",
    "ACCESSOIRES": "ACCESSOIRES",
    "PAP": "PAP",
    "SOS": "SOS",
    "JEUX / ENFANTS": "JEU_ENFANTS",
    "COSMETIQUE": "COSMETIQUE",
    "SOUVENIRS": "SOUVENIRS",
}


# ---------------------------------------------------------------------------
# Nettoyage nom produit
# ---------------------------------------------------------------------------
def clean_product_name(name: object) -> object:
    if pd.isna(name):
        return name
    s = str(name).strip()

    s = re.sub(
        r"\s*\(\s*(\d+[.,]?\d*\s*(?:cl|g|ml|l|cm|kg|mm|G|CL|ML|L)?)\s*\)",
        r" \1",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s*\(\s*bouteille en verre\s*\)", " Bouteille En Verre", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\(\s*canette\s*\)", " Canette", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*/\s*", " / ", s)
    s = re.sub(r"\s*-\s*", " - ", s)
    s = re.sub(r"\s+", " ", s).strip()

    brand_map = {
        "coca cola": "Coca-Cola",
        "coca-cola": "Coca-Cola",
        "coca/cola": "Coca-Cola",
        "red bull": "Red Bull",
        "m&m's": "M&M's",
        "m&ms": "M&M's",
        "kinder bueno": "Kinder Bueno",
        "kinder maxi": "Kinder Maxi",
        "san benedetto": "San Benedetto",
        "san pellegrino": "San Pellegrino",
        "novotel": "Novotel",
        "michel&augustin": "Michel & Augustin",
        "michel & augustin": "Michel & Augustin",
        "nuxe": "Nuxe",
        "perrier": "Perrier",
        "evian": "Evian",
        "vittel": "Vittel",
        "orangina": "Orangina",
        "fuze tea": "Fuze Tea",
        "fuzetea": "Fuze Tea",
        "kit kat": "Kit Kat",
        "kitkat": "Kit Kat",
        "toblerone": "Toblerone",
        "tobleron": "Toblerone",
    }
    lower_s = s.lower()
    for k, v in sorted(brand_map.items(), key=lambda x: -len(x[0])):
        if k in lower_s:
            s = re.compile(re.escape(k), re.IGNORECASE).sub(v, s)

    small = {
        "de", "à", "et", "au", "aux", "la", "le", "les", "du", "des",
        "d'", "l'", "en", "sur", "pour", "avec", "sans", "ou", "un", "une", "a", "of", "and", "x",
    }
    words = s.split(" ")
    result = []
    for i, w in enumerate(words):
        if not w:
            continue
        m = re.match(r"^(\d+[.,]?\d*)(cl|g|ml|l|cm|kg|mm)$", w, re.I)
        if m:
            result.append(m.group(1) + m.group(2).lower())
            continue
        if re.match(r"^\d", w) or w.upper() in {"USB", "IPX8", "BIO", "AOP", "SPF", "BTE"}:
            result.append(w)
            continue
        if any(c in w for c in "-&'"):
            parts = re.split(r"([-&'])", w)
            new_parts = []
            for p in parts:
                if p in "-&'":
                    new_parts.append(p)
                elif p:
                    new_parts.append(p[0].upper() + p[1:].lower() if len(p) > 1 else p.upper())
            result.append("".join(new_parts))
            continue
        lower = w.lower()
        if i > 0 and lower in small:
            result.append(lower)
        else:
            result.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())

    s = " ".join(result)
    s = re.sub(r"\bCoca-cola\b", "Coca-Cola", s)
    s = re.sub(r"\bM&m's\b", "M&M's", s, flags=re.I)
    s = re.sub(r"\bRed bull\b", "Red Bull", s, flags=re.I)
    s = re.sub(r"\bBiere\b", "Bière", s)
    return re.sub(r"\s+", " ", s).strip()


def map_gamme_series(s: pd.Series) -> pd.Series:
    return s.map(lambda x: GAMME_MAP.get(str(x).strip(), x) if pd.notna(x) else x)


def compute_categorie_row(type_, gamme_raw, gamme) -> str:
    if pd.isna(type_):
        return "Unknown"
    if str(type_).strip().upper().replace(" ", "") in {"NON-F&B", "NONF&B"}:
        return "NonF&B"

    g_raw = str(gamme_raw).strip() if pd.notna(gamme_raw) else ""
    g = str(gamme).strip() if pd.notna(gamme) else ""

    if g in ("SALTY FOOD", "SUGARY FOOD"):
        if "(Fresh)" in g_raw or g_raw == "FOOD SALEE":
            return "Fresh"
        if "(Dry)" in g_raw or g_raw == "FOOD SUCREE":
            return "Dry"
        return "Unknown"

    return g if g else "Unknown"


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def build_lookups(map_df: pd.DataFrame):
    """Retourne deux DataFrames prêts pour un merge."""
    m = map_df.copy()
    m["nom_boutique"] = m["nom_boutique"].astype(str).str.strip()
    m["nom_produit_raw"] = m["nom_produit_raw"].astype(str).str.strip()

    # (hôtel, produit) — on garde la première occurrence (suffisant)
    by_hp = (
        m.drop_duplicates(subset=["nom_boutique", "nom_produit_raw"], keep="first")
        [["nom_boutique", "nom_produit_raw", "type", "gamme", "nom_produit", "categorie"]]
        .rename(columns={
            "type": "type_map_hp",
            "gamme": "gamme_map_hp",
            "nom_produit": "nom_produit_map_hp",
            "categorie": "categorie_map_hp",
        })
    )

    # produit seul — mode (valeur la plus fréquente)
    def mode_or_first(s):
        m = s.mode()
        return m.iloc[0] if len(m) else s.iloc[0]

    by_p = (
        m.groupby("nom_produit_raw", as_index=False)
        .agg(
            type_map_p=("type", mode_or_first),
            gamme_map_p=("gamme", mode_or_first),
            nom_produit_map_p=("nom_produit", mode_or_first),
            categorie_map_p=("categorie", mode_or_first),
        )
    )

    return by_hp, by_p


# ---------------------------------------------------------------------------
# Nettoyage principal (vectorisé)
# ---------------------------------------------------------------------------
def clean_raw(raw_df: pd.DataFrame, by_hp: pd.DataFrame, by_p: pd.DataFrame) -> pd.DataFrame:
    df = raw_df.copy()

    # Sauvegarde raw
    df["TYPE_RAW"] = df["TYPE"] if "TYPE" in df.columns else pd.NA
    df["GAMME_RAW"] = df["GAMME"] if "GAMME" in df.columns else pd.NA
    df["NOM_PRODUIT_RAW"] = df["NOM_PRODUIT"] if "NOM_PRODUIT" in df.columns else pd.NA

    # Clés normalisées pour le merge
    df["_boutique_key"] = df["NOM_BOUTIQUE"].astype(str).str.strip()
    df["_produit_key"] = df["NOM_PRODUIT_RAW"].astype(str).str.strip()

    # Merge 1 : (hôtel, produit)
    df = df.merge(
        by_hp,
        left_on=["_boutique_key", "_produit_key"],
        right_on=["nom_boutique", "nom_produit_raw"],
        how="left",
        suffixes=("", "_drop"),
    )
    df.drop(columns=[c for c in df.columns if c.endswith("_drop") or c in ("nom_boutique", "nom_produit_raw")], inplace=True, errors="ignore")

    # Merge 2 : produit seul
    df = df.merge(
        by_p,
        left_on="_produit_key",
        right_on="nom_produit_raw",
        how="left",
        suffixes=("", "_drop2"),
    )
    df.drop(columns=[c for c in df.columns if c.endswith("_drop2") or c == "nom_produit_raw"], inplace=True, errors="ignore")

    # Résolution : priorité hotel+produit > produit > règles globales
    df["TYPE"] = (
        df["type_map_hp"]
        .combine_first(df["type_map_p"])
        .combine_first(df["TYPE_RAW"])
    )

    df["GAMME"] = (
        df["gamme_map_hp"]
        .combine_first(df["gamme_map_p"])
        .combine_first(map_gamme_series(df["GAMME_RAW"]))
    )

    # Nom produit : mapping > clean fonction
    print("  → Nettoyage des noms de produits…")
    cleaned_names = df["NOM_PRODUIT_RAW"].map(clean_product_name)
    df["NOM_PRODUIT"] = (
        df["nom_produit_map_hp"]
        .combine_first(df["nom_produit_map_p"])
        .combine_first(cleaned_names)
    )

    # Categorie : mapping > calcul
    print("  → Calcul des catégories…")
    cat_from_map = df["categorie_map_hp"].combine_first(df["categorie_map_p"])
    cat_computed = [
        compute_categorie_row(t, gr, g)
        for t, gr, g in zip(df["TYPE"], df["GAMME_RAW"], df["GAMME"])
    ]
    df["CATEGORIE"] = cat_from_map.combine_first(pd.Series(cat_computed, index=df.index))

    # Nettoyage colonnes techniques
    drop_cols = [
        "_boutique_key", "_produit_key",
        "type_map_hp", "gamme_map_hp", "nom_produit_map_hp", "categorie_map_hp",
        "type_map_p", "gamme_map_p", "nom_produit_map_p", "categorie_map_p",
    ]
    df.drop(columns=[c for c in drop_cols if c in df.columns], inplace=True)

    # Ordre des colonnes : tout le reste, puis les raw + clean
    core = ["TYPE_RAW", "TYPE", "GAMME_RAW", "GAMME", "NOM_PRODUIT_RAW", "NOM_PRODUIT", "CATEGORIE"]
    other = [c for c in df.columns if c not in core]
    df = df[other + core]

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Nettoie hotel_sales_raw_data.xlsx → hotel_sales_raw_clean.xlsx")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.raw.exists():
        print(f"❌ Fichier brut introuvable : {args.raw.resolve()}")
        print("   Exemple : python clean_hotel_sales.py --raw /chemin/hotel_sales_raw_data.xlsx")
        sys.exit(1)
    if not args.map.exists():
        print(f"❌ Fichier mapping introuvable : {args.map.resolve()}")
        print("   Place hotels_produits_nettoyes.xlsx à côté du script ou utilise --map")
        sys.exit(1)

    print(f"1. Mapping  : {args.map}")
    map_df = pd.read_excel(args.map, sheet_name="produits_corriges")
    print(f"   → {len(map_df):,} lignes de référence")

    print("2. Lookups…")
    by_hp, by_p = build_lookups(map_df)
    print(f"   → {len(by_hp):,} couples (hôtel, produit)")
    print(f"   → {len(by_p):,} produits uniques")

    print(f"3. Brut     : {args.raw}")
    raw_df = pd.read_excel(args.raw)
    print(f"   → {len(raw_df):,} lignes | colonnes : {list(raw_df.columns)}")

    required = {"NOM_BOUTIQUE", "NOM_PRODUIT"}
    missing = required - set(raw_df.columns)
    if missing:
        print(f"❌ Colonnes manquantes : {missing}")
        sys.exit(1)

    print("4. Nettoyage…")
    clean_df = clean_raw(raw_df, by_hp, by_p)

    print(f"5. Écriture : {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Excel a une limite de ~1M lignes ; pour 130k c'est OK
    clean_df.to_excel(args.out, index=False, sheet_name="sales_clean")
    size_mo = args.out.stat().st_size / (1024 * 1024)
    print(f"   → {len(clean_df):,} lignes | {size_mo:.1f} Mo")

    print("\n✅ Terminé →", args.out.resolve())
    print("\nColonnes ajoutées / normalisées :")
    print("  TYPE_RAW          → TYPE")
    print("  GAMME_RAW         → GAMME")
    print("  NOM_PRODUIT_RAW   → NOM_PRODUIT")
    print("  CATEGORIE         (Fresh / Dry / NonF&B / ou fallback gamme)")


if __name__ == "__main__":
    main()
EOF