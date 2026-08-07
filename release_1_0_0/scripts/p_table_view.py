#!/usr/bin/env python3
"""
Matérialise une table / vue pipeline via p_table_view.

Script de dev (scripts/) — hors coeur applicatif.

Usage (depuis release_1_0_0/, venv active) :

  python scripts/p_table_view.py v_hotel_clients
  python scripts/p_table_view.py t_hotel_data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# scripts/ → racine release_1_0_0/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline.connection import PipelineFactory
from src.pipeline.paths import Paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ouvre la pipeline et exécute p_table_view(<name>).",
    )
    parser.add_argument(
        "name",
        help="Nom de la table / vue pipeline (ex. v_hotel_clients)",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Ouvre la base en lecture seule (défaut: écriture)",
    )
    parser.add_argument(
        "-n",
        "--head",
        type=int,
        default=20,
        metavar="N",
        help="Affiche les N premières lignes (défaut: 20, 0 = aucune)",
    )
    args = parser.parse_args(argv)

    paths = Paths(ROOT).ensure()
    cp = PipelineFactory(paths).open(read_only=args.read_only)
    try:
        rel = cp.p_table_view(args.name)
        print(rel)
    finally:
        cp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
