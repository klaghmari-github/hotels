"""
Etat persistant machine-lisible (etat.json).

Schema versionne : toute evolution doit incrementer schema_version
et rester compatible via EtatSchema.validate().
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agentic.paths import AgenticPaths

SCHEMA_VERSION = 1


class EtatSchemaError(ValueError):
    """etat.json invalide ou schema non supporte."""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class WatchdogInfo:
    """Etat du process watchdog."""

    pid: int | None = None
    running: bool = False
    heartbeat_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WatchdogInfo:
        data = data or {}
        return cls(
            pid=data.get("pid"),
            running=bool(data.get("running", False)),
            heartbeat_at=data.get("heartbeat_at"),
        )


@dataclass
class LocksInfo:
    """Locks merge develop / main (holder = id feature ou None)."""

    develop: str | None = None
    main: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LocksInfo:
        data = data or {}
        return cls(
            develop=data.get("develop"),
            main=data.get("main"),
        )


@dataclass
class GitInfo:
    """Dernier snapshot git local vs remote."""

    local_branch: str | None = None
    local_tip: str | None = None
    remote_tip: str | None = None
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    fetch_ok: bool | None = None
    checked_at: str | None = None
    # SHAs courts main / develop (local vs origin) pour eviter merges a l'aveugle
    main_local: str | None = None
    main_origin: str | None = None
    develop_local: str | None = None
    develop_origin: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> GitInfo:
        data = data or {}
        return cls(
            local_branch=data.get("local_branch"),
            local_tip=data.get("local_tip"),
            remote_tip=data.get("remote_tip"),
            ahead=int(data.get("ahead") or 0),
            behind=int(data.get("behind") or 0),
            dirty=bool(data.get("dirty", False)),
            fetch_ok=data.get("fetch_ok"),
            checked_at=data.get("checked_at"),
            main_local=data.get("main_local"),
            main_origin=data.get("main_origin"),
            develop_local=data.get("develop_local"),
            develop_origin=data.get("develop_origin"),
        )


@dataclass
class Etat:
    """Snapshot complet de l'etat agentic en memoire."""

    schema_version: int = SCHEMA_VERSION
    updated_at: str | None = None
    watchdog: WatchdogInfo = field(default_factory=WatchdogInfo)
    agents: list[dict[str, Any]] = field(default_factory=list)
    features_en_cours: list[str] = field(default_factory=list)
    anomalies_en_cours: list[str] = field(default_factory=list)
    locks: LocksInfo = field(default_factory=LocksInfo)
    git: GitInfo = field(default_factory=GitInfo)

    @classmethod
    def create_default(cls) -> Etat:
        return cls(schema_version=SCHEMA_VERSION, updated_at=_now_iso())

    @classmethod
    def _normalize_agents(cls, raw: Any) -> list[dict[str, Any]]:
        """Accepte liste d'agents ou dict {role: infos}."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return [a for a in raw if isinstance(a, dict)]
        if isinstance(raw, dict):
            result: list[dict[str, Any]] = []
            for role, info in raw.items():
                if isinstance(info, dict):
                    entry = dict(info)
                    entry.setdefault("role", role)
                    result.append(entry)
                else:
                    result.append({"role": role, "status": str(info)})
            return result
        return []

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Etat:
        git_raw = data.get("git") if isinstance(data.get("git"), dict) else {}
        # Compat schema etendu (CLI state.py) : current_branch / last_check_at
        if "local_branch" not in git_raw and git_raw.get("current_branch"):
            git_raw = dict(git_raw)
            git_raw["local_branch"] = git_raw.get("current_branch")
        if "checked_at" not in git_raw and git_raw.get("last_check_at"):
            git_raw = dict(git_raw)
            git_raw["checked_at"] = git_raw.get("last_check_at")
        # tip depuis section feature ou main si absents
        feature = git_raw.get("feature") if isinstance(git_raw.get("feature"), dict) else {}
        main = git_raw.get("main") if isinstance(git_raw.get("main"), dict) else {}
        if not git_raw.get("local_tip"):
            git_raw = dict(git_raw)
            git_raw["local_tip"] = feature.get("local") or main.get("local")
        if not git_raw.get("remote_tip"):
            git_raw = dict(git_raw)
            git_raw["remote_tip"] = feature.get("origin") or main.get("origin")

        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            updated_at=data.get("updated_at"),
            watchdog=WatchdogInfo.from_dict(data.get("watchdog")),
            agents=cls._normalize_agents(data.get("agents")),
            features_en_cours=list(data.get("features_en_cours") or []),
            anomalies_en_cours=list(data.get("anomalies_en_cours") or []),
            locks=LocksInfo.from_dict(data.get("locks")),
            git=GitInfo.from_dict(git_raw),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "watchdog": asdict(self.watchdog),
            "agents": list(self.agents),
            "features_en_cours": list(self.features_en_cours),
            "anomalies_en_cours": list(self.anomalies_en_cours),
            "locks": asdict(self.locks),
            "git": asdict(self.git),
        }


class EtatSchema:
    """Detection et validation du schema etat.json."""

    SUPPORTED_VERSIONS = frozenset({1})
    REQUIRED_TOP_KEYS = frozenset(
        {
            "schema_version",
            "updated_at",
            "watchdog",
            "agents",
            "features_en_cours",
            "anomalies_en_cours",
            "locks",
            "git",
        }
    )

    @property
    def current_version(self) -> int:
        return SCHEMA_VERSION

    def default_etat(self) -> dict[str, Any]:
        return Etat.create_default().to_dict()

    def detect_version(self, data: dict[str, Any]) -> int:
        if not isinstance(data, dict):
            raise EtatSchemaError("etat.json doit etre un objet JSON")
        try:
            return int(data.get("schema_version", 0))
        except (TypeError, ValueError) as exc:
            raise EtatSchemaError("schema_version invalide") from exc

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Valide et normalise un dict etat.

        Accepte agents en liste ou en dict (role -> infos).
        Conserve les cles supplementaires (ex. session) hors normalisation.
        Leve EtatSchemaError si structure ou version incorrecte.
        """
        if not isinstance(data, dict):
            raise EtatSchemaError("etat.json doit etre un objet JSON")

        version = self.detect_version(data)
        if version not in self.SUPPORTED_VERSIONS:
            raise EtatSchemaError(
                f"schema_version {version} non supporte "
                f"(supportes: {sorted(self.SUPPORTED_VERSIONS)})"
            )

        missing = self.REQUIRED_TOP_KEYS - set(data.keys())
        if missing:
            raise EtatSchemaError(f"cles manquantes: {sorted(missing)}")

        if not isinstance(data.get("watchdog"), dict):
            raise EtatSchemaError("watchdog doit etre un objet")
        agents = data.get("agents")
        if not isinstance(agents, (list, dict)):
            raise EtatSchemaError("agents doit etre une liste ou un objet")
        if not isinstance(data.get("features_en_cours"), list):
            raise EtatSchemaError("features_en_cours doit etre une liste")
        if not isinstance(data.get("anomalies_en_cours"), list):
            raise EtatSchemaError("anomalies_en_cours doit etre une liste")
        if not isinstance(data.get("locks"), dict):
            raise EtatSchemaError("locks doit etre un objet")
        if not isinstance(data.get("git"), dict):
            raise EtatSchemaError("git doit etre un objet")

        # Normalisation via Etat pour types stables (agents -> liste)
        normalized = Etat.from_dict(data).to_dict()
        # Conserver cles hors schema strict (ex. session) si presentes
        for key, value in data.items():
            if key not in normalized:
                normalized[key] = value
        return normalized

