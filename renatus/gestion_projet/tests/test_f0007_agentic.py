"""
Tests unitaires F0007 — module agentic (etat persistant + git check).

Cible : lecture/ecriture etat.json, detection schema, git check mockable.
Pas de vrai fetch reseau ; pas de modification features.csv.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def gestion_dir(tmp_path: Path) -> Path:
    """Dossier gestion_projet temporaire avec sous-dossier agentic."""
    root = tmp_path / "gestion_projet"
    root.mkdir(parents=True, exist_ok=True)
    (root / "agentic").mkdir()
    return root


@pytest.fixture
def agentic_paths(gestion_dir: Path):
    from agentic import AgenticPaths

    return AgenticPaths(gestion_dir=gestion_dir).ensure()


# ---------------------------------------------------------------------------
# AgenticPaths
# ---------------------------------------------------------------------------


def test_agentic_paths_layout(gestion_dir: Path):
    """Les chemins agentic pointent sous gestion_projet/agentic/."""
    from agentic import AgenticPaths

    paths = AgenticPaths(gestion_dir=gestion_dir).ensure()
    assert paths.agentic_dir == gestion_dir / "agentic"
    assert paths.etat_path == gestion_dir / "agentic" / "etat.json"
    assert paths.session_path == gestion_dir / "agentic" / "session.md"
    assert paths.templates_dir == gestion_dir / "agentic" / "templates"
    assert paths.templates_dir.is_dir()
    assert paths.plan_path("F0007") == gestion_dir / "agentic" / "plan_F0007.md"
    assert paths.plan_path("A0001") == gestion_dir / "agentic" / "plan_A0001.md"


# ---------------------------------------------------------------------------
# Schema + EtatStore
# ---------------------------------------------------------------------------


def test_etat_schema_default_and_version():
    """Schema courant et etat par defaut sont coherents."""
    from agentic import EtatSchema

    schema = EtatSchema()
    assert schema.current_version == 1
    data = schema.default_etat()
    assert data["schema_version"] == 1
    assert "watchdog" in data
    assert "agents" in data
    assert "features_en_cours" in data
    assert "anomalies_en_cours" in data
    assert "locks" in data
    assert "git" in data
    assert "updated_at" in data
    assert schema.detect_version(data) == 1
    validated = schema.validate(data)
    assert validated["schema_version"] == 1


def test_etat_schema_rejects_invalid():
    """Schema invalide leve EtatSchemaError."""
    from agentic import EtatSchema, EtatSchemaError

    schema = EtatSchema()
    with pytest.raises(EtatSchemaError):
        schema.validate({})
    with pytest.raises(EtatSchemaError):
        schema.validate({"schema_version": 1})
    with pytest.raises(EtatSchemaError):
        schema.validate({"schema_version": 99, "watchdog": {}, "agents": [],
                         "features_en_cours": [], "anomalies_en_cours": [],
                         "locks": {}, "git": {}, "updated_at": "x"})


def test_etat_store_write_read_roundtrip(agentic_paths):
    """Ecriture puis lecture de etat.json conserve les champs cles."""
    from agentic import Etat, EtatStore

    store = EtatStore(paths=agentic_paths)
    etat = Etat.create_default()
    etat.watchdog.pid = 4242
    etat.watchdog.running = True
    etat.features_en_cours = ["F0007"]
    etat.agents = [
        {"role": "developpeur", "feature": "F0007", "status": "en_cours", "notes": "impl"},
    ]
    etat.locks.develop = "F0007"
    etat.git.local_branch = "F0007"
    etat.git.local_tip = "abc123"
    etat.git.ahead = 2
    etat.git.behind = 0

    store.write(etat)
    assert agentic_paths.etat_path.is_file()

    loaded = store.read()
    assert loaded.watchdog.pid == 4242
    assert loaded.watchdog.running is True
    assert loaded.features_en_cours == ["F0007"]
    assert loaded.agents[0]["role"] == "developpeur"
    assert loaded.locks.develop == "F0007"
    assert loaded.git.local_tip == "abc123"
    assert loaded.git.ahead == 2
    assert loaded.schema_version == 1


def test_etat_store_load_or_create(agentic_paths):
    """Sans fichier, load_or_create cree un etat valide sur disque."""
    from agentic import EtatStore

    store = EtatStore(paths=agentic_paths)
    assert not store.exists()
    etat = store.load_or_create()
    assert store.exists()
    assert etat.schema_version == 1
    assert agentic_paths.etat_path.is_file()
    raw = json.loads(agentic_paths.etat_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1


def test_etat_store_heartbeat(agentic_paths):
    """update_heartbeat met a jour pid, running et timestamp."""
    from agentic import EtatStore

    store = EtatStore(paths=agentic_paths)
    store.load_or_create()
    etat = store.update_heartbeat(pid=99)
    assert etat.watchdog.pid == 99
    assert etat.watchdog.running is True
    assert etat.watchdog.heartbeat_at is not None
    assert etat.updated_at is not None

    again = store.read()
    assert again.watchdog.pid == 99
    assert again.watchdog.heartbeat_at == etat.watchdog.heartbeat_at


def test_etat_store_rejects_corrupt_json(agentic_paths):
    """JSON corrompu leve EtatSchemaError (ou ValueError)."""
    from agentic import EtatSchemaError, EtatStore

    agentic_paths.etat_path.write_text("{not json", encoding="utf-8")
    store = EtatStore(paths=agentic_paths)
    with pytest.raises((EtatSchemaError, json.JSONDecodeError, ValueError)):
        store.read()


# ---------------------------------------------------------------------------
# GitStatusChecker (mockable)
# ---------------------------------------------------------------------------


class FakeGitRunner:
    """Runner git en memoire pour tests (pas de sous-processus)."""

    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]] | None = None):
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def run(self, args: list[str], cwd: Path) -> tuple[int, str, str]:
        self.calls.append(list(args))
        key = tuple(args)
        if key in self.responses:
            return self.responses[key]
        # prefix match (utile pour args variables)
        for resp_key, value in self.responses.items():
            if len(resp_key) <= len(key) and key[: len(resp_key)] == resp_key:
                return value
        return 1, "", f"unexpected git args: {args}"


def test_git_status_checker_ahead_behind(tmp_path: Path):
    """GitStatusChecker calcule ahead/behind via runner mocke."""
    from agentic import GitStatusChecker

    runner = FakeGitRunner(
        {
            ("rev-parse", "--abbrev-ref", "HEAD"): (0, "F0007\n", ""),
            ("rev-parse", "HEAD"): (0, "localsha\n", ""),
            ("rev-parse", "origin/F0007"): (0, "remotesha\n", ""),
            ("rev-list", "--left-right", "--count", "HEAD...origin/F0007"): (0, "3\t1\n", ""),
            ("status", "--porcelain"): (0, " M file.py\n", ""),
            ("fetch", "--quiet", "origin"): (0, "", ""),
            ("rev-parse", "--verify", "main"): (0, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n", ""),
            ("rev-parse", "--verify", "origin/main"): (
                0,
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
                "",
            ),
            ("rev-parse", "--verify", "develop"): (
                0,
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n",
                "",
            ),
            ("rev-parse", "--verify", "origin/develop"): (
                0,
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n",
                "",
            ),
        }
    )
    checker = GitStatusChecker(repo_root=tmp_path, runner=runner, remote="origin")
    status = checker.check(fetch=True)

    assert status.local_branch == "F0007"
    assert status.local_tip == "localsha"
    assert status.remote_tip == "remotesha"
    assert status.ahead == 3
    assert status.behind == 1
    assert status.dirty is True
    assert status.fetch_ok is True
    assert status.error is None
    assert status.main_local == "aaaaaaa"
    assert status.main_origin == "aaaaaaa"
    assert status.develop_local == "bbbbbbb"
    assert status.develop_origin == "bbbbbbb"
    # fetch appele en premier
    assert runner.calls[0][:1] == ["fetch"]


def test_git_status_checker_no_remote_ref(tmp_path: Path):
    """Branche sans remote : remote_tip vide, ahead/behind a 0."""
    from agentic import GitStatusChecker

    runner = FakeGitRunner(
        {
            ("rev-parse", "--abbrev-ref", "HEAD"): (0, "F0007\n", ""),
            ("rev-parse", "HEAD"): (0, "localsha\n", ""),
            ("rev-parse", "origin/F0007"): (128, "", "unknown revision"),
            ("status", "--porcelain"): (0, "", ""),
            ("fetch", "--quiet", "origin"): (0, "", ""),
        }
    )
    checker = GitStatusChecker(repo_root=tmp_path, runner=runner)
    status = checker.check(fetch=True)
    assert status.local_tip == "localsha"
    assert status.remote_tip is None or status.remote_tip == ""
    assert status.ahead == 0
    assert status.behind == 0
    assert status.dirty is False


def test_git_status_checker_fetch_failure(tmp_path: Path):
    """Echec fetch : fetch_ok False mais statut local toujours renseigne."""
    from agentic import GitStatusChecker

    runner = FakeGitRunner(
        {
            ("fetch", "--quiet", "origin"): (1, "", "network error"),
            ("rev-parse", "--abbrev-ref", "HEAD"): (0, "main\n", ""),
            ("rev-parse", "HEAD"): (0, "abc\n", ""),
            ("rev-parse", "origin/main"): (0, "def\n", ""),
            ("rev-list", "--left-right", "--count", "HEAD...origin/main"): (0, "0\t2\n", ""),
            ("status", "--porcelain"): (0, "", ""),
        }
    )
    checker = GitStatusChecker(repo_root=tmp_path, runner=runner)
    status = checker.check(fetch=True)
    assert status.fetch_ok is False
    assert status.behind == 2
    assert status.local_branch == "main"


# ---------------------------------------------------------------------------
# AgenticSession facade
# ---------------------------------------------------------------------------


def test_agentic_session_startup_updates_etat(agentic_paths, tmp_path: Path):
    """startup() fait le check git et persiste le resultat dans etat.json."""
    from agentic import AgenticSession, EtatStore, GitStatusChecker

    runner = FakeGitRunner(
        {
            ("fetch", "--quiet", "origin"): (0, "", ""),
            ("rev-parse", "--abbrev-ref", "HEAD"): (0, "F0007\n", ""),
            ("rev-parse", "HEAD"): (0, "tip1\n", ""),
            ("rev-parse", "origin/F0007"): (0, "tip1\n", ""),
            ("rev-list", "--left-right", "--count", "HEAD...origin/F0007"): (0, "0\t0\n", ""),
            ("status", "--porcelain"): (0, "", ""),
        }
    )
    store = EtatStore(paths=agentic_paths)
    checker = GitStatusChecker(repo_root=tmp_path, runner=runner)
    session = AgenticSession(paths=agentic_paths, store=store, git_checker=checker)

    report = session.startup(fetch=True)
    assert report["ok"] is True
    assert report["git"]["local_branch"] == "F0007"
    assert report["git"]["ahead"] == 0
    assert report["git"]["behind"] == 0

    etat = store.read()
    assert etat.git.local_branch == "F0007"
    assert etat.git.local_tip == "tip1"
    assert etat.git.checked_at is not None


def test_agentic_session_summary_roundtrip(agentic_paths, tmp_path: Path):
    """Lecture/ecriture session.md."""
    from agentic import AgenticSession, EtatStore, GitStatusChecker

    runner = FakeGitRunner(
        {
            ("rev-parse", "--abbrev-ref", "HEAD"): (0, "F0007\n", ""),
            ("rev-parse", "HEAD"): (0, "x\n", ""),
            ("rev-parse", "origin/F0007"): (128, "", "err"),
            ("status", "--porcelain"): (0, "", ""),
        }
    )
    session = AgenticSession(
        paths=agentic_paths,
        store=EtatStore(paths=agentic_paths),
        git_checker=GitStatusChecker(repo_root=tmp_path, runner=runner),
    )
    session.write_session_summary("# Session\n\nDerniere action: tests F0007\n")
    text = session.read_session_summary()
    assert "tests F0007" in text
    assert agentic_paths.session_path.is_file()


def test_agentic_session_set_agent_and_feature(agentic_paths, tmp_path: Path):
    """Helpers gestionnaire : agents et features en cours."""
    from agentic import AgenticSession, EtatStore, GitStatusChecker

    runner = FakeGitRunner(
        {
            ("rev-parse", "--abbrev-ref", "HEAD"): (0, "F0007\n", ""),
            ("rev-parse", "HEAD"): (0, "x\n", ""),
            ("rev-parse", "origin/F0007"): (128, "", "err"),
            ("status", "--porcelain"): (0, "", ""),
        }
    )
    session = AgenticSession(
        paths=agentic_paths,
        store=EtatStore(paths=agentic_paths),
        git_checker=GitStatusChecker(repo_root=tmp_path, runner=runner),
    )
    session.load_or_create()
    session.set_agent(role="developpeur", feature="F0007", status="en_cours", notes="code")
    session.set_feature_en_cours("F0007", active=True)
    session.set_lock("develop", "F0007")

    etat = session.store.read()
    assert any(a["role"] == "developpeur" for a in etat.agents)
    assert "F0007" in etat.features_en_cours
    assert etat.locks.develop == "F0007"

    session.set_feature_en_cours("F0007", active=False)
    session.set_lock("develop", None)
    etat = session.store.read()
    assert "F0007" not in etat.features_en_cours
    assert etat.locks.develop is None


def test_public_exports():
    """API publique agentic expose les classes principales."""
    from agentic import (
        AgenticPaths,
        AgenticSession,
        Etat,
        EtatSchema,
        EtatStore,
        GitStatusChecker,
    )

    for cls in (AgenticPaths, AgenticSession, Etat, EtatSchema, EtatStore, GitStatusChecker):
        assert cls is not None
