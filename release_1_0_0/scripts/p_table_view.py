#!/usr/bin/env python3
"""
Matérialise une table / vue pipeline via p_table_view.

Script de dev (scripts/) — hors cœur applicatif.

Usage (depuis release_1_0_0/, venv active) :

  python scripts/p_table_view.py v_hotel_clients
  python scripts/p_table_view.py t_hotel_data

Important :
  Doit écrire dans main.duckdb (celle attachée par DuckDB UI sous l'alias
  main_db). Si main.duckdb est verrouillée (UI, serve, …), arrête le process
  qui la tient puis relance ce script — sinon les objets partent dans
  main_work.duckdb et restent invisibles dans l'UI.
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
    parser.add_argument(
        "--allow-work",
        action="store_true",
        help=(
            "Autorise l'écriture dans main_work.duckdb si main.duckdb "
            "est verrouillée (sinon erreur)"
        ),
    )
    args = parser.parse_args(argv)

    paths = Paths(ROOT).ensure()
    cp = PipelineFactory(paths).open(read_only=args.read_only)
    try:
        db_path = Path(cp.db_path).resolve()
        main_db = Path(paths.main_db).resolve()
        print(f"db: {db_path}")

        if db_path != main_db and not args.read_only:
            msg = (
                f"Écriture sur {db_path.name} au lieu de {main_db.name} "
                f"(base verrouillée par un autre process, souvent "
                f"scripts/start_duckdb_ui.py ou run.py serve).\n"
                f"→ Arrête ce process (Ctrl+C dans son terminal), puis "
                f"relance : python scripts/p_table_view.py {args.name}\n"
                f"→ Ou force le fallback : "
                f"python scripts/p_table_view.py {args.name} --allow-work"
            )
            if not args.allow_work:
                print(msg, file=sys.stderr)
                return 2
            print("WARN: --allow-work → continue sur la copie de travail.", file=sys.stderr)

        rel = cp.p_table_view(args.name)
        df = rel.df()
        print(
            f"OK p_table_view({args.name!r}) — "
            f"rows={len(df)} cols={df.shape[1]}"
        )
        print(f"columns: {list(df.columns)}")
        if args.head > 0 and len(df) > 0:
            print(df.head(args.head).to_string())
        elif args.head > 0:
            print("(vide)")
    finally:
        cp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