class EtatStore:
    """Lecture et ecriture atomique de etat.json."""

    def __init__(
        self,
        paths: AgenticPaths | None = None,
        schema: EtatSchema | None = None,
    ):
        self._paths = paths
        self._schema = schema

    @property
    def paths(self) -> AgenticPaths:
        if self._paths is None:
            self._paths = AgenticPaths().ensure()
        return self._paths

    @property
    def schema(self) -> EtatSchema:
        if self._schema is None:
            self._schema = EtatSchema()
        return self._schema

    def exists(self) -> bool:
        return self.paths.etat_path.is_file()

    def read(self) -> Etat:
        """Lit et valide etat.json. Leve si absent ou invalide."""
        path = self.paths.etat_path
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise EtatSchemaError(f"impossible de lire {path}: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EtatSchemaError(f"JSON invalide dans {path}: {exc}") from exc
        validated = self.schema.validate(data)
        return Etat.from_dict(validated)

    def write(self, etat: Etat) -> None:
        """Ecrit etat.json de facon atomique (temp + replace)."""
        self.paths.ensure()
        etat.updated_at = _now_iso()
        etat.schema_version = self.schema.current_version
        payload = json.dumps(etat.to_dict(), indent=2, ensure_ascii=False) + "\n"
        path = self.paths.etat_path
        directory = path.parent
        fd, tmp_name = tempfile.mkstemp(prefix=".etat_", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            Path(tmp_name).replace(path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def load_or_create(self) -> Etat:
        """Charge l'etat existant ou cree un etat par defaut sur disque."""
        if self.exists():
            return self.read()
        etat = Etat.create_default()
        self.write(etat)
        return etat

    def update_heartbeat(self, pid: int | None = None) -> Etat:
        """
        Met a jour le heartbeat watchdog dans etat.json.

        Cree le fichier s'il n'existe pas encore.
        """
        etat = self.load_or_create()
        if pid is not None:
            etat.watchdog.pid = pid
        etat.watchdog.running = True
        etat.watchdog.heartbeat_at = _now_iso()
        self.write(etat)
        return etat
