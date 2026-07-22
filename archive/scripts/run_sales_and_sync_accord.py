#!/usr/bin/env python3
"""
Exécute SalesPrep (archive) puis synchronise hotel_sales_data → accord/data
et reconstruit data.xlsx (All Data).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ARCHIVE = Path(__file__).resolve().parents[1]
ROOT = ARCHIVE.parent
sys.path.insert(0, str(ARCHIVE))

from prepare.sales_prep.pipeline import SalesPrep  # noqa: E402


def main() -> int:
    sales_csv = ARCHIVE / "prepare" / "SalesPrep" / "Input" / "ventes.csv"
    if not sales_csv.exists():
        sales_csv = ARCHIVE / "sources" / "raw" / "001.queryVentes.csv"
    out = ARCHIVE / "prepare" / "SalesPrep" / "Output"
    hol = ARCHIVE / "prepare" / "SalesPrep" / "Input" / "hotel_holidays_data.parquet"
    if not hol.exists():
        hol = ARCHIVE / "prepare" / "HolidaysPrep" / "Output" / "hotel_holidays_data.parquet"
    rod = ARCHIVE / "prepare" / "RodPrep" / "Output" / "hotel_lookup.parquet"
    accord_data = ROOT / "accord" / "data"

    lookup = None
    if rod.exists():
        lookup = pd.read_parquet(rod)
        if "nom_hotel" not in lookup.columns and "name_ventes" in lookup.columns:
            lookup = lookup.rename(columns={"name_ventes": "nom_hotel"})

    print("[1/3] SalesPrep…")
    prep = SalesPrep(
        sales_path=sales_csv,
        output_dir=out,
        rod_lookup=lookup[["nom_hotel", "hotel_code"]].drop_duplicates()
        if lookup is not None
        else None,
        holdout_year=2026,
        holidays_path=hol if hol.exists() else None,
        copy_to=accord_data,
    )
    joined = prep.run()
    pct_cols = [c for c in joined.columns if c.startswith("pct_")]
    print(f"  → {len(joined)} lignes, {len(joined.columns)} cols, {len(pct_cols)} pct_*")
    print(f"  → Excel : {out / 'hotel_sales_data.xlsx'}")
    print(f"  → Copie : {accord_data / 'hotel_sales_data.xlsx'}")

    print("[2/3] Rebuild All Data (accord)…")
    sys.path.insert(0, str(ROOT / "accord"))
    from join_data import build_joined_dataframe, save_joined_excel  # noqa: E402

    frame = build_joined_dataframe(fill_weather=True, fill_proximity=False)
    path = save_joined_excel(frame)
    print(f"  → {path} shape={frame.shape}")

    print("[3/3] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
