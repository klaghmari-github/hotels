#!/usr/bin/env python3
"""
Étend hotel_sales_raw_clean_data.xlsx avec :

  - HOTEL_CODE          code hôtel Accor
  - SOLUTION            simply | liberty | connected (pilotes ROD)
  - PRIX_TTC_MARCHE     prix unitaire marché (médiane) × QUANTITE
  - MARGE               (PRIX_TTC × QUANTITE) − PRIX_TTC_MARCHE

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

# Boutique caisse → hotel_code (évite les faux positifs du matcher générique)
BOUTIQUE_TO_CODE: dict[str, str] = {
    "ibis budget nice": "H2075",
    "ibis budget strasbourg centre republique": "HB6A3",
    "mercure paris boulogne": "H6188",
    "novotel megeve mont blanc": "HB5I0",
    "mercure paris montmartre sacre coeur": "H0373",
    "novotel paris tour eiffel": "H1978",
    # Novotel Porte d'Italie : pas de code fiable dans hotel_data / pilotes
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
    key = _norm(name)
    if key in BOUTIQUE_TO_CODE:
        return BOUTIQUE_TO_CODE[key]
    # tolère tirets / apostrophes déjà normalisés
    for k, code in BOUTIQUE_TO_CODE.items():
        if k in key or key in k:
            return code
    return None


def load_pilot_map() -> dict[str, str]:
    """hotel_code → simply|liberty|connected."""
    sys.path.insert(0, str(ROOT / "src"))
    from accor.hotel_solutions import load_pilot_solution_codes

    raw = load_pilot_solution_codes()
    return {code: sol.lower() for code, sol in raw.items()}


def extend(df: pd.DataFrame, pilot_map: dict[str, str]) -> pd.DataFrame:
    out = df.copy()

    codes = out["NOM_BOUTIQUE"].map(boutique_to_code)
    out["HOTEL_CODE"] = codes
    out["SOLUTION"] = codes.map(
        lambda c: pilot_map.get(c) if isinstance(c, str) else pd.NA
    )

    q = pd.to_numeric(out["QUANTITE"], errors="coerce").fillna(1.0).clip(lower=0)
    prix_ttc = pd.to_numeric(out["PRIX_TTC"], errors="coerce")

    ean = out["CODE_EAN"].astype(str).str.strip()
    ean = ean.where(~ean.isin(["", "nan", "None", "NaN", "<NA>"]), other=pd.NA)
    prod_key = ean.fillna(out["NOM_PRODUIT"].astype(str).str.strip())

    # Prix unitaire habituel = médiane TTC observée du produit
    unit_market = prix_ttc.groupby(prod_key).transform("median")
    unit_market = unit_market.fillna(
        prix_ttc.groupby(out["NOM_PRODUIT"].astype(str)).transform("median")
    )

    # Niveau ligne (× quantité) pour être comparable au CA TTC ligne
    out["PRIX_TTC_MARCHE"] = (unit_market * q).astype(float)
    out["MARGE"] = (prix_ttc * q - out["PRIX_TTC_MARCHE"]).astype(float)

    extra = ["HOTEL_CODE", "SOLUTION", "PRIX_TTC_MARCHE", "MARGE"]
    base = [c for c in out.columns if c not in extra]
    return out[base + extra]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Étend les ventes clean avec solution + prix marché + marge"
    )
    parser.add_argument("--clean", type=Path, default=DEFAULT_CLEAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
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

    print("3. Extension…")
    extended = extend(df, pilot_map)
    print("   SOLUTION :")
    print(extended["SOLUTION"].value_counts(dropna=False).to_string())
    print("   par boutique :")
    print(
        extended.groupby(["NOM_BOUTIQUE", "HOTEL_CODE", "SOLUTION"], dropna=False)
        .size()
        .to_string()
    )
    print(
        f"   MARGE mean={extended['MARGE'].mean():.3f} "
        f"median={extended['MARGE'].median():.3f} "
        f"sum={extended['MARGE'].sum():.2f}"
    )

    print(f"4. Écriture : {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    extended.to_excel(args.out, index=False, sheet_name="sales_extended")
    size_mo = args.out.stat().st_size / (1024 * 1024)
    print(f"   → {len(extended):,} lignes | {size_mo:.1f} Mo")
    print("\n✅", args.out.resolve())
    print(
        "\nColonnes ajoutées :\n"
        "  HOTEL_CODE\n"
        "  SOLUTION           (simply / liberty / connected | vide si non pilote)\n"
        "  PRIX_TTC_MARCHE    (médiane unitaire produit × QUANTITE)\n"
        "  MARGE              (PRIX_TTC × QUANTITE − PRIX_TTC_MARCHE)"
    )


if __name__ == "__main__":
    main()
