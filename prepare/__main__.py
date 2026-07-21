"""``python -m prepare`` — lance le pipeline CLI."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline prepare/ — RodPrep d'abord, puis Meteo/Proximity/Sales/All"
    )
    parser.add_argument(
        "--skip-meteo",
        action="store_true",
        help="Ignore MeteoPrep (pas d'appel API météo)",
    )
    parser.add_argument(
        "--skip-proximity",
        action="store_true",
        help="Ignore ProximityPrep (pas d'appel Overpass)",
    )
    parser.add_argument(
        "--skip-holidays",
        action="store_true",
        help="Ignore HolidaysPrep (vacances / fériés)",
    )
    parser.add_argument(
        "--holdout-year",
        type=int,
        default=2026,
        help="Année exclue de l'apprentissage SalesPrep (défaut: 2026)",
    )
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="RodPrep: ne pas géocoder les hôtels sans coords",
    )
    args = parser.parse_args()

    try:
        from prepare import PreparePipeline

        result = PreparePipeline(holdout_year=args.holdout_year).run(
            skip_meteo=args.skip_meteo,
            skip_proximity=args.skip_proximity,
            skip_holidays=args.skip_holidays,
            geocode_missing=not args.no_geocode,
        )
        print(f"[prepare] OK — {result.meta}")
    except Exception as exc:
        print(f"[prepare] Erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
