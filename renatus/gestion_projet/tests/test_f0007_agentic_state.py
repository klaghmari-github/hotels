"""
Tests F0007 — CLI agentic/state.py (fine couche autour de agentic).

Le code metier est dans le package ; state.py expose show/check/refresh.
Git est exerce via un mini-depot sous tmp_path (sans remote obligatoire).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

STATE_PY = Path(__file__).resolve().parents[1] / "agentic" / "state.py"


@pytest.fixture
def state_mod():
    """Charge state.py par chemin fichier."""
    agentic_dir = str(STATE_PY.parent)
    if agentic_dir not in sys.path:
        sys.path.insert(0, agentic_dir)
    if "state" in sys.modules:
        del sys.modules["state"]
    import state as state_module  # type: ignore

    return state_module


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return (completed.stdout or "").strip()


@pytest.fixture
def mini_repo(tmp_path: Path) -> Path:
    """Depot git minimal avec branche main et un commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "init")
    return repo


@pytest.fixture
def gestion_dir(tmp_path: Path) -> Path:
    """Dossier gestion_projet temporaire (etat isole du depot)."""
    gestion = tmp_path / "gestion_projet"
    (gestion / "agentic").mkdir(parents=True)
    return gestion


# ---------------------------------------------------------------------------
# CLI show / check / refresh
# ---------------------------------------------------------------------------


def test_cli_show_without_etat_returns_1(state_mod, gestion_dir: Path):
    """show sans etat.json -> code 1."""
    code = state_mod.main(["--gestion", str(gestion_dir), "show"])
    assert code == 1


def test_cli_show_exits_zero(state_mod, gestion_dir: Path):
    """show avec etat valide -> code 0."""
    from agentic import AgenticPaths, EtatStore

    store = EtatStore(paths=AgenticPaths(gestion_dir=gestion_dir).ensure())
    store.load_or_create()
    code = state_mod.main(["--gestion", str(gestion_dir), "show"])
    assert code == 0


def test_cli_check_on_mini_repo(state_mod, mini_repo: Path, gestion_dir: Path):
    """check --no-fetch sur mini-repo : pas de crash, etat ecrit."""
    code = state_mod.main(
        [
            "--gestion",
            str(gestion_dir),
            "--repo",
            str(mini_repo),
            "check",
            "--no-fetch",
        ]
    )
    assert code in (0, 1)
    etat_path = gestion_dir / "agentic" / "etat.json"
    assert etat_path.is_file()
    data = json.loads(etat_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["git"]["local_branch"] == "main"


def test_cli_refresh_alias(state_mod, mini_repo: Path, gestion_dir: Path):
    """refresh se comporte comme check (persiste etat)."""
    code = state_mod.main(
        [
            "--gestion",
            str(gestion_dir),
            "--repo",
            str(mini_repo),
            "refresh",
            "--no-fetch",
        ]
    )
    assert code in (0, 1)
    data = json.loads((gestion_dir / "agentic" / "etat.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert "git" in data


def test_cli_unknown_command_exits_nonzero(state_mod):
    """Commande inconnue : argparse leve SystemExit 2."""
    with pytest.raises(SystemExit) as exc:
        state_mod.main(["nope"])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Package (source de verite unique)
# ---------------------------------------------------------------------------


def test_etat_store_roundtrip_via_package(gestion_dir: Path):
    """Round-trip EtatStore."""
    from agentic import AgenticPaths, EtatStore

    store = EtatStore(paths=AgenticPaths(gestion_dir=gestion_dir).ensure())
    etat = store.load_or_create()
    etat.features_en_cours = ["F0007"]
    etat.agents = [
        {"role": "developpeur", "feature": "F0007", "status": "en_cours", "notes": "t"}
    ]
    store.write(etat)
    loaded = store.read()
    assert loaded.features_en_cours == ["F0007"]
    assert loaded.agents[0]["role"] == "developpeur"


def test_git_checker_on_mini_repo(mini_repo: Path):
    """GitStatusChecker sur mini-depot reel sans remote."""
    from agentic import GitStatusChecker

    status = GitStatusChecker(repo_root=mini_repo).check(fetch=False)
    assert status.local_branch == "main"
    assert status.local_tip is not None
    assert status.remote_tip in (None, "")
    assert status.ahead == 0
    assert status.behind == 0


def test_git_checker_feature_branch(mini_repo: Path):
    """Detecte la branche feature courante."""
    from agentic import GitStatusChecker

    _git(mini_repo, "checkout", "-b", "F0007")
    (mini_repo / "work.txt").write_text("x\n", encoding="utf-8")
    _git(mini_repo, "add", "work.txt")
    _git(mini_repo, "commit", "-m", "F0007: work")
    status = GitStatusChecker(repo_root=mini_repo).check(fetch=False)
    assert status.local_branch == "F0007"
    assert status.local_tip is not None


def test_session_startup_persists_git(mini_repo: Path, gestion_dir: Path):
    """AgenticSession.startup ecrit le snapshot git dans etat.json."""
    from agentic import AgenticPaths, AgenticSession, EtatStore, GitStatusChecker

    paths = AgenticPaths(gestion_dir=gestion_dir).ensure()
    store = EtatStore(paths=paths)
    session = AgenticSession(
        paths=paths,
        store=store,
        git_checker=GitStatusChecker(repo_root=mini_repo),
    )
    report = session.startup(fetch=False)
    assert "git" in report
    etat = store.read()
    assert etat.git.local_branch == "main"
    assert etat.git.checked_at is not None


def test_state_py_is_cli_not_duplicate_store():
    """state.py reste une CLI fine : pas de seconde AgenticStateStore."""
    text = STATE_PY.read_text(encoding="utf-8")
    assert "agentic" in text
    assert "AgenticStateStore" not in text
    assert "def main" in text
