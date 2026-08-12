"""
Depot git local d un projet renatus (F0032).

- A la creation du projet: git init, commit initial sur main,
  branche de travail b_YYYY_MM_DD_hh_mm_ss.
- Toute modification de fichiers projet est auto-committee sur la branche
  de travail (sans demander a l utilisateur).
- A l ouverture: checkout main; si une branche est en avance, signaler.
- Au Save projet (action utilisateur): merge de la branche de travail dans main.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


GITIGNORE = """\
# renatus project (F0032 / F0043)
# Pipelines YAML = versionnes. Donnees privees = ignorees.
*.duckdb
*.duckdb.wal
# sources uploadees localement (preferer chemins absolus hors projet)
input/
# caches / OS
*.pyc
__pycache__/
.DS_Store
*.tmp
"""

BRANCH_RE = re.compile(
    r"^b_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}(_\d+)?$"
)


def work_branch_name(when: datetime | None = None) -> str:
    d = when or datetime.now()
    # microsecond pour unicite si deux branches dans la meme seconde
    return (
        f"b_{d.year:04d}_{d.month:02d}_{d.day:02d}_"
        f"{d.hour:02d}_{d.minute:02d}_{d.second:02d}_{d.microsecond:06d}"
    )


@dataclass
class PendingBranch:
    name: str
    ahead: int
    last_commit: str
    last_date: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ahead": self.ahead,
            "last_commit": self.last_commit,
            "last_date": self.last_date,
        }


class ProjectGit:
    """Operations git minimales autour d un repertoire projet."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    @property
    def git_dir(self) -> Path:
        return self.root / ".git"

    def is_repo(self) -> bool:
        return self.git_dir.is_dir()

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("GIT_AUTHOR_NAME", "renatus")
        env.setdefault("GIT_AUTHOR_EMAIL", "renatus@local")
        env.setdefault("GIT_COMMITTER_NAME", "renatus")
        env.setdefault("GIT_COMMITTER_EMAIL", "renatus@local")
        # evite prompts
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env

    def _run(
        self,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            env=self._env(),
            text=True,
            capture_output=True,
            check=check,
        )

    def _write_gitignore(self) -> None:
        gi = self.root / ".gitignore"
        if not gi.is_file():
            gi.write_text(GITIGNORE, encoding="utf-8")

    # -- cycle de vie -------------------------------------------------------

    def init_repository(self) -> str:
        """
        Initialise le repo, commit initial sur main, cree branche de travail.

        Retourne le nom de la branche de travail.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.is_repo():
            self._run("init", "-b", "main")
        self._write_gitignore()
        # commit initial (meme si rien a part gitignore + projet)
        self._run("add", "-A", check=False)
        status = self._run("status", "--porcelain", check=False)
        if status.stdout.strip():
            self._run("commit", "-m", "chore: initial project")
        elif not self._has_commits():
            # commit vide impossible: touch keep
            keep = self.root / ".renatus_keep"
            keep.write_text("", encoding="utf-8")
            self._run("add", "-A", check=False)
            self._run("commit", "-m", "chore: initial project")
        # s assurer d etre sur main
        self.checkout("main")
        branch = work_branch_name()
        self._run("checkout", "-b", branch)
        return branch

    def _has_commits(self) -> bool:
        r = self._run("rev-parse", "HEAD", check=False)
        return r.returncode == 0

    def current_branch(self) -> str:
        r = self._run("rev-parse", "--abbrev-ref", "HEAD", check=False)
        if r.returncode != 0:
            return ""
        return (r.stdout or "").strip()

    def checkout(self, branch: str) -> None:
        self._run("checkout", branch)

    def ensure_work_branch(self) -> str:
        """
        Si on est sur main, cree une nouvelle branche de travail.
        Sinon reste sur la branche courante.
        """
        if not self.is_repo():
            return self.init_repository()
        cur = self.current_branch()
        if cur in ("main", "master", ""):
            branch = work_branch_name()
            # base main si possible
            if self._branch_exists("main"):
                self._run("checkout", "main", check=False)
            self._run("checkout", "-b", branch)
            return branch
        return cur

    def _branch_exists(self, name: str) -> bool:
        r = self._run(
            "show-ref",
            "--verify",
            f"refs/heads/{name}",
            check=False,
        )
        return r.returncode == 0

    def commit_all(
        self,
        message: str,
        *,
        components: list[str] | None = None,
        paths: list[str] | None = None,
    ) -> bool:
        """
        Stage + commit si changements. True si un commit a ete cree.

        F0115: message multi-ligne avec trailers machine-lisibles:
          renatus-component: <id>
          renatus-path: <relpath>
        pour filtrer Track par composant (et zones recursives).
        """
        if not self.is_repo():
            return False
        self._write_gitignore()
        self._run("add", "-A", check=False)
        status = self._run("status", "--porcelain", check=False)
        if not (status.stdout or "").strip():
            return False
        subject = (message or "chore: update").strip().splitlines()[0][:200]
        body_lines: list[str] = [subject, ""]
        seen_c: set[str] = set()
        for cid in components or []:
            c = str(cid or "").strip()
            if not c or c in seen_c:
                continue
            seen_c.add(c)
            body_lines.append(f"renatus-component: {c}")
        seen_p: set[str] = set()
        for p in paths or []:
            rp = str(p or "").strip().replace("\\", "/")
            if not rp or rp in seen_p:
                continue
            seen_p.add(rp)
            body_lines.append(f"renatus-path: {rp}")
        # git commit -m subject -m body (trailers)
        msg = "\n".join(body_lines).strip() + "\n"
        self._run("commit", "-m", msg, check=False)
        return True

    def reinit_history(
        self,
        message: str = "chore: renatus history reset (component tracking)",
    ) -> dict[str, Any]:
        """
        F0115: efface l historique git et repart de zero (1 commit initial).

        Conserve les fichiers du working tree. Utilise pour basculer sur le
        format de commits filtrable par composant.
        """
        import shutil

        git_dir = self.git_dir
        if git_dir.is_dir():
            shutil.rmtree(git_dir)
        # init_repository: main + commit initial + branche b_*
        branch = self.init_repository()
        # amender le message du commit initial (sur main si on y est, sinon HEAD)
        msg = (message or "chore: renatus history reset").strip()[:200]
        # init laisse sur b_*; le commit initial est sur main — amend HEAD
        # (1er commit de b_* est le meme objet que main au checkout -b)
        self._run("commit", "--amend", "-m", msg, "--allow-empty", check=False)
        return {
            "ok": True,
            "branch": branch or self.current_branch(),
            "message": "Historique git reinitialise",
        }

    def merge_into_main(self, work_branch: str | None = None) -> dict[str, Any]:
        """
        Merge la branche de travail dans main.
        Retourne un resume {ok, work_branch, message}.
        """
        if not self.is_repo():
            return {"ok": False, "message": "Pas de depot git"}
        work = work_branch or self.current_branch()
        if work in ("main", "master", ""):
            # rien a merger; commit sur main si dirty
            self.commit_all("chore: save on main")
            return {
                "ok": True,
                "work_branch": work,
                "message": "Deja sur main",
            }
        # commit pending sur work
        self.commit_all(f"chore: save before merge ({work})")
        self.checkout("main")
        merged = self._run("merge", "--no-ff", work, "-m", f"merge {work}", check=False)
        if merged.returncode != 0:
            # abort si conflit
            self._run("merge", "--abort", check=False)
            # revenir sur work
            self.checkout(work)
            return {
                "ok": False,
                "work_branch": work,
                "message": (
                    f"Merge {work} → main echoue: "
                    f"{(merged.stderr or merged.stdout or '').strip()}"
                ),
            }
        # nouvelle branche de travail pour la suite
        new_work = work_branch_name()
        created = self._run("checkout", "-b", new_work, check=False)
        if created.returncode != 0:
            # collision rare: reessayer avec un nouvel instant
            new_work = work_branch_name()
            self._run("checkout", "-b", new_work)
        return {
            "ok": True,
            "work_branch": new_work,
            "merged_from": work,
            "message": f"Branche {work} fusionnee dans main; travail sur {new_work}",
        }

    def list_local_branches(self) -> list[str]:
        r = self._run("branch", "--format=%(refname:short)", check=False)
        if r.returncode != 0:
            return []
        return [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]

    def find_latest_branch_ahead_of_main(self) -> PendingBranch | None:
        """
        Trouve la branche b_* la plus recente ayant des commits absents de main.
        """
        if not self.is_repo() or not self._branch_exists("main"):
            return None
        candidates: list[PendingBranch] = []
        for br in self.list_local_branches():
            if br in ("main", "master"):
                continue
            # commits dans br pas dans main
            ahead_r = self._run(
                "rev-list",
                "--count",
                f"main..{br}",
                check=False,
            )
            try:
                ahead = int((ahead_r.stdout or "0").strip() or "0")
            except ValueError:
                ahead = 0
            if ahead <= 0:
                continue
            meta = self._run(
                "log",
                "-1",
                "--format=%h|%cI|%s",
                br,
                check=False,
            )
            parts = (meta.stdout or "").strip().split("|", 2)
            last_commit = parts[0] if parts else ""
            last_date = parts[1] if len(parts) > 1 else ""
            subject = parts[2] if len(parts) > 2 else ""
            candidates.append(
                PendingBranch(
                    name=br,
                    ahead=ahead,
                    last_commit=last_commit,
                    last_date=last_date or subject,
                )
            )
        if not candidates:
            return None
        # plus recente par date ISO, sinon par nom
        candidates.sort(key=lambda p: (p.last_date, p.name), reverse=True)
        return candidates[0]

    def status_summary(self) -> dict[str, Any]:
        if not self.is_repo():
            return {
                "is_repo": False,
                "branch": None,
                "pending": None,
            }
        pending = self.find_latest_branch_ahead_of_main()
        return {
            "is_repo": True,
            "branch": self.current_branch(),
            "pending": pending.to_dict() if pending else None,
        }

    # -- historique global / changelog (F0033 + F0035) ----------------------

    def relpath(self, absolute: str | Path) -> str:
        """Chemin relatif au root git (posix)."""
        p = Path(absolute).expanduser().resolve()
        return p.relative_to(self.root).as_posix()

    def global_log(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """
        Timeline globale des commits (plus recent en premier).

        Chaque entree inclut la liste des fichiers touches par le commit.
        """
        if not self.is_repo():
            return []
        lim = max(1, min(int(limit), 200))
        # Marker de debut de commit + name-only (fichiers sous le marqueur)
        # --all: historique global (branches travail + main), F0065
        r = self._run(
            "log",
            f"-n{lim}",
            "--all",
            "--name-only",
            "--pretty=format:>>> %H|%h|%cI|%s",
            check=False,
        )
        if r.returncode != 0:
            return []
        entries: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in (r.stdout or "").splitlines():
            if line.startswith(">>> "):
                if current is not None:
                    current["file_count"] = len(current["files"])
                    entries.append(current)
                meta = line[4:].strip()
                parts = meta.split("|", 3)
                if len(parts) < 4:
                    current = None
                    continue
                full, short, date, subject = (
                    parts[0],
                    parts[1],
                    parts[2],
                    parts[3],
                )
                current = {
                    "commit": full,
                    "short": short,
                    "date": date,
                    "subject": subject,
                    "files": [],
                    "file_count": 0,
                }
            elif current is not None:
                p = line.strip()
                if p:
                    current["files"].append(p)
        if current is not None:
            current["file_count"] = len(current["files"])
            entries.append(current)
        return entries

    def file_log(
        self,
        rel_path: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Timeline des commits touchant un fichier (plus recent en premier)."""
        return self.paths_log([rel_path], limit=limit)

    def paths_log(
        self,
        rel_paths: list[str],
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        F0115: timeline des commits touchant au moins un des chemins.

        Utilise pour Track filtre par composant (union des fichiers YAML
        du step + membres recursifs si zone).
        """
        if not self.is_repo():
            return []
        paths = [
            str(p).strip().replace("\\", "/")
            for p in (rel_paths or [])
            if str(p or "").strip()
        ]
        if not paths:
            return []
        lim = max(1, min(int(limit), 200))
        # --name-only pour renseigner files (filtre UI)
        r = self._run(
            "log",
            f"-n{lim}",
            "--all",
            "--name-only",
            "--pretty=format:>>> %H|%h|%cI|%s",
            "--",
            *paths,
            check=False,
        )
        if r.returncode != 0:
            return []
        entries: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        path_set = set(paths)
        for line in (r.stdout or "").splitlines():
            if line.startswith(">>> "):
                if current is not None:
                    # ne garder que les fichiers du scope demande
                    current["files"] = [
                        f
                        for f in current["files"]
                        if f in path_set
                        or any(
                            f == p or f.startswith(p.rstrip("/") + "/")
                            for p in path_set
                        )
                    ]
                    current["file_count"] = len(current["files"])
                    entries.append(current)
                meta = line[4:].strip()
                parts = meta.split("|", 3)
                if len(parts) < 4:
                    current = None
                    continue
                full, short, date, subject = (
                    parts[0],
                    parts[1],
                    parts[2],
                    parts[3],
                )
                current = {
                    "commit": full,
                    "short": short,
                    "date": date,
                    "subject": subject,
                    "files": [],
                    "file_count": 0,
                }
            elif current is not None:
                p = line.strip()
                if p:
                    current["files"].append(p)
        if current is not None:
            current["files"] = [
                f
                for f in current["files"]
                if f in path_set
                or any(
                    f == p or f.startswith(p.rstrip("/") + "/")
                    for p in path_set
                )
            ]
            current["file_count"] = len(current["files"])
            entries.append(current)
        return entries

    def commit_files(self, commit: str) -> list[str]:
        """Fichiers modifies dans un commit."""
        if not self.is_repo() or not commit:
            return []
        r = self._run(
            "show",
            "--name-only",
            "--pretty=format:",
            commit,
            check=False,
        )
        if r.returncode != 0:
            return []
        return [
            ln.strip()
            for ln in (r.stdout or "").splitlines()
            if ln.strip()
        ]

    def files_at_commit(self, commit: str) -> list[str]:
        """Tous les chemins presents dans l arbre du commit."""
        if not self.is_repo() or not commit:
            return []
        r = self._run(
            "ls-tree",
            "-r",
            "--name-only",
            commit,
            check=False,
        )
        if r.returncode != 0:
            return []
        return [
            ln.strip()
            for ln in (r.stdout or "").splitlines()
            if ln.strip()
        ]

    def file_content_at(self, commit: str, rel_path: str) -> str | None:
        """Contenu du fichier a un commit (None si absent)."""
        if not self.is_repo() or not commit:
            return None
        r = self._run(
            "show",
            f"{commit}:{rel_path}",
            check=False,
        )
        if r.returncode != 0:
            return None
        return r.stdout if r.stdout is not None else ""

    def file_diff_at(
        self,
        commit: str,
        rel_path: str,
    ) -> dict[str, Any]:
        """Diff unifie du fichier pour ce commit (vs parent)."""
        if not self.is_repo():
            return {
                "ok": False,
                "commit": commit,
                "path": rel_path,
                "diff": "",
                "message": "Pas de depot git",
            }
        r = self._run(
            "show",
            "--format=",
            "--unified=3",
            commit,
            "--",
            rel_path,
            check=False,
        )
        diff = r.stdout or ""
        if r.returncode != 0 and not diff:
            content = self.file_content_at(commit, rel_path)
            if content is not None:
                lines = content.splitlines()
                body = "".join(f"+{ln}\n" for ln in lines)
                diff = (
                    f"--- /dev/null\n+++ b/{rel_path}\n"
                    f"@@ -0,0 +1,{len(lines)} @@\n{body}"
                )
        return {
            "ok": True,
            "commit": commit,
            "path": rel_path,
            "diff": diff,
            "message": "OK",
        }

    def commit_diff(
        self,
        commit: str,
        rel_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Diff unifie d un commit (tous fichiers ou un chemin).
        """
        if not self.is_repo():
            return {
                "ok": False,
                "commit": commit,
                "path": rel_path,
                "diff": "",
                "files": [],
                "message": "Pas de depot git",
            }
        files = self.commit_files(commit)
        if rel_path:
            data = self.file_diff_at(commit, rel_path)
            return {
                "ok": True,
                "commit": commit,
                "path": rel_path,
                "diff": data.get("diff") or "",
                "files": files,
                "message": "OK",
            }
        r = self._run(
            "show",
            "--format=",
            "--unified=3",
            commit,
            check=False,
        )
        return {
            "ok": True,
            "commit": commit,
            "path": None,
            "diff": r.stdout or "",
            "files": files,
            "message": "OK",
        }

    def restore_file_from_commit(
        self,
        commit: str,
        rel_path: str,
        *,
        message: str | None = None,
    ) -> dict[str, Any]:
        """
        Forward-only: copie le contenu du fichier au commit dans le WT
        et cree un NOUVEAU commit (pas de reset / revert).
        """
        if not self.is_repo():
            return {"ok": False, "message": "Pas de depot git"}
        content = self.file_content_at(commit, rel_path)
        if content is None:
            return {
                "ok": False,
                "message": f"Fichier absent au commit {commit[:8]}",
            }
        self.ensure_work_branch()
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        short = commit[:8]
        msg = message or f"restore {rel_path} from {short} (ff apply file)"
        committed = self.commit_all(msg)
        return {
            "ok": True,
            "mode": "file",
            "path": rel_path,
            "paths": [rel_path],
            "from_commit": commit,
            "branch": self.current_branch(),
            "committed": committed,
            "message": (
                f"Fichier {rel_path} restaure depuis {short} (nouveau commit)"
                if committed
                else f"Fichier {rel_path} deja identique a {short}"
            ),
        }

    def restore_snapshot_from_commit(
        self,
        commit: str,
        *,
        message: str | None = None,
    ) -> dict[str, Any]:
        """
        Forward-only: restaure TOUS les fichiers a leur etat au commit
        (snapshot), puis cree un NOUVEAU commit.

        - checkout des chemins presents au commit
        - suppression des fichiers tracks apparus apres ce commit
        - jamais de reset/revert de branche
        """
        if not self.is_repo():
            return {"ok": False, "message": "Pas de depot git"}
        if not commit:
            return {"ok": False, "message": "Commit requis"}
        # valide le commit
        chk = self._run("rev-parse", "--verify", f"{commit}^{{commit}}", check=False)
        if chk.returncode != 0:
            return {"ok": False, "message": f"Commit invalide: {commit[:12]}"}

        self.ensure_work_branch()
        paths_at = self.files_at_commit(commit)
        cur_r = self._run("ls-files", check=False)
        current = {
            ln.strip()
            for ln in (cur_r.stdout or "").splitlines()
            if ln.strip()
        }
        at_set = set(paths_at)

        # restaure l arbre tracke a l etat du commit
        co = self._run("checkout", commit, "--", ".", check=False)
        if co.returncode != 0:
            err = (co.stderr or co.stdout or "").strip()
            return {"ok": False, "message": f"Checkout snapshot echoue: {err}"}

        # retire les fichiers ajoutes apres ce commit
        removed: list[str] = []
        for path in sorted(current - at_set):
            p = self.root / path
            if p.is_file():
                try:
                    p.unlink()
                    removed.append(path)
                except OSError:
                    pass

        short = commit[:8]
        msg = message or f"restore snapshot from {short} (ff apply all)"
        committed = self.commit_all(msg)
        return {
            "ok": True,
            "mode": "all",
            "path": None,
            "paths": paths_at,
            "removed": removed,
            "from_commit": commit,
            "branch": self.current_branch(),
            "committed": committed,
            "message": (
                f"Snapshot {short} reapplique "
                f"({len(paths_at)} fichier(s), nouveau commit)"
                if committed
                else f"Snapshot {short} deja identique"
            ),
        }
