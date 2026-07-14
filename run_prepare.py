#!/usr/bin/env python3
"""Exécute le pipeline prepare/ décrit dans consignes.txt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREPARE = ROOT / "prepare"
sys.path.insert(0, str(ROOT))
for sub in ("RodPrep", "SalesPrep", "MeteoPrep", "ProximityPrep", "AllPrep"):
    sys.path.insert(0, str(PREPARE / sub / "Src"))

from all_prep.prep import AllPrep
from meteo_prep.prep import MeteoPrep
from proximity_prep.prep import ProximityPrep
from rod_prep.prep import RodPrep
from sales_prep.pipeline import SalesPrep
from rod_ia.config.settings import get_settings


def _paths() -> dict[str, Path]:
    base = PREPARE
    return {
        "rod_input": base / "RodPrep" / "Input",
        "rod_output": base / "RodPrep" / "Output",
        "meteo_input": base / "MeteoPrep" / "Input",
        "meteo_output": base / "MeteoPrep" / "Output",
        "prox_input": base / "ProximityPrep" / "Input",
        "prox_output": base / "ProximityPrep" / "Output",
        "sales_input": base / "SalesPrep" / "Input",
        "sales_output": base / "SalesPrep" / "Output",
        "all_input": base / "AllPrep" / "Input",
        "all_output": base / "AllPrep" / "Output",
    }


def run_pipeline(*, skip_meteo: bool = False, skip_proximity: bool = False) -> None:
    settings = get_settings()
    paths = _paths()

    print("[prepare] Step 1 — RodPrep")
    rod = RodPrep(paths["rod_input"], paths["rod_output"])
    rod.seed_input_from_sources()
    hotel_lookup = rod.run()
    print(f"  → {len(hotel_lookup)} hôtels")

    print("[prepare] Step 2 — MeteoPrep")
    meteo_frame = None
    if not skip_meteo:
        # Années ventes typiques + année en cours (défaut MeteoPrep = année en cours seule)
        from datetime import datetime

        current = datetime.utcnow().year
        meteo_years = tuple(range(current - 3, current + 1))
        meteo = MeteoPrep(
            paths["meteo_input"],
            paths["meteo_output"],
            target_years=meteo_years,
        )
        meteo.fill_input_from_rod(paths["rod_output"])
        meteo_frame = meteo.run()
        print(f"  → {len(meteo_frame)} lignes météo (années {meteo_years})")

    print("[prepare] Step 3 — ProximityPrep")
    prox_frame = None
    if not skip_proximity:
        prox = ProximityPrep(paths["prox_input"], paths["prox_output"])
        prox.fill_input_from_rod(paths["rod_output"])
        prox_frame = prox.run()
        print(f"  → {len(prox_frame)} hôtels proximité")

    print("[prepare] Step 4 — SalesPrep")
    sales_path = settings.sales_csv_path
    paths["sales_input"].mkdir(parents=True, exist_ok=True)
    sales_input_copy = paths["sales_input"] / "ventes.csv"
    if not sales_input_copy.exists() and sales_path.exists():
        sales_input_copy.write_bytes(sales_path.read_bytes())

    lookup_cols = hotel_lookup[["nom_hotel", "hotel_code"]].drop_duplicates()
    sales = SalesPrep(
        sales_path=sales_path,
        output_dir=paths["sales_output"],
        rod_lookup=lookup_cols,
        holdout_year=2026,
        feature_store_dir=settings.feature_store_dir,
    )
    joined = sales.run()
    print(f"  → {len(joined)} lignes jointes ventes")

    print("[prepare] Step 5 — AllPrep")
    paths["all_input"].mkdir(parents=True, exist_ok=True)
    joined.to_parquet(paths["all_input"] / "sales_joined.parquet", index=False)
    hotel_lookup.to_parquet(paths["all_input"] / "rod_hotel_lookup.parquet", index=False)
    if meteo_frame is not None:
        meteo_frame.to_parquet(paths["all_input"] / "meteo_monthly.parquet", index=False)
    if prox_frame is not None:
        prox_frame.to_parquet(paths["all_input"] / "proximity.parquet", index=False)

    all_prep = AllPrep(paths["all_input"], paths["all_output"])
    final = all_prep.run()
    print(f"[prepare] Terminé — dataset final : {len(final)} lignes")
    print(f"[prepare] Sortie : {paths['all_output'] / 'dataset_full.parquet'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline prepare/ (consignes.txt)")
    parser.add_argument("--skip-meteo", action="store_true", help="Ignore MeteoPrep (pas d'appel API)")
    parser.add_argument("--skip-proximity", action="store_true", help="Ignore ProximityPrep")
    args = parser.parse_args()
    try:
        run_pipeline(skip_meteo=args.skip_meteo, skip_proximity=args.skip_proximity)
    except Exception as exc:
        print(f"[prepare] Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())