"""
Tests F0007 complementaires — layout gestion_projet et watchdog.

Verifie :
- existence / role de gestion_projet/agentic/
- features.csv et anomalies.csv restent a la racine gestion_projet
- watchdog ignore agentic/etat.json et ecrit un heartbeat
- presence .running toujours possible (create_running)
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# gestion_projet/tests/xxx.py -> parents[1] = gestion_projet, parents[2] = repo
GESTION_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = GESTION_DIR.parent
AGENTIC_DIR = GESTION_DIR / "agentic"
WATCHDOG_PATH = GESTION_DIR / "watchdog.py"
GESTION_SRC = GESTION_DIR / "src"


@pytest.fixture
def watchdog_mod(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """
    Charge watchdog.py en redirigeant ses chemins vers un tmp_path.

    Evite d ecrire dans le vrai .running / etat.json du depot.
    """
    gestion = tmp_path / "gestion_projet"
    agentic = gestion / "agentic"
    agentic.mkdir(parents=True)

    spec = importlib.util.spec_from_file_location(
        "watchdog_f0007_test",
        WATCHDOG_PATH,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Force rechargement isole (pas le module deja en cache)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    monkeypatch.setattr(mod, "GESTION_DIR", gestion)
    monkeypatch.setattr(mod, "RUNNING_FILE", gestion / ".running")
    monkeypatch.setattr(mod, "STATE_FILE", gestion / ".watchdog_state")
    monkeypatch.setattr(mod, "NOTIFICATIONS_LOG", gestion / "notifications.log")
    monkeypatch.setattr(mod, "AGENTIC_ETAT", agentic / "etat.json")
    return mod, gestion, agentic


# ---------------------------------------------------------------------------
# Layout projet (fichiers reels du depot)
# ---------------------------------------------------------------------------


def test_agentic_directory_exists_with_role_readme():
    """gestion_projet/agentic/ existe et documente son role."""
    assert AGENTIC_DIR.is_dir()
    readme = AGENTIC_DIR / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8").lower()
    assert "agentic" in text
    assert "etat" in text
    assert "features.csv" in text  # doc migration : reste a la racine


def test_features_and_anomalies_csv_at_gestion_root():
    """features.csv / anomalies.csv restent a la racine gestion_projet (pas dans agentic/)."""
    assert (GESTION_DIR / "features.csv").is_file()
    assert (GESTION_DIR / "anomalies.csv").is_file()
    assert not (AGENTIC_DIR / "features.csv").exists()
    assert not (AGENTIC_DIR / "anomalies.csv").exists()


def test_agentic_expected_artifacts_present():
    """Artefacts de reprise presents sous agentic/."""
    assert (AGENTIC_DIR / "etat.json").is_file()
    assert (AGENTIC_DIR / "session.md").is_file()
    assert (AGENTIC_DIR / "plan_F0007.md").is_file()
    assert (AGENTIC_DIR / "templates").is_dir()


def test_agent_notes_live_under_agentic():
    """
    Notes agents et etat_agents vivent sous agentic/ (pas a la racine gestion).

    Decision projet : place naturelle des notes_dev / notes_test / etat_agents.
    """
    assert (AGENTIC_DIR / "etat_agents.md").is_file()
    notes = list(AGENTIC_DIR.glob("notes_dev_*.md")) + list(
        AGENTIC_DIR.glob("notes_test_*.md")
    )
    assert notes, "au moins une note agent attendue sous agentic/"
    # plus de notes a la racine gestion_projet/
    assert not list(GESTION_DIR.glob("notes_dev_*.md"))
    assert not list(GESTION_DIR.glob("notes_test_*.md"))
    assert not (GESTION_DIR / "etat_agents.md").exists()


def test_watchdog_script_still_present():
    """watchdog.py reste a la racine gestion_projet (non migre)."""
    assert WATCHDOG_PATH.is_file()
    assert (GESTION_DIR / "regles_de_gestion.md").is_file()


def test_live_etat_json_schema_version_1():
    """etat.json live : schema_version 1 et cles minimales pour reprise."""
    data = json.loads((AGENTIC_DIR / "etat.json").read_text(encoding="utf-8"))
    assert data.get("schema_version") == 1
    assert "watchdog" in data
    assert "features_en_cours" in data
    assert "git" in data
    assert "locks" in data
    assert "agents" in data


# ---------------------------------------------------------------------------
# Watchdog (isole tmp_path)
# ---------------------------------------------------------------------------


def test_watchdog_ignores_agentic_etat_json(watchdog_mod):
    """agentic/etat.json est ignore (pas de notification heartbeat)."""
    mod, gestion, agentic = watchdog_mod
    etat = agentic / "etat.json"
    etat.write_text("{}", encoding="utf-8")
    other = agentic / "session.md"
    other.write_text("# session\n", encoding="utf-8")
    features = gestion / "features.csv"
    features.write_text("id\n", encoding="utf-8")

    assert mod._should_ignore(etat) is True
    assert mod._should_ignore(other) is False
    assert mod._should_ignore(features) is False


def test_watchdog_snapshot_excludes_etat_json(watchdog_mod):
    """snapshot_dir ne contient pas agentic/etat.json."""
    mod, gestion, agentic = watchdog_mod
    (agentic / "etat.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
    (agentic / "session.md").write_text("ok\n", encoding="utf-8")
    (gestion / "features.csv").write_text("id\n", encoding="utf-8")

    snap = mod.snapshot_dir(gestion)
    assert "agentic/etat.json" not in snap
    assert "agentic/session.md" in snap
    assert "features.csv" in snap


def test_watchdog_create_running_and_heartbeat(watchdog_mod):
    """
    create_running ecrit .running et un heartbeat agentic.

    Presence de .running = watchdog actif (regle projet).
    """
    mod, gestion, agentic = watchdog_mod
    # Preparer un etat minimal pour fallback ou EtatStore
    (agentic / "etat.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "2020-01-01T00:00:00",
                "watchdog": {"pid": None, "running": False, "heartbeat_at": None},
                "agents": [],
                "features_en_cours": [],
                "anomalies_en_cours": [],
                "locks": {"develop": None, "main": None},
                "git": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    mod.create_running()

    running = gestion / ".running"
    assert running.is_file()
    text = running.read_text(encoding="utf-8")
    assert "pid=" in text
    assert "started=" in text

    etat_path = agentic / "etat.json"
    assert etat_path.is_file()
    data = json.loads(etat_path.read_text(encoding="utf-8"))
    assert data["watchdog"]["running"] is True
    assert data["watchdog"]["pid"] is not None


def test_watchdog_write_heartbeat_fallback_without_package(
    watchdog_mod, monkeypatch: pytest.MonkeyPatch
):
    """Fallback JSON si agentic indisponible."""
    mod, gestion, agentic = watchdog_mod

    # Force le chemin fallback en faisant echouer l import agentic
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "agentic" or name.startswith("agentic"):
            raise ImportError("forced for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    etat = agentic / "etat.json"
    etat.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "agents": [],
                "features_en_cours": [],
                "anomalies_en_cours": [],
                "locks": {"develop": None, "main": None},
                "git": {},
                "watchdog": {},
            }
        ),
        encoding="utf-8",
    )
    mod.write_agentic_heartbeat(pid=12345)
    data = json.loads(etat.read_text(encoding="utf-8"))
    assert data["watchdog"]["pid"] == 12345
    assert data["watchdog"]["running"] is True
    assert data["watchdog"]["heartbeat_at"]


# ---------------------------------------------------------------------------
# Reprise : round-trip EtatStore (agentic) simule session
# ---------------------------------------------------------------------------


def test_resume_after_restart_roundtrip(tmp_path: Path):
    """
    Simule arret/redemarrage : etat ecrit, relecture, reprise feature en cours.
    """
    from agentic import AgenticPaths, AgenticSession, EtatStore, GitStatusChecker

    gestion = tmp_path / "gestion_projet"
    paths = AgenticPaths(gestion_dir=gestion).ensure()
    store = EtatStore(paths=paths)

    class FakeRunner:
        def run(self, args, cwd):
            mapping = {
                ("fetch", "--quiet", "origin"): (0, "", ""),
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "F0007\n", ""),
                ("rev-parse", "HEAD"): (0, "sha1\n", ""),
                ("rev-parse", "origin/F0007"): (0, "sha1\n", ""),
                ("rev-list", "--left-right", "--count", "HEAD...origin/F0007"): (
                    0,
                    "0\t0\n",
                    "",
                ),
                ("status", "--porcelain"): (0, "", ""),
            }
            return mapping.get(tuple(args), (1, "", "unexpected"))

    session = AgenticSession(
        paths=paths,
        store=store,
        git_checker=GitStatusChecker(repo_root=tmp_path, runner=FakeRunner()),
    )
    session.load_or_create()
    session.set_agent(role="developpeur", feature="F0007", status="en_cours")
    session.set_feature_en_cours("F0007", active=True)
    session.write_session_summary("# reprise F0007\n")
    report = session.startup(fetch=True)
    assert report["ok"] is True

    # "Redemarrage" : nouvelle session / store sur les memes chemins
    store2 = EtatStore(paths=paths)
    etat = store2.read()
    assert "F0007" in etat.features_en_cours
    assert any(a.get("role") == "developpeur" for a in etat.agents)
    assert etat.git.local_branch == "F0007"
    assert "reprise F0007" in session.read_session_summary()


def test_no_agentic_inside_renatus_package():
    """Separation stricte : aucun code agentic sous src/renatus/."""
    renatus_pkg = REPO_ROOT / "src" / "renatus"
    assert renatus_pkg.is_dir()
    assert not (renatus_pkg / "agentic").exists()
    # code agentic uniquement sous gestion_projet/src/agentic
    assert (GESTION_SRC / "agentic" / "__init__.py").is_file()
    assert (GESTION_SRC / "agentic" / "paths.py").is_file()


def test_gestion_src_package_importable():
    """Le package agentic s importe depuis gestion_projet/src sans renatus."""
    import agentic
    from agentic import AgenticPaths, EtatStore, AgenticSession

    assert AgenticPaths is not None
    path = agentic.__file__.replace("\\", "/")
    # hors package produit (le nom du depot peut contenir "renatus")
    assert "/src/renatus/" not in path
    assert "/gestion_projet/src/agentic/" in path
