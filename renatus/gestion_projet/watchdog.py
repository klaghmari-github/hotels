#!/usr/bin/env python3
"""
Watchdog du dossier gestion_projet.

Ecoute betement les modifications (features.csv, anomalies.csv,
regles_de_gestion.md et tout autre fichier du dossier), applique un
debounce de 5 secondes, puis notifie le gestionnaire via stdout et
via le fichier notifications.log.

La presence de .running indique que le watchdog est actif.
Il reste fonctionnel meme apres traitement des features.

Heartbeat agentic : ecrit periodiquement dans agentic/etat.json
(pid + timestamp) sans declencher de notification (fichier ignore).
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path

# Dossier surveille = dossier contenant ce script
GESTION_DIR = Path(__file__).resolve().parent
RUNNING_FILE = GESTION_DIR / ".running"
STATE_FILE = GESTION_DIR / ".watchdog_state"
NOTIFICATIONS_LOG = GESTION_DIR / "notifications.log"
AGENTIC_ETAT = GESTION_DIR / "agentic" / "etat.json"
DEBOUNCE_SECONDS = 5.0
POLL_INTERVAL = 1.0
HEARTBEAT_INTERVAL = 30.0

# Fichiers / prefixes ignores (etat interne du watchdog)
IGNORE_NAMES = {
    ".running",
    ".watchdog_state",
    "notifications.log",
    "watchdog.py",
    "__pycache__",
}
# Chemins relatifs a GESTION_DIR ignores (heartbeat auto, caches)
IGNORE_REL_PATHS = {
    "agentic/etat.json",
}
IGNORE_SUFFIXES = (".pyc", ".pyo", ".swp", "~")


def _should_ignore(path: Path) -> bool:
    name = path.name
    if name in IGNORE_NAMES:
        return True
    try:
        rel = str(path.resolve().relative_to(GESTION_DIR.resolve()))
    except ValueError:
        rel = name
    if rel in IGNORE_REL_PATHS:
        return True
    if name.startswith(".") and name not in {".running"}:
        # on ignore les fichiers caches internes sauf si utiles
        if name.startswith(".watchdog"):
            return True
    if any(name.endswith(suf) for suf in IGNORE_SUFFIXES):
        return True
    return False


def write_agentic_heartbeat(pid: int | None = None) -> None:
    """
    Met a jour uniquement la section watchdog de agentic/etat.json.

    Fusion minimale (pas de reecriture complete) pour ne pas ecraser
    agents/git/session ecrits par le gestionnaire ou package agentic (gestion_projet/src).
    """
    current_pid = pid if pid is not None else os.getpid()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        AGENTIC_ETAT.parent.mkdir(parents=True, exist_ok=True)
        if AGENTIC_ETAT.is_file():
            try:
                data = json.loads(AGENTIC_ETAT.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except (OSError, json.JSONDecodeError):
                data = {}
        else:
            data = {
                "schema_version": 1,
                "agents": [],
                "features_en_cours": [],
                "anomalies_en_cours": [],
                "locks": {"develop": None, "main": None},
                "git": {},
            }
        watchdog = data.get("watchdog") if isinstance(data.get("watchdog"), dict) else {}
        watchdog["pid"] = current_pid
        watchdog["running"] = True
        watchdog["heartbeat_at"] = ts
        data["watchdog"] = watchdog
        data["updated_at"] = ts
        if "schema_version" not in data:
            data["schema_version"] = 1
        AGENTIC_ETAT.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"WARN|cannot write agentic heartbeat: {exc}", flush=True)


def _file_fingerprint(path: Path) -> str:
    """Hash contenu + mtime + taille pour detecter un vrai changement."""
    try:
        stat = path.stat()
        h = hashlib.sha256()
        h.update(str(stat.st_mtime_ns).encode())
        h.update(str(stat.st_size).encode())
        with path.open("rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return "missing"


def snapshot_dir(directory: Path) -> dict[str, str]:
    """Retourne {chemin_relatif: fingerprint} des fichiers suivis."""
    result: dict[str, str] = {}
    if not directory.is_dir():
        return result
    for root, dirs, files in os.walk(directory):
        # ne pas descendre dans les caches
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git"}]
        root_path = Path(root)
        for name in files:
            path = root_path / name
            if _should_ignore(path):
                continue
            rel = str(path.relative_to(directory))
            result[rel] = _file_fingerprint(path)
    return result


def load_state() -> dict[str, str]:
    if not STATE_FILE.is_file():
        return {}
    state: dict[str, str] = {}
    try:
        for line in STATE_FILE.read_text(encoding="utf-8").splitlines():
            if "\t" not in line:
                continue
            rel, fp = line.split("\t", 1)
            state[rel] = fp
    except OSError:
        return {}
    return state


def save_state(state: dict[str, str]) -> None:
    lines = [f"{rel}\t{fp}" for rel, fp in sorted(state.items())]
    STATE_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def notify(message: str, changed_files: list[str]) -> None:
    """Ecrit une notification lisible par le gestionnaire (stdout + log)."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    files_str = ",".join(changed_files) if changed_files else "-"
    line = f"CHANGE|{ts}|{files_str}|{message}"
    # stdout : le monitor Grok notifie l'agent a chaque ligne
    print(line, flush=True)
    try:
        with NOTIFICATIONS_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as exc:
        print(f"WARN|cannot write notifications.log: {exc}", flush=True)


