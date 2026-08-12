"""
Projet renatus : sauvegarde / rechargement de la connexion workspace.

Un fichier projet (extension .renatus.yaml) memorise :
  - le chemin de la base DuckDB (peut etre hors projet : donnees privees)
  - le chemin du dossier flow (DOIT etre sous le dossier projet / git)
  - le nom du projet et l option read_only

Regles (F0043 / F0090) :
  - Le repertoire du .renatus.yaml est le root projet (= depot git).
  - Les YAML de flux sont versionnes : ils vivent sous root/flow/
    (ou un sous-dossier du root). Jamais hors du projet.
  - Ancien nom de dossier : pipelines/ (migre vers flow/ quand possible).
  - Les donnees (fichiers sources, souvent DuckDB) sont referencees par
    chemin ; elles ne sont pas copiees dans le workspace git (*.duckdb et
    input/ ignores).

Les chemins relatifs sont resolus par rapport au repertoire du fichier projet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from renatus.pipeline.workspace import FLOW_DIR_NAME

PROJECT_VERSION = 1
PROJECT_SUFFIXES = (".renatus.yaml", ".renatus.yml")


def is_project_file(path: str | Path) -> bool:
    name = Path(path).name.lower()
    return name.endswith(".renatus.yaml") or name.endswith(".renatus.yml")


def _as_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def find_project_file(path: str | Path) -> Path | None:
    """
    Resolve un chemin utilisateur vers un fichier .renatus.yaml existant.

    - fichier .renatus.yaml/.yml → lui-meme s il existe
    - dossier → unique *.renatus.yaml a la racine, sinon None
    """
    p = _as_path(path)
    if p.is_file() and is_project_file(p):
        return p.resolve()
    if p.is_dir():
        matches = sorted(
            [
                *p.glob("*.renatus.yaml"),
                *p.glob("*.renatus.yml"),
            ]
        )
        if len(matches) == 1:
            return matches[0].resolve()
        if len(matches) > 1:
            # prefere <dirname>.renatus.yaml si present
            preferred = p / f"{p.name}.renatus.yaml"
            if preferred.is_file():
                return preferred.resolve()
            return matches[0].resolve()
    # chemin fichier pas encore cree mais extension projet
    if is_project_file(p) and not p.exists():
        return None
    return None


def resolve_project_target(path: str | Path) -> tuple[Path, Path]:
    """
    Retourne (project_file, project_root) pour un chemin saisi.

    Accepte un dossier projet ou un fichier .renatus.yaml (existant ou non).
    """
    p = _as_path(path)
    if is_project_file(p):
        return p.expanduser().resolve() if p.exists() else p.expanduser(), (
            p.expanduser().resolve().parent if p.exists() else p.expanduser().parent
        )
    # dossier (existant ou a creer)
    root = p.expanduser()
    if root.exists() and root.is_file():
        # fichier non-projet: parent
        root = root.parent
    found = find_project_file(root) if root.is_dir() else None
    if found is not None:
        return found, found.parent
    safe = root.name.strip() or "renatus"
    # nettoie pour un nom de fichier raisonnable
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in safe).strip(
        "_"
    ) or "renatus"
    project_file = (root / f"{safe}.renatus.yaml").expanduser()
    return project_file, root.expanduser()


def is_under_directory(path: str | Path, root: str | Path) -> bool:
    """True si path est root ou un descendant de root."""
    try:
        p = Path(path).expanduser().resolve()
        r = Path(root).expanduser().resolve()
        p.relative_to(r)
        return True
    except (ValueError, OSError):
        return False


def ensure_pipelines_inside_project(
    project_root: str | Path,
    pipeline_path: str | Path | None = None,
    *,
    default_name: str = FLOW_DIR_NAME,
) -> Path:
    """
    Force le dossier flow sous le root projet (git).

    - None / vide → <root>/flow
    - relatif → resolu sous root
    - absolu hors root → ValueError

    Alias historique : ensure_flow_inside_project.
    """
    root = Path(project_root).expanduser().resolve()
    if pipeline_path is None or not str(pipeline_path).strip():
        from renatus.pipeline.workspace import default_flow_dir

        return default_flow_dir(root).resolve()
    raw = Path(str(pipeline_path).strip()).expanduser()
    if not raw.is_absolute():
        resolved = (root / raw).resolve()
    else:
        resolved = raw.resolve()
    if not is_under_directory(resolved, root):
        raise ValueError(
            "Le dossier flow doit etre a l interieur du projet "
            f"({root}). Les YAML de flux sont versionnes par git ; "
            f"chemin refuse : {resolved}"
        )
    return resolved


# F0090
ensure_flow_inside_project = ensure_pipelines_inside_project


@dataclass
class RenatusProject:
    """
    Description portable d un workspace renatus.

    Attributs:
      name: libelle court du projet
      db_path: chemin base DuckDB (absolu apres resolve, ou tel que stocke)
      pipeline_path: chemin du dossier flow (YAML de flux)
      read_only: ouverture lecture seule
      project_file: chemin du fichier .renatus.yaml si connu
    """

    name: str
    db_path: str
    pipeline_path: str  # chemin flow/ (nom attribut historique)
    read_only: bool = False
    version: int = PROJECT_VERSION
    project_file: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def flow_path(self) -> str:
        """Alias F0090 de pipeline_path (dossier flow)."""
        return self.pipeline_path

    @flow_path.setter
    def flow_path(self, value: str) -> None:
        self.pipeline_path = value

    # -- construction -------------------------------------------------------

    @classmethod
    def from_workspace(
        cls,
        db_path: str | Path,
        pipeline_path: str | Path,
        *,
        name: str | None = None,
        read_only: bool = False,
        project_file: str | Path | None = None,
    ) -> RenatusProject:
        db = _as_path(db_path).resolve()
        pipe = _as_path(pipeline_path).resolve()
        label = (name or "").strip()
        if not label:
            # nom par defaut: dossier parent commun ou stem db
            label = db.stem or pipe.name or "renatus"
        return cls(
            name=label,
            db_path=str(db),
            pipeline_path=str(pipe),
            read_only=bool(read_only),
            project_file=str(_as_path(project_file).resolve())
            if project_file
            else None,
        )

    # -- serialisation ------------------------------------------------------

    def to_dict(self, *, relative_to: Path | None = None) -> dict[str, Any]:
        """
        Dict YAML. Si relative_to est fourni, chemins stockes en relatif
        quand c est possible (portabilite).
        """
        db = Path(self.db_path)
        pipe = Path(self.pipeline_path)
        if relative_to is not None:
            base = relative_to.resolve()
            try:
                db_out = str(db.resolve().relative_to(base))
            except ValueError:
                db_out = str(db.resolve())
            try:
                pipe_out = str(pipe.resolve().relative_to(base))
            except ValueError:
                pipe_out = str(pipe.resolve())
        else:
            db_out = str(db)
            pipe_out = str(pipe)

        data: dict[str, Any] = {
            "version": int(self.version or PROJECT_VERSION),
            "name": self.name,
            "db_path": db_out,
            # F0090: flow_path principal ; pipeline_path = alias lecture legacy
            "flow_path": pipe_out,
            "pipeline_path": pipe_out,
            "read_only": bool(self.read_only),
        }
        for key, value in (self.extra or {}).items():
            if key not in data:
                data[key] = value
        return data

    def to_yaml(self, *, relative_to: Path | None = None) -> str:
        return yaml.dump(
            self.to_dict(relative_to=relative_to),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    def save(self, path: str | Path) -> Path:
        """Ecrit le fichier projet. Met a jour project_file."""
        target = _as_path(path)
        if target.suffix.lower() not in {".yaml", ".yml"} and not is_project_file(
            target
        ):
            # force extension reconnue
            target = target.with_name(target.name + ".renatus.yaml")
        elif target.suffix.lower() in {".yaml", ".yml"} and not is_project_file(
            target
        ):
            # accepte .yaml generique mais recommande .renatus.yaml
            pass

        target = target.expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        base = target.parent.resolve()
        text = self.to_yaml(relative_to=base)
        target.write_text(text, encoding="utf-8")
        resolved = target.resolve()
        self.project_file = str(resolved)
        # re-resolve paths absolute for runtime
        abs_db, abs_pipe = self.resolved_paths(base=base)
        self.db_path = str(abs_db)
        self.pipeline_path = str(abs_pipe)
        return resolved

    # -- chargement ---------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> RenatusProject:
        """Charge un fichier projet et resout les chemins."""
        file_path = _as_path(path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(f"Fichier projet introuvable: {file_path}")

        raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(
                f"Projet invalide (mapping attendu): {file_path}"
            )

        version = int(raw.get("version") or PROJECT_VERSION)
        if version > PROJECT_VERSION:
            raise ValueError(
                f"Version projet {version} non supportée "
                f"(max {PROJECT_VERSION})"
            )

        name = str(raw.get("name") or file_path.stem).strip()
        db_raw = raw.get("db_path")
        # F0090: flow_path prioritaire, pipeline_path = alias legacy
        pipe_raw = raw.get("flow_path") or raw.get("pipeline_path")
        if not db_raw or not pipe_raw:
            raise ValueError(
                "Projet incomplet: db_path et flow_path "
                "(ou pipeline_path) sont obligatoires"
            )

        base = file_path.parent
        db_path = cls._resolve_stored_path(str(db_raw), base)
        pipeline_path = cls._resolve_stored_path(str(pipe_raw), base)
        # F0090: pipelines/ → flow/ (rename si possible)
        from renatus.pipeline.workspace import (
            LEGACY_FLOW_DIR_NAMES,
            default_flow_dir,
        )

        try:
            if pipeline_path.name.lower() in LEGACY_FLOW_DIR_NAMES:
                pipeline_path = default_flow_dir(pipeline_path.parent)
        except OSError:
            pass
        read_only = bool(raw.get("read_only", False))

        known = {
            "version",
            "name",
            "db_path",
            "flow_path",
            "pipeline_path",
            "read_only",
        }
        extra = {k: v for k, v in raw.items() if k not in known}

        return cls(
            name=name,
            db_path=str(db_path),
            pipeline_path=str(pipeline_path),
            read_only=read_only,
            version=version,
            project_file=str(file_path),
            extra=extra,
        )

    @staticmethod
    def _resolve_stored_path(stored: str, base: Path) -> Path:
        p = Path(stored).expanduser()
        if p.is_absolute():
            return p.resolve()
        return (base / p).resolve()

    def resolved_paths(
        self, *, base: Path | None = None
    ) -> tuple[Path, Path]:
        """Retourne (db, pipeline) absolus."""
        if base is None and self.project_file:
            base = Path(self.project_file).parent
        if base is None:
            return Path(self.db_path).resolve(), Path(self.pipeline_path).resolve()
        return (
            self._resolve_stored_path(self.db_path, base)
            if not Path(self.db_path).is_absolute()
            else Path(self.db_path).resolve(),
            self._resolve_stored_path(self.pipeline_path, base)
            if not Path(self.pipeline_path).is_absolute()
            else Path(self.pipeline_path).resolve(),
        )

    def default_save_path(self) -> Path:
        """
        Proposition de chemin de sauvegarde (F0043 / F0069).

        Racine projet = parent de ``flow/`` (ou legacy pipelines/) si applicable,
        sinon parent du chemin flow. Fichier ``<name>.renatus.yaml``.
        """
        pipe = Path(self.pipeline_path).expanduser()
        try:
            pipe_r = pipe.resolve()
        except OSError:
            pipe_r = pipe
        if pipe_r.suffix.lower() in {".yaml", ".yml"}:
            root = pipe_r.parent
        elif pipe_r.name.lower() in {
            FLOW_DIR_NAME,
            "flow",
            "pipelines",
            "pipeline",
        }:
            root = pipe_r.parent
        elif pipe_r.is_dir() or not pipe.suffix:
            # dossier pipelines custom : parent si on reconnait le layout
            root = pipe_r
        else:
            root = pipe_r.parent
        safe = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in self.name
        ).strip("_") or "renatus"
        return (root / f"{safe}.renatus.yaml").resolve()
