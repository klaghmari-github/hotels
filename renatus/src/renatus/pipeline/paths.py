"""
Chemins generiques du moteur renatus.

La racine est configurable : chemin explicite, ou detection d'un dossier
contenant pipeline/ ou src/renatus/, ou cwd en dernier recours.

Aucune arborescence metier de projet consommateur n'est imposee ni creee
par ce module (pas de sous-dossiers simulateur / ML metier dans le coeur).
"""

from __future__ import annotations

from pathlib import Path


def find_project_root(start: str | Path | None = None) -> Path:
    """
    Cherche un dossier projet plausible.

    Ordre de recherche :
    1. start s'il est fourni (et ses parents)
    2. cwd et ses parents
    3. emplacement du package et ses parents
    4. cwd si rien n'est trouve

    Un candidat est retenu s'il contient pipeline/ ou src/renatus/
    (data/ n'est plus un critere : il n'appartient pas au coeur renatus).
    """
    candidates: list[Path] = []

    if start is not None:
        start_path = Path(start).expanduser().resolve()
        candidates.append(start_path)
        candidates.extend(start_path.parents)

    cwd = Path.cwd().resolve()
    candidates.append(cwd)
    candidates.extend(cwd.parents)

    package_dir = Path(__file__).resolve().parent
    candidates.append(package_dir)
    candidates.extend(package_dir.parents)

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "pipeline").is_dir():
            return candidate
        if (candidate / "src" / "renatus").is_dir():
            return candidate

    return cwd


def release_root(root: str | Path | None = None) -> Path:
    """
    Racine projet.

    Si root est fourni, il est utilise tel quel (resolu).
    Sinon, recherche automatique via find_project_root().
    """
    if root is not None:
        return Path(root).expanduser().resolve()
    return find_project_root()


class Paths:
    """
    Chemins de travail optionnels relatifs a la racine.

    Conventions generiques (le consommateur decide d'utiliser data/ ou non) :
    - data/files/input, data/files/output
    - data/duckdb/main, data/duckdb/workers
    - pipeline/
    - models/

    ensure() ne cree plus d'arborescence vide metier : seulement, a la
    demande, le parent d'une base via ensure_db_parent().
    """

    def __init__(self, root: str | Path | None = None):
        self.root = release_root(root)

        self.data = self.root / "data"
        self.files = self.data / "files"
        self.input = self.files / "input"
        self.output = self.files / "output"

        self.duckdb = self.data / "duckdb"
        self.duckdb_main = self.duckdb / "main"
        self.duckdb_workers = self.duckdb / "workers"
        self.main_db = self.duckdb_main / "main.duckdb"

        self.pipeline = self.root / "pipeline"
        self.models = self.root / "models"
        self.doc = self.root / "doc"
        self.src = self.root / "src"

    def ensure(self) -> "Paths":
        """
        Compatibilite API : ne cree plus de dossiers metier.

        Les repertoires runtime sont crees a la demande
        (ex: ensure_db_parent, mkdir a l'ecriture d'un fichier).
        """
        return self

    def ensure_db_parent(self) -> Path:
        """Cree uniquement le dossier parent de main.duckdb si besoin."""
        self.main_db.parent.mkdir(parents=True, exist_ok=True)
        return self.main_db

    def ensure_dir(self, path: str | Path) -> Path:
        """Cree un repertoire donne (parents inclus) et le retourne."""
        directory = Path(path)
        if not directory.is_absolute():
            directory = self.root / directory
        directory.mkdir(parents=True, exist_ok=True)
        return directory.resolve()

    def input_file(self, name: str) -> Path:
        return self.input / name

    def output_file(self, name: str) -> Path:
        return self.output / name