def create_running() -> None:
    pid = os.getpid()
    RUNNING_FILE.write_text(
        f"pid={pid}\nstarted={time.strftime('%Y-%m-%dT%H:%M:%S')}\n",
        encoding="utf-8",
    )
    print(f"RUNNING|pid={pid}|dir={GESTION_DIR}", flush=True)
    write_agentic_heartbeat(pid=pid)


def remove_running() -> None:
    try:
        if RUNNING_FILE.is_file():
            RUNNING_FILE.unlink()
    except OSError:
        pass
    # Marque watchdog arrete dans etat.json (best effort)
    try:
        if AGENTIC_ETAT.is_file():
            data = json.loads(AGENTIC_ETAT.read_text(encoding="utf-8"))
            watchdog = data.get("watchdog") if isinstance(data.get("watchdog"), dict) else {}
            watchdog["running"] = False
            data["watchdog"] = watchdog
            data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            AGENTIC_ETAT.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except (OSError, json.JSONDecodeError):
        pass


def main() -> int:
    create_running()
    atexit.register(remove_running)

    def _on_signal(signum: int, _frame: object) -> None:
        print(f"STOP|signal={signum}", flush=True)
        remove_running()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    previous = load_state()
    if not previous:
        previous = snapshot_dir(GESTION_DIR)
        save_state(previous)
        notify("watchdog demarre, etat initial enregistre", [])

    # pending: fingerprint en attente de stabilisation
    pending: dict[str, str] | None = None
    pending_since: float | None = None
    last_heartbeat = time.time()

    print(
        f"WATCH|debounce={DEBOUNCE_SECONDS}s|poll={POLL_INTERVAL}s|"
        f"heartbeat={HEARTBEAT_INTERVAL}s|dir={GESTION_DIR}",
        flush=True,
    )

    while True:
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            write_agentic_heartbeat()
            last_heartbeat = now

        current = snapshot_dir(GESTION_DIR)
        if current != previous:
            # changement detecte (ou encore en cours)
            pending = current
            pending_since = time.time()
            previous = current  # pour detecter les changements suivants
            # on n'ecrit pas encore le state final tant que pas stable
        elif pending is not None and pending_since is not None:
            # pas de nouveau changement depuis le dernier poll
            elapsed = time.time() - pending_since
            if elapsed >= DEBOUNCE_SECONDS:
                # stabilise : comparer au dernier etat commite
                committed = load_state()
                changed = sorted(
                    set(pending.keys()) | set(committed.keys())
                )
                really_changed = [
                    rel
                    for rel in changed
                    if pending.get(rel) != committed.get(rel)
                ]
                if really_changed:
                    save_state(pending)
                    notify(
                        "modifications stabilisees apres debounce 5s",
                        really_changed,
                    )
                else:
                    save_state(pending)
                previous = dict(pending)
                pending = None
                pending_since = None

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
