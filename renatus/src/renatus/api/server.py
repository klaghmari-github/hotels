"""
Point d'entree serveur HTTP : renatus-api / python -m renatus.api.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from renatus.pipeline.netutil import find_free_port
from renatus.pipeline.workspace import (
    normalize_db_and_pipeline,
    prepare_workspace,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renatus-api",
        description="Serveur API HTTP JSON renatus (FastAPI + uvicorn).",
    )
    parser.add_argument("db_path", help="Chemin vers le fichier DuckDB")
    parser.add_argument(
        "pipeline_path",
        help="Dossier flow/ ou fichier YAML du flux",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port HTTP (defaut 8000 ; si occupe, port libre suivant sauf --strict-port)",
    )
    parser.add_argument(
        "--strict-port",
        action="store_true",
        default=False,
        help="Echouer si --port est deja utilise",
    )
    parser.add_argument("--read-only", action="store_true", default=False)
    parser.add_argument("--max-rows", type=int, default=200)
    parser.add_argument(
        "--no-create",
        action="store_true",
        default=False,
        help="Ne pas creer les chemins manquants",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    db_path, pipeline_path = normalize_db_and_pipeline(
        args.db_path,
        args.pipeline_path,
    )
    try:
        db_path, pipeline_path = prepare_workspace(
            db_path,
            pipeline_path,
            read_only=args.read_only,
            create=not args.no_create,
        )
    except FileNotFoundError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1

    try:
        port = find_free_port(
            args.host,
            args.port,
            strict=args.strict_port,
        )
    except OSError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1

    if port != args.port:
        print(
            f"Attention: le port {args.port} est occupe ; "
            f"utilisation du port libre {port}.",
            file=sys.stderr,
        )

    try:
        import uvicorn
    except ImportError:
        print(
            "Erreur: fastapi/uvicorn manquants (pip install -e .)",
            file=sys.stderr,
        )
        return 1

    from renatus.api.app import create_app

    app = create_app(
        db_path=db_path,
        pipelines_dir=pipeline_path,
        read_only=args.read_only,
        max_rows=args.max_rows,
    )
    print(
        f"renatus-api: db={db_path} flow={pipeline_path} "
        f"http://{args.host}:{port}",
        file=sys.stderr,
    )
    uvicorn.run(app, host=args.host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
