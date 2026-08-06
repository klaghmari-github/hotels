#!/usr/bin/env python3
"""
Ouvre l'interface web DuckDB (extension ui) sur la base principale.

Usage (depuis release_1_0_0/) :

  .venv/bin/python scripts/start_duckdb_ui.py
  .venv/bin/python scripts/start_duckdb_ui.py --write   # si besoin d'ecrire
  .venv/bin/python scripts/start_duckdb_ui.py --db data/duckdb/main/main.duckdb

Par defaut : lecture seule (compatible avec `python run.py serve` qui tient le lock).
Ctrl+C pour arreter.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DB = ROOT / "data" / "duckdb" / "main" / "main.duckdb"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Demarre DuckDB UI sur main.duckdb"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"Fichier DuckDB (defaut: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Ouvre en ecriture (defaut: lecture seule)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Ne force pas l'ouverture navigateur (si l'API le permet)",
    )
    args = parser.parse_args(argv)

    db = args.db.expanduser().resolve()
    if not db.exists():
        print(f"Base introuvable : {db}", file=sys.stderr)
        return 1

    import duckdb

    read_only = not args.write
    print(f"DuckDB {duckdb.__version__}")
    print(f"Base    : {db}")
    print(f"Mode    : {'lecture seule' if read_only else 'lecture/ecriture'}")

    try:
        con = duckdb.connect(str(db), read_only=read_only)
    except Exception as exc:
        print(f"Connexion impossible : {exc}", file=sys.stderr)
        if read_only:
            print(
                "Astuce : arrete `run.py serve` ou utilise une copie, "
                "ou relance avec --write si aucun autre process ne tient le lock.",
                file=sys.stderr,
            )
        else:
            print(
                "Astuce : arrete le serveur web (`run.py serve`) qui lock la base, "
                "ou relance sans --write (lecture seule).",
                file=sys.stderr,
            )
        return 1

    try:
        # Extension officielle DuckDB UI
        con.execute("INSTALL ui;")
        con.execute("LOAD ui;")
        print("Extension ui chargee.")
        print("Lancement de l'UI (le navigateur devrait s'ouvrir)…")
        # CALL start_ui() demarre le serveur local et ouvre le browser
        con.execute("CALL start_ui();")
        print("UI demarree. Laisse ce terminal ouvert (Ctrl+C pour quitter).")
        # garder le process vivant tant que l'UI tourne
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nArret UI.")
        return 0
    except Exception as exc:
        print(f"Echec start_ui : {exc}", file=sys.stderr)
        print(
            "Verifie la version DuckDB (>= 1.2) et la connectivite "
            "pour INSTALL ui.",
            file=sys.stderr,
        )
        return 1
    finally:
        try:
            con.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
