"""
Preparation d'un espace de travail (db + flow).

Utilise par renatus-gui et renatus-api pour demarrer meme si les
chemins n'existent pas encore (creation parents, dossier flow vide).

F0090: le dossier utilisateur s appelle ``flow/`` (ex-pipelines/).
"""

from __future__ import annotations

from pathlib import Path

# Dossier des YAML de flux (user-facing)
FLOW_DIR_NAME = "flow"
# Anciens noms encore reconnus (migration)
LEGACY_FLOW_DIR_NAMES = ("pipelines", "pipeline")


def looks_like_duckdb(path: Path) -> bool:
    """True si le chemin designe un fichier base DuckDB."""
    name = path.name.lower()
    return name.endswith(".duckdb") or path.suffix.lower() == ".duckdb"


def looks_like_yaml_file(path: Path) -> bool:
    return path.suffix.lower() in {".yaml", ".yml"}


def looks_like_flow_dir_name(name: str) -> bool:
    n = (name or "").strip().lower()
    return n == FLOW_DIR_NAME or n in LEGACY_FLOW_DIR_NAMES


def default_flow_dir(project_root: str | Path) -> Path:
    """
    Chemin flow par defaut sous un root projet.

    Prefere ``flow/`` ; si seul l ancien ``pipelines/`` existe, le renomme
    en ``flow/`` quand c est possible.
    """
    root = Path(project_root).expanduser()
    flow = root / FLOW_DIR_NAME
    if flow.exists():
        return flow
    for leg in LEGACY_FLOW_DIR_NAMES:
        legacy = root / leg
        if legacy.is_dir():
            try:
                legacy.rename(flow)
                return flow
            except OSError:
                return legacy
    return flow


def normalize_db_and_pipeline(
    first: str | Path,
    second: str | Path,
) -> tuple[Path, Path]:
    """
    Retourne (db_path, flow_path).

    Ordre CLI documente : db puis flow.
    Si l'utilisateur inverse (flow puis db.duckdb), on corrige.
    """
    a = Path(first).expanduser()
    b = Path(second).expanduser()
    a_db = looks_like_duckdb(a)
    b_db = looks_like_duckdb(b)
    if b_db and not a_db:
        return b, a
    return a, b


# alias historique
normalize_db_and_flow = normalize_db_and_pipeline


def prepare_workspace(
    db_path: str | Path,
    pipeline_path: str | Path,
    *,
    read_only: bool = False,
    create: bool = True,
) -> tuple[Path, Path]:
    """
    Prepare les chemins db + flow pour une ouverture.

    Si create et non read_only :
    - cree les dossiers parents de la base
    - cree le dossier flow (ou le parent si chemin fichier YAML)
    - ne cree pas de fichier YAML (UI vide = zero step)

    La base DuckDB elle-meme est creee a la premiere connexion moteur.
    """
    db = Path(db_path).expanduser()
    pipe = Path(pipeline_path).expanduser()

    # Si on pointe encore vers .../pipelines et flow n existe pas a cote
    if (
        pipe.name.lower() in LEGACY_FLOW_DIR_NAMES
        and not pipe.exists()
        and (pipe.parent / FLOW_DIR_NAME).exists()
    ):
        pipe = pipe.parent / FLOW_DIR_NAME
    elif (
        pipe.name.lower() in LEGACY_FLOW_DIR_NAMES
        and pipe.is_dir()
        and not (pipe.parent / FLOW_DIR_NAME).exists()
        and create
        and not read_only
    ):
        try:
            target = pipe.parent / FLOW_DIR_NAME
            pipe.rename(target)
            pipe = target
        except OSError:
            pass

    if create and not read_only:
        db.parent.mkdir(parents=True, exist_ok=True)
        if looks_like_yaml_file(pipe):
            pipe.parent.mkdir(parents=True, exist_ok=True)
        elif pipe.exists() and pipe.is_file():
            pass
        else:
            # dossier flow (meme s'il n'existe pas encore)
            pipe.mkdir(parents=True, exist_ok=True)
            # F0082 / F0144: zone default protegee = flow/default/
            try:
                from renatus.gui.yaml_store import YamlStepStore

                YamlStepStore(pipe, ensure_default=True)
            except Exception:
                from renatus.gui.yaml_store import YamlStepStore as _YS

                (pipe / _YS.ROOT_TAB).mkdir(parents=True, exist_ok=True)
    else:
        # read-only ou --no-create : les chemins doivent deja exister
        if not pipe.exists():
            raise FileNotFoundError(f"flow_path introuvable: {pipe}")
        if not db.parent.exists():
            raise FileNotFoundError(
                f"parent de la base introuvable: {db.parent}"
            )

    return db.resolve(), pipe.resolve()
