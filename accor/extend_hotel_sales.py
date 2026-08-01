#!/usr/bin/env python3
"""
Étend hotel_sales_raw_clean_data.xlsx avec :

  - SOLUTION            simply | liberty | connected (pilotes ROD)
  - HOTEL_CODE          code hôtel Accor
  - HOTEL_NAME          nom hôtel (hotel_data, sinon NOM_BOUTIQUE)
  - METRES_LINEAIRES    m_lin corner hôtel (même source que le simulateur)
  - PRIX_TTC_MARCHE     prix unitaire marché (médiane) × QUANTITE
  - MARGE               PRIX_TTC − PRIX_TTC_MARCHE
                        (PRIX_TTC est déjà le total ligne)

Ordre des colonnes (aligné notebook main.ipynb) :
  SOLUTION, HOTEL_CODE, HOTEL_NAME, METRES_LINEAIRES,
  TYPE / GAMME / NOM_PRODUIT (+ raw + CATEGORIE),
  puis le reste, puis PRIX_TTC_MARCHE, MARGE

Mètres linéaires (aligné hotel_context / director) :
  hotel_metres_lineaires_dedies_corner
  sinon hotel_corner_de_vente_actuel_metres_lineaires
  (NaN si non renseigné dans hotel_data — le simulateur bascule alors sur 6 m)

Usage :
  python extend_hotel_sales.py
  python extend_hotel_sales.py \\
      --clean data/hotel_sales_raw_clean_data.xlsx \\
      --out   data/hotel_sales_raw_extended_data.xlsx
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_CLEAN = ROOT / "data" / "hotel_sales_raw_clean_data.xlsx"
DEFAULT_OUT = ROOT / "data" / "hotel_sales_raw_extended_data.xlsx"
DEFAULT_HOTEL = ROOT / "data" / "hotel_data.xlsx"

# Colonnes hotel_data (même ordre de priorité que HotelContextBuilder)
COL_M_LIN_DEDIE = "hotel_metres_lineaires_dedies_corner"
COL_M_LIN_ACTUEL = "hotel_corner_de_vente_actuel_metres_lineaires"

# Boutique caisse (NOM_BOUTIQUE) → hotel_code Accor
# Source : archive/data/reference/hotel_identity_registry.json + tests + rod_recap
# Attention : "Novotel Paris Tour Eiffel" = H3546 Centre (Quai de Grenelle),
# PAS H1978 Vaugirard Montparnasse (faux positif du matcher fuzzy).
BOUTIQUE_TO_CODE: dict[str, str] = {
    "ibis budget nice": "H2075",
    "ibis budget strasbourg centre republique": "HB6A3",
    "mercure paris boulogne": "H6188",
    "novotel megeve mont blanc": "HB5I0",
    "mercure paris montmartre sacre coeur": "H0373",
    "novotel paris tour eiffel": "H3546",
    "novotel paris centre tour eiffel": "H3546",
    "novotel porte d italie": "H5586",
    "novotel paris 13 porte d italie": "H5586",
}


def _norm(s: object) -> str:
    text = str(s).strip().lower()
    # Ligatures / caractères spéciaux FR avant NFKD
    for a, b in (
        ("œ", "oe"),
        ("æ", "ae"),
        ("ß", "ss"),
        ("’", "'"),
        ("‘", "'"),
        ("ʼ", "'"),
    ):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def boutique_to_code(name: object) -> str | None:
    """Match exact sur nom normalisé uniquement (pas de fuzzy substring)."""
    key = _norm(name)
    return BOUTIQUE_TO_CODE.get(key)


def load_pilot_map() -> dict[str, str]:
    """hotel_code → simply|liberty|connected (rod_pilot_concepts.json)."""
    sys.path.insert(0, str(ROOT / "src"))
    from accor.hotel_solutions import load_pilot_solution_codes

    raw = load_pilot_solution_codes()
    return {code: sol.lower() for code, sol in raw.items()}


def load_hotel_lookup(hotel_path: Path) -> pd.DataFrame:
    """
    Table HOTEL_CODE → HOTEL_NAME + METRES_LINEAIRES.

    M_lin aligné sur ``HotelContextBuilder`` (hotel_context.py) :
      1. hotel_metres_lineaires_dedies_corner
      2. hotel_corner_de_vente_actuel_metres_lineaires
    """
    if not hotel_path.exists():
        raise FileNotFoundError(f"hotel_data introuvable : {hotel_path}")

    hotels = pd.read_excel(hotel_path)
    if "hotel_code" not in hotels.columns:
        raise ValueError("Colonne hotel_code absente de hotel_data.xlsx")

    frame = pd.DataFrame(
        {"HOTEL_CODE": hotels["hotel_code"].astype(str).str.strip()}
    )
    if "hotel_name" in hotels.columns:
        frame["HOTEL_NAME"] = hotels["hotel_name"].astype(str).str.strip()
    else:
        frame["HOTEL_NAME"] = pd.NA

    dedie = (
        pd.to_numeric(hotels[COL_M_LIN_DEDIE], errors="coerce")
        if COL_M_LIN_DEDIE in hotels.columns
        else pd.Series(pd.NA, index=hotels.index)
    )
    actuel = (
        pd.to_numeric(hotels[COL_M_LIN_ACTUEL], errors="coerce")
        if COL_M_LIN_ACTUEL in hotels.columns
        else pd.Series(pd.NA, index=hotels.index)
    )
    # 0 ou négatif = non renseigné utile
    dedie = dedie.where(dedie.notna() & (dedie > 0), other=pd.NA)
    actuel = actuel.where(actuel.notna() & (actuel > 0), other=pd.NA)
    frame["METRES_LINEAIRES"] = dedie.combine_first(actuel)
    return frame.drop_duplicates("HOTEL_CODE", keep="first")


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ordre stable pour analyses / GROUP BY notebook :

      SOLUTION, HOTEL_CODE, HOTEL_NAME, METRES_LINEAIRES,
      TYPE, TYPE_RAW, GAMME, GAMME_RAW, NOM_PRODUIT, NOM_PRODUIT_RAW, CATEGORIE,
      … reste transactionnel …,
      PRIX_TTC_MARCHE, MARGE
    """
    head = [
        "SOLUTION",
        "HOTEL_CODE",
        "HOTEL_NAME",
        "METRES_LINEAIRES",
        "NOM_BOUTIQUE",
        "TYPE",
        "TYPE_RAW",
        "GAMME",
        "GAMME_RAW",
        "NOM_PRODUIT",
        "NOM_PRODUIT_RAW",
        "CATEGORIE",
    ]
    tail = ["PRIX_TTC_MARCHE", "MARGE"]
    middle = [
        c
        for c in df.columns
        if c not in head and c not in tail
    ]
    ordered = [c for c in head if c in df.columns] + middle + [
        c for c in tail if c in df.columns
    ]
    # colonnes imprévues déjà couvertes par middle ; garanti exhaustif
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]


