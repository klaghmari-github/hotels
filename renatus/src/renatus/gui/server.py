"""
Point d'entree serveur : renatus-gui / python -m renatus.gui.
"""

from __future__ import annotations

# F0046: silence pandas env noise before any renatus import chain
import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Pandas requires version .* of '(numexpr|bottleneck)'",
    category=UserWarning,
)

import argparse
import sys
from pathlib import Path

from renatus.pipeline.netutil import find_free_port
from renatus.pipeline.project import RenatusProject, is_project_file
from renatus.pipeline.workspace import (
    looks_like_duckdb,
    normalize_db_and_pipeline,
    prepare_workspace,
)

# Layout par defaut (F0069 / A0006) :
#   workspaces/ws_main/proj_main/{flow, main.duckdb, proj_main.renatus.yaml}
DEFAULT_WORKSPACES_DIR = "workspaces"
DEFAULT_WORKSPACE_ID = "ws_main"
DEFAULT_PROJECT_ID = "proj_main"
DEFAULT_PROJECT_ROOT = (
    Path(DEFAULT_WORKSPACES_DIR) / DEFAULT_WORKSPACE_ID / DEFAULT_PROJECT_ID
)
DEFAULT_DB_REL = DEFAULT_PROJECT_ROOT / "main.duckdb"
DEFAULT_PIPE_REL = DEFAULT_PROJECT_ROOT / "flow"
DEFAULT_PROJECT_FILE_REL = (
    DEFAULT_PROJECT_ROOT / f"{DEFAULT_PROJECT_ID}.renatus.yaml"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renatus-gui",
        description=(
            "Renatus GUI — interface web de flux (FastAPI + uvicorn). "
            "Sans argument: demarre sur "
            f"{DEFAULT_PROJECT_ROOT}/ (cree si besoin). "
            "Sinon: <db.duckdb> <flow/>, "
            "ou un fichier .renatus.yaml, "
            "ou --project mon.renatus.yaml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples:\n"
            "  renatus-gui\n"
            "  renatus-gui mon.duckdb flow/\n"
            "  renatus-gui mon.renatus.yaml\n"
            "  renatus-gui --project mon.renatus.yaml\n"
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help=(
            "Optionnel. Fichier projet (.renatus.yaml), "
            "ou db.duckdb + dossier flow (flux). "
            f"Absent = {DEFAULT_PROJECT_ROOT}/ par defaut."
        ),
    )
    parser.add_argument(
        "--project",
        "-p",
        default=None,
        help="Fichier projet .renatus.yaml (db + flow)",
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
        help="Echouer si --port est deja utilise (pas de bascule automatique)",
    )
    parser.add_argument("--read-only", action="store_true", default=False)
    parser.add_argument("--max-rows", type=int, default=200)
    parser.add_argument(
        "--no-create",
        action="store_true",
        default=False,
        help="Ne pas creer les chemins manquants (echoue s'ils absents)",
    )
    return parser


def _find_cwd_project_file(cwd: Path) -> Path | None:
    """Un seul *.renatus.yaml a la racine cwd, sinon None."""
    found = sorted(
        [
            *cwd.glob("*.renatus.yaml"),
            *cwd.glob("*.renatus.yml"),
        ]
    )
    if len(found) == 1:
        return found[0]
    return None


def resolve_startup_paths(
    paths: list[str],
    project_arg: str | None,
    *,
    read_only: bool,
    create: bool,
    cwd: Path | None = None,
) -> tuple[Path, Path, RenatusProject | None, str | None]:
    """
    Retourne (db_path, pipeline_path, project_or_none, info_message).

    Accepte:
      - --project file.renatus.yaml
      - zero path: defaut workspace/ (ou unique .renatus.yaml du cwd)
      - un path .renatus.yaml
      - un path .duckdb → pipelines = <parent>/pipelines
      - un path dossier → pipelines = ce dossier, db = parent/main.duckdb
      - deux paths db + pipelines
    """
    base = (cwd or Path.cwd()).resolve()
    note: str | None = None

    if project_arg:
        project = RenatusProject.load(project_arg)
        db, pipe = prepare_workspace(
            project.db_path,
            project.pipeline_path,
            read_only=read_only or project.read_only,
            create=create and not (read_only or project.read_only),
        )
        return db, pipe, project, None

    if len(paths) == 0:
        # A0006 / F0069: lancer renatus-gui sans argument
        auto_proj = _find_cwd_project_file(base)
        if auto_proj is not None:
            project = RenatusProject.load(auto_proj)
            db, pipe = prepare_workspace(
                project.db_path,
                project.pipeline_path,
                read_only=read_only or project.read_only,
                create=create and not (read_only or project.read_only),
            )
            note = f"Projet detecte: {auto_proj}"
            return db, pipe, project, note

        # workspaces/ws_main/proj_main — cree si absent
        root = (base / DEFAULT_PROJECT_ROOT).expanduser()
        db_path = base / DEFAULT_DB_REL
        pipe_path = base / DEFAULT_PIPE_REL
        proj_file = base / DEFAULT_PROJECT_FILE_REL
        if create and not read_only:
            root.mkdir(parents=True, exist_ok=True)
            note = (
                "Aucun argument: demarrage sur le projet par defaut "
                f"({DEFAULT_PROJECT_ROOT}/). "
                "Passez db+flow ou un .renatus.yaml pour un autre projet."
            )
        db, pipe = prepare_workspace(
            db_path,
            pipe_path,
            read_only=read_only,
            create=create and not read_only,
        )
        # Fichier projet + git-friendly (F0032/F0065)
        project: RenatusProject | None = None
        if create and not read_only:
            if not proj_file.is_file():
                project = RenatusProject.from_workspace(
                    db,
                    pipe,
                    name=DEFAULT_PROJECT_ID,
                    project_file=proj_file,
                )
                written = project.save(proj_file)
                project.project_file = str(written)
            else:
                try:
                    project = RenatusProject.load(proj_file)
                except Exception:
                    project = None
        elif proj_file.is_file():
            try:
                project = RenatusProject.load(proj_file)
            except Exception:
                project = None
        return db, pipe, project, note

    if len(paths) == 1:
        only = Path(paths[0]).expanduser()
        if is_project_file(only):
            project = RenatusProject.load(only)
            db, pipe = prepare_workspace(
                project.db_path,
                project.pipeline_path,
                read_only=read_only or project.read_only,
                create=create and not (read_only or project.read_only),
            )
            return db, pipe, project, None

        # Un seul chemin .duckdb → pipelines a cote
        if looks_like_duckdb(only):
            db_path = only
            pipe_path = only.expanduser().resolve().parent / "flow"
            note = f"Un seul argument base: flow={pipe_path}"
            db, pipe = prepare_workspace(
                db_path,
                pipe_path,
                read_only=read_only,
                create=create and not read_only,
            )
            return db, pipe, None, note

        # Un seul dossier → pipelines, db = parent/main.duckdb ou dossier/../main
        cand = only.expanduser()
        if cand.exists() and cand.is_dir() or only.suffix == "":
            pipe_path = cand
            db_path = cand.expanduser().resolve().parent / "main.duckdb"
            # si le path n existe pas encore et ressemble a pipelines
            if cand.name.lower() in {"flow", "pipelines", "pipeline"}:
                db_path = cand.expanduser().resolve().parent / "main.duckdb"
            note = f"Un seul argument dossier: db={db_path} flow={pipe_path}"
            db, pipe = prepare_workspace(
                db_path,
                pipe_path,
                read_only=read_only,
                create=create and not read_only,
            )
            return db, pipe, None, note

        raise ValueError(
            f"Argument unique non reconnu: {paths[0]!r}.\n"
            "Attendu:\n"
            "  renatus-gui\n"
            "  renatus-gui <projet.renatus.yaml>\n"
            "  renatus-gui <db.duckdb> <flow/>\n"
            "  renatus-gui --project <projet.renatus.yaml>"
        )

    if len(paths) == 2:
        db_path, pipeline_path = normalize_db_and_pipeline(paths[0], paths[1])
        db, pipe = prepare_workspace(
            db_path,
            pipeline_path,
            read_only=read_only,
            create=create and not read_only,
        )
        return db, pipe, None, None

    raise ValueError(
        f"Trop d arguments positionnels ({len(paths)}). "
        "Attendu 0, 1 ou 2 chemins.\n"
        "  renatus-gui\n"
        "  renatus-gui <db.duckdb> <flow/>\n"
        "  renatus-gui <projet.renatus.yaml>"
    )


def main(argv: list[str] | None = None) -> int:
    # filtre deja pose en tete de module / renatus.__init__ (F0046)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        db_path, pipeline_path, project, note = resolve_startup_paths(
            list(args.paths or []),
            args.project,
            read_only=args.read_only,
            create=not args.no_create,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        print(
            "Aide: renatus-gui --help",
            file=sys.stderr,
        )
        return 1

    if note:
        # message utile, sans alarme (demarrage normal sans args)
        print(f"Info: {note}", file=sys.stderr)

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
            "Erreur: fastapi/uvicorn manquants "
            "(pip install -e . pour reinstaller renatus)",
            file=sys.stderr,
        )
        return 1

    from renatus.gui.app import create_gui_app

    ro = args.read_only or (project.read_only if project else False)
    app = create_gui_app(
        db_path=db_path,
        pipeline_path=pipeline_path,
        read_only=ro,
        max_rows=args.max_rows,
    )
    if project is not None:
        svc = getattr(app.state, "gui", None)
        if svc is not None:
            svc._project_file = project.project_file
            svc._project_name = project.name

    proj_msg = ""
    if project is not None:
        proj_msg = f" project={project.project_file}"
    print(
        f"renatus-gui: db={db_path} flow={pipeline_path}"
        f"{proj_msg} http://{args.host}:{port}",
        file=sys.stderr,
    )
    uvicorn.run(app, host=args.host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
