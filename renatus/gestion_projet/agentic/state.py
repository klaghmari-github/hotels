#!/usr/bin/env python3
"""
CLI fine autour du package agentic (gestion_projet/src/agentic).

Usage (racine du depot) :

  python gestion_projet/agentic/state.py check
  python gestion_projet/agentic/state.py check --no-fetch
  python gestion_projet/agentic/state.py refresh
  python gestion_projet/agentic/state.py show

Code : gestion_projet/src/agentic/ (pas le package produit renatus).
Donnees : gestion_projet/agentic/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _ensure_gestion_src_path() -> Path:
    """Ajoute gestion_projet/src au path (package agentic)."""
    gestion = Path(__file__).resolve().parents[1]
    src = gestion / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return gestion


def _build_session(gestion: Path | None, repo: Path | None):
    from agentic import AgenticPaths, AgenticSession, EtatStore, GitStatusChecker

    paths = AgenticPaths(gestion_dir=gestion).ensure() if gestion else AgenticPaths().ensure()
    store = EtatStore(paths=paths)
    if repo is not None:
        checker = GitStatusChecker(repo_root=repo)
        return AgenticSession(paths=paths, store=store, git_checker=checker)
    return AgenticSession(paths=paths, store=store, repo_root=None)


def _cmd_show(gestion: Path | None) -> int:
    from agentic import AgenticPaths, EtatSchemaError, EtatStore

    _ensure_gestion_src_path()
    paths = AgenticPaths(gestion_dir=gestion).ensure() if gestion else AgenticPaths().ensure()
    store = EtatStore(paths=paths)
    try:
        etat = store.read()
    except EtatSchemaError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(etat.to_dict(), indent=2, ensure_ascii=False))
    return 0


def _cmd_check(gestion: Path | None, repo: Path | None, fetch: bool) -> int:
    _ensure_gestion_src_path()
    session = _build_session(gestion, repo)
    report = session.startup(fetch=fetch)
    git = report.get("git") or {}
    ok = bool(report.get("ok", True))
    print(
        f"ok={ok} branche={git.get('local_branch')} "
        f"ahead={git.get('ahead')} behind={git.get('behind')} "
        f"dirty={git.get('dirty')} fetch_ok={git.get('fetch_ok')}"
    )
    if git.get("local_tip"):
        print(f"local_tip={git.get('local_tip')} remote_tip={git.get('remote_tip')}")
    if report.get("warnings"):
        for w in report["warnings"]:
            print(f"WARN: {w}")
    if report.get("etat_path"):
        print(f"etat: {report['etat_path']}")
    return 0 if ok else 1


def _cmd_refresh(gestion: Path | None, repo: Path | None, fetch: bool) -> int:
    return _cmd_check(gestion, repo, fetch=fetch)


def main(argv: list[str] | None = None) -> int:
    _ensure_gestion_src_path()
    parser = argparse.ArgumentParser(
        description="CLI agentic (etat.json + check git) — package gestion_projet/src/agentic",
    )
    parser.add_argument(
        "command",
        choices=["show", "check", "refresh"],
        help="show | check | refresh",
    )
    parser.add_argument("--gestion", type=Path, default=None, help="dossier gestion_projet")
    parser.add_argument("--repo", type=Path, default=None, help="racine git")
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="ne pas faire git fetch (check/refresh)",
    )
    args = parser.parse_args(argv)

    fetch = not args.no_fetch
    if args.command == "show":
        return _cmd_show(args.gestion)
    if args.command == "check":
        return _cmd_check(args.gestion, args.repo, fetch=fetch)
    if args.command == "refresh":
        return _cmd_refresh(args.gestion, args.repo, fetch=fetch)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