def extend(
    df: pd.DataFrame,
    pilot_map: dict[str, str],
    hotel_lookup: pd.DataFrame | None = None,
) -> pd.DataFrame:
    out = df.copy()

    codes = out["NOM_BOUTIQUE"].map(boutique_to_code)
    out["HOTEL_CODE"] = codes
    out["SOLUTION"] = codes.map(
        lambda c: pilot_map.get(c) if isinstance(c, str) else pd.NA
    )

    # Nom hôtel + mètres linéaires (hotel_data)
    if hotel_lookup is not None and not hotel_lookup.empty:
        out = out.merge(hotel_lookup, on="HOTEL_CODE", how="left")
    else:
        out["HOTEL_NAME"] = pd.NA
        out["METRES_LINEAIRES"] = pd.NA

    # Fallback nom : boutique caisse si pas de match hotel_data
    if "HOTEL_NAME" not in out.columns:
        out["HOTEL_NAME"] = pd.NA
    out["HOTEL_NAME"] = out["HOTEL_NAME"].where(
        out["HOTEL_NAME"].notna()
        & ~out["HOTEL_NAME"].astype(str).isin(["", "nan", "None", "NaN", "<NA>"]),
        other=out["NOM_BOUTIQUE"],
    )

    q = pd.to_numeric(out["QUANTITE"], errors="coerce").fillna(1.0)
    prix_ttc = pd.to_numeric(out["PRIX_TTC"], errors="coerce")

    ean = out["CODE_EAN"].astype(str).str.strip()
    ean = ean.where(~ean.isin(["", "nan", "None", "NaN", "<NA>"]), other=pd.NA)
    prod_key = ean.fillna(out["NOM_PRODUIT"].astype(str).str.strip())

    # PRIX_TTC = total ligne → unitaire = TTC / |QUANTITE| (ignore qty ≤ 0 pour le barème)
    abs_q = q.abs().where(q != 0, other=pd.NA)
    unit_ttc = prix_ttc / abs_q
    # Uniquement ventes "normales" pour la médiane de référence
    unit_for_ref = unit_ttc.where(q > 0)
    unit_market = unit_for_ref.groupby(prod_key).transform("median")
    unit_market = unit_market.fillna(
        unit_for_ref.groupby(out["NOM_PRODUIT"].astype(str)).transform("median")
    )

    # Marché total ligne = unitaire habituel × QUANTITE (signe conservé si retour)
    out["PRIX_TTC_MARCHE"] = (unit_market * q).astype(float)
    # Marge = total vendu − total marché (PRIX_TTC déjà total, pas de × qty)
    out["MARGE"] = (prix_ttc - out["PRIX_TTC_MARCHE"]).astype(float)

    return reorder_columns(out)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Étend les ventes clean avec solution + m_lin + prix marché + marge"
    )
    parser.add_argument("--clean", type=Path, default=DEFAULT_CLEAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--hotel", type=Path, default=DEFAULT_HOTEL)
    args = parser.parse_args()

    if not args.clean.exists():
        print(f"❌ Clean introuvable : {args.clean}")
        sys.exit(1)

    print(f"1. Clean    : {args.clean}")
    df = pd.read_excel(args.clean, sheet_name=0)
    print(f"   → {len(df):,} lignes")

    print("2. Pilotes solution (rod_pilot_concepts.json)…")
    pilot_map = load_pilot_map()
    print(f"   → {pilot_map}")

    print(f"3. Lookup hôtel ({args.hotel.name})…")
    hotel_lookup = load_hotel_lookup(args.hotel)
    n_filled = hotel_lookup["METRES_LINEAIRES"].notna().sum()
    print(f"   → {len(hotel_lookup):,} hôtels | {n_filled} avec m_lin renseigné")

    print("4. Extension…")
    extended = extend(df, pilot_map, hotel_lookup=hotel_lookup)
    print("   colonnes :", list(extended.columns))
    print("   SOLUTION :")
    print(extended["SOLUTION"].value_counts(dropna=False).to_string())
    print("   par hôtel :")
    print(
        extended.groupby(
            [
                "SOLUTION",
                "HOTEL_CODE",
                "HOTEL_NAME",
                "METRES_LINEAIRES",
            ],
            dropna=False,
        )
        .size()
        .to_string()
    )
    print(
        f"   MARGE mean={extended['MARGE'].mean():.3f} "
        f"median={extended['MARGE'].median():.3f} "
        f"sum={extended['MARGE'].sum():.2f}"
    )

    print(f"5. Écriture : {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    extended.to_excel(args.out, index=False, sheet_name="sales_extended")
    size_mo = args.out.stat().st_size / (1024 * 1024)
    print(f"   → {len(extended):,} lignes | {size_mo:.1f} Mo")
    print("\n✅", args.out.resolve())
    print(
        "\nColonnes (ordre notebook) :\n"
        "  SOLUTION, HOTEL_CODE, HOTEL_NAME, METRES_LINEAIRES,\n"
        "  TYPE / GAMME / NOM_PRODUIT (+ raw + CATEGORIE),\n"
        "  … transaction …, PRIX_TTC_MARCHE, MARGE"
    )


if __name__ == "__main__":
    main()
