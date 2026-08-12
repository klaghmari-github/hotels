"""
Verification git local vs remote au demarrage.

fetch + statut branche + ahead/behind. Le runner est injectable
pour les tests (pas de vrai reseau en unitaires).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class GitCommandRunner(Protocol):
    """Contrat d'execution d'une commande git."""

    def run(self, args: list[str], cwd: Path) -> tuple[int, str, str]:
        """Retourne (code_retour, stdout, stderr)."""
        ...


class SubprocessGitRunner:
    """Execution git via sous-processus."""

    def __init__(self, timeout_seconds: float = 60.0):
        self.timeout_seconds = timeout_seconds

    def run(self, args: list[str], cwd: Path) -> tuple[int, str, str]:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            return completed.returncode, completed.stdout or "", completed.stderr or ""
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, "", str(exc)


@dataclass
class GitStatus:
    """Resultat d'un check git local/remote."""

    local_branch: str | None = None
    local_tip: str | None = None
    remote_tip: str | None = None
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    remote: str = "origin"
    fetch_ok: bool = True
    error: str | None = None
    checked_at: str | None = None
    main_local: str | None = None
    main_origin: str | None = None
    develop_local: str | None = None
    develop_origin: str | None = None

    def to_dict(self) -> dict:
        return {
            "local_branch": self.local_branch,
            "local_tip": self.local_tip,
            "remote_tip": self.remote_tip,
            "ahead": self.ahead,
            "behind": self.behind,
            "dirty": self.dirty,
            "remote": self.remote,
            "fetch_ok": self.fetch_ok,
            "error": self.error,
            "checked_at": self.checked_at,
            "main_local": self.main_local,
            "main_origin": self.main_origin,
            "develop_local": self.develop_local,
            "develop_origin": self.develop_origin,
        }


class GitStatusChecker:
    """
    Compare la branche courante au remote homonyme.

    Sequence :
    1. optionnel : git fetch --quiet <remote>
    2. branche courante, tip HEAD
    3. tip remote (si ref existe)
    4. ahead/behind via rev-list --left-right --count
    5. working tree dirty via status --porcelain
    """

    def __init__(
        self,
        repo_root: str | Path,
        runner: GitCommandRunner | None = None,
        remote: str = "origin",
    ):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self._runner = runner
        self.remote = remote

    @property
    def runner(self) -> GitCommandRunner:
        if self._runner is None:
            self._runner = SubprocessGitRunner()
        return self._runner

    def _git(self, *args: str) -> tuple[int, str, str]:
        return self.runner.run(list(args), cwd=self.repo_root)

    def fetch(self) -> bool:
        """git fetch --quiet. True si code 0."""
        code, _out, _err = self._git("fetch", "--quiet", self.remote)
        return code == 0

    def check(self, fetch: bool = True) -> GitStatus:
        """Construit le statut git. Ne leve pas : erreurs dans status.error."""
        checked_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        status = GitStatus(remote=self.remote, checked_at=checked_at)

        if fetch:
            status.fetch_ok = self.fetch()
            if not status.fetch_ok:
                status.error = "fetch a echoue"
        else:
            status.fetch_ok = True

        code, out, err = self._git("rev-parse", "--abbrev-ref", "HEAD")
        if code != 0:
            status.error = (status.error + "; " if status.error else "") + (
                err.strip() or "branche inconnue"
            )
            return status
        status.local_branch = out.strip()

        code, out, err = self._git("rev-parse", "HEAD")
        if code != 0:
            status.error = (status.error + "; " if status.error else "") + (
                err.strip() or "HEAD inconnu"
            )
            return status
        status.local_tip = out.strip()

        remote_ref = f"{self.remote}/{status.local_branch}"
        code, out, _err = self._git("rev-parse", remote_ref)
        if code == 0:
            status.remote_tip = out.strip()
            code, out, err = self._git(
                "rev-list",
                "--left-right",
                "--count",
                f"HEAD...{remote_ref}",
            )
            if code == 0:
                parts = out.strip().split()
                if len(parts) >= 2:
                    try:
                        status.ahead = int(parts[0])
                        status.behind = int(parts[1])
                    except ValueError:
                        status.error = (status.error + "; " if status.error else "") + (
                            "parse ahead/behind impossible"
                        )
            else:
                status.error = (status.error + "; " if status.error else "") + (
                    err.strip() or "rev-list a echoue"
                )
        else:
            # Pas de branche remote homonyme : pas d'ahead/behind
            status.remote_tip = None
            status.ahead = 0
            status.behind = 0

        code, out, _err = self._git("status", "--porcelain")
        if code == 0:
            status.dirty = bool(out.strip())

        # Tips main / develop (local et origin) pour le tableau de bord agentic
        status.main_local = self._short_tip("main")
        status.main_origin = self._short_tip(f"{self.remote}/main")
        status.develop_local = self._short_tip("develop")
        status.develop_origin = self._short_tip(f"{self.remote}/develop")
        return status

    def _short_tip(self, ref: str) -> str | None:
        """SHA court (7) d'une ref, ou None si absente."""
        code, out, _err = self._git("rev-parse", "--verify", ref)
        if code != 0:
            return None
        sha = out.strip()
        return sha[:7] if sha else None
