#!/usr/bin/env python3
"""
Ouvre l'interface web DuckDB (extension ui) branchée sur la base principale.

Important (doc DuckDB) :
  L'UI ne peut PAS tourner directement sur une base read-only
  (elle a besoin d'un catalogue interne `_duckdb_ui` en écriture).
  On démarre donc l'UI sur un petit fichier writable, puis on ATTACH
  main.duckdb en lecture seule.

Usage (depuis release_1_0_0/, venv active) :

  python scripts/start_duckdb_ui.py
  python run.py duckdb-ui

  # si l'extension est obsolete / erreur _duckdb_ui :
  python scripts/start_duckdb_ui.py --force-install

  # si lock sur ui_catalog.duckdb :
  python scripts/start_duckdb_ui.py --kill-lock
  # ou catalogue temporaire :
  python scripts/start_duckdb_ui.py --fresh

Ctrl+C pour arreter.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DB = ROOT / "data" / "duckdb" / "main" / "main.duckdb"
UI_CATALOG = ROOT / "data" / "duckdb" / "ui_catalog.duckdb"


def _pids_locking(path: Path) -> list[int]:
    pids: set[int] = set()
    try:
        out = subprocess.check_output(
            ["fuser", str(path)],
            stderr=subprocess.STDOUT,
            text=True,
        )
        for m in re.finditer(r"(\d+)", out):
            pids.add(int(m.group(1)))
    except Exception:
        pass
    # scan cmdline
    me = os.getpid()
    for pid_s in os.listdir("/proc"):
        if not pid_s.isdigit():
            continue
        pid = int(pid_s)
        if pid == me:
            continue
        try:
            cmd = (
                open(f"/proc/{pid}/cmdline", "rb")
                .read()
                .replace(b"\0", b" ")
                .decode(errors="replace")
            )
        except Exception:
            continue
        if "start_duckdb_ui" in cmd or str(path) in cmd or "ui_catalog.duckdb" in cmd:
            pids.add(pid)
    return sorted(pids)


def _kill_pids(pids: list[int]) -> None:
    for p in pids:
        try:
            os.kill(p, signal.SIGTERM)
            print(f"  SIGTERM {p}")
        except ProcessLookupError:
            pass
    time.sleep(1.0)
    for p in pids:
        try:
            os.kill(p, 0)
            os.kill(p, signal.SIGKILL)
            print(f"  SIGKILL {p}")
        except ProcessLookupError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Demarre DuckDB UI attachee a main.duckdb"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"Base metier a explorer (defaut: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--ui-catalog",
        type=Path,
        default=UI_CATALOG,
        help=f"Petit .duckdb writable pour l'UI (defaut: {UI_CATALOG})",
    )
    parser.add_argument(
        "--alias",
        default="main_db",
        help="Alias ATTACH de la base metier (defaut: main_db)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="ATTACHE main.duckdb en lecture/ecriture (defaut: read_only)",
    )
    parser.add_argument(
        "--force-install",
        action="store_true",
        help="FORCE INSTALL ui (corrige souvent Catalog _duckdb_ui missing)",
    )
    parser.add_argument(
        "--kill-lock",
        action="store_true",
        help="Tue les process qui lockent ui_catalog / start_duckdb_ui",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Utilise un ui_catalog temporaire (evite le lock du fichier fixe)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="N'ouvre pas le navigateur (affiche seulement l'URL)",
    )
    args = parser.parse_args(argv)

    db = args.db.expanduser().resolve()
    if args.fresh:
        import tempfile

        ui_cat = Path(tempfile.mkdtemp(prefix="duckdb_ui_")) / "ui_catalog.duckdb"
    else:
        ui_cat = args.ui_catalog.expanduser().resolve()

    if not db.exists():
        print(f"Base introuvable : {db}", file=sys.stderr)
        return 1

    ui_cat.parent.mkdir(parents=True, exist_ok=True)

    if args.kill_lock:
        lock_target = (
            args.ui_catalog.expanduser().resolve()
            if not args.fresh
            else UI_CATALOG
        )
        pids = _pids_locking(lock_target)
        if not pids:
            print("Aucun process bloquant detecte.")
        else:
            print(f"Arret des process : {pids}")
            _kill_pids(pids)

    import duckdb

    print(f"DuckDB {duckdb.__version__}")
    print(f"UI catalog (writable) : {ui_cat}")
    print(f"Base metier           : {db}")
    print(
        f"Attach mode           : "
        f"{'READ_WRITE' if args.write else 'READ_ONLY'}"
    )

    # 1) connexion writable sur le catalogue UI (obligatoire)
    try:
        con = duckdb.connect(str(ui_cat), read_only=False)
    except Exception as exc:
        print(f"Connexion UI catalog impossible : {exc}", file=sys.stderr)
        pids = _pids_locking(ui_cat)
        if pids:
            print(
                f"\nProcess qui tiennent le lock : {pids}\n"
                f"  python scripts/start_duckdb_ui.py --kill-lock\n"
                f"  # ou\n"
                f"  kill {' '.join(str(p) for p in pids)}\n"
                f"  # ou catalogue neuf :\n"
                f"  python scripts/start_duckdb_ui.py --fresh",
                file=sys.stderr,
            )
        else:
            print(
                "Astuce : python scripts/start_duckdb_ui.py --fresh",
                file=sys.stderr,
            )
        return 1

    try:
        # 2) extension UI a jour
        if args.force_install:
            print("FORCE INSTALL ui …")
            con.execute("FORCE INSTALL ui;")
        else:
            try:
                con.execute("INSTALL ui;")
            except Exception:
                print("INSTALL ui a echoue, tentative FORCE INSTALL …")
                con.execute("FORCE INSTALL ui;")
        try:
            con.execute("UPDATE EXTENSIONS;")
        except Exception:
            pass
        con.execute("LOAD ui;")
        print("Extension ui chargee.")

        # 3) attacher la base principale
        alias = str(args.alias).replace('"', "")
        # detache si deja present
        try:
            con.execute(f'DETACH "{alias}";')
        except Exception:
            pass
        ro = "READ_ONLY" if not args.write else "READ_WRITE"
        # echapper le chemin pour SQL
        db_sql = str(db).replace("'", "''")
        con.execute(
            f"ATTACH '{db_sql}' AS \"{alias}\" ({ro});"
        )
        print(f'ATTACH OK → USE "{alias}"; pour interroger la base metier.')

        # 4) demarrer le serveur UI
        # start_ui_server demarre sans bloquer ; start_ui peut renvoyer
        # "already running" si une autre instance existe.
        url = None
        try:
            con.execute("CALL start_ui_server();")
        except Exception as exc:
            msg = str(exc)
            if "already" not in msg.lower():
                print(f"start_ui_server : {exc}", file=sys.stderr)

        try:
            rows = con.execute("CALL get_ui_url();").fetchall()
            if rows and rows[0] and rows[0][0]:
                url = str(rows[0][0])
        except Exception:
            # fallback port par defaut
            try:
                port = con.execute(
                    "SELECT value FROM duckdb_settings() WHERE name='ui_local_port'"
                ).fetchone()
                port = port[0] if port else "4213"
            except Exception:
                port = "4213"
            url = f"http://localhost:{port}"

        # optionnel : forcer le contexte notebook
        try:
            con.execute(f'USE "{alias}";')
        except Exception:
            pass

        print()
        print("=" * 60)
        print(f"DuckDB UI : {url}")
        print(f'Dans un notebook, si besoin :')
        print(f'  USE "{alias}";')
        print(f'  SHOW TABLES;')
        print("=" * 60)
        print("Laisse ce terminal ouvert (Ctrl+C pour quitter).")

        if not args.no_browser and url:
            try:
                webbrowser.open(url)
            except Exception:
                pass

        # garder la connexion + le process vivants
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nArret UI.")
        try:
            con.execute("CALL stop_ui_server();")
        except Exception:
            pass
        return 0
    except Exception as exc:
        print(f"Echec : {exc}", file=sys.stderr)
        print(
            "\nSi l'erreur mentionne Catalog \"_duckdb_ui\" :\n"
            "  1) python scripts/start_duckdb_ui.py --force-install\n"
            "  2) ferme les autres onglets / instances DuckDB UI\n"
            "  3) ne lance PAS l'UI en --write sur main.duckdb en read-only\n"
            "     (ce script utilise un ui_catalog.duckdb writable).",
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
