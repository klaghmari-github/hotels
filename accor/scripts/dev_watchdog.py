#!/usr/bin/env python3
"""
Watchdog permanent Accor — ne s'arrête que sur signal / STOP_WATCHDOG_NOW.

Garantit toutes les minutes :
  1. run_dev  (:5500)  + tunnel Cloudflare public
  2. run_admin (:5055) + tunnel Cloudflare public
  3. run_user  (:5056) + tunnel (optionnel mais maintenu)
  4. README git à jour avec les URL publiques
  5. pull/fetch du README distant pour exécuter les consignes ``watchdog>``

Consignes (section « Watchdog inbox » du README, aussi lues depuis le remote) :

  watchdog> status
  watchdog> restart admin|user|dev|all
  watchdog> reexpose [admin|user|dev|all]
  watchdog> note: texte libre
  watchdog> STOP_WATCHDOG_NOW   # arrêt volontaire

Lancer (indéfini) :
  nohup python scripts/dev_watchdog.py >> /tmp/accor-dev-watchdog.log 2>&1 &

Désactiver push : ACCOR_DEV_NO_PUSH=1
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # accor/
README = ROOT / "README.md"
STATE_DIR = ROOT / "data" / "dev_console"
LOG_DIR = Path(os.environ.get("ACCOR_TUNNEL_LOG_DIR") or "/tmp/accor-tunnels")
WD_PID_FILE = STATE_DIR / "watchdog.pid"
WD_LOG = Path(os.environ.get("ACCOR_DEV_WATCHDOG_LOG") or "/tmp/accor-dev-watchdog.log")

PREFERRED_DEV_PORT = int(os.environ.get("ACCOR_DEV_PORT") or 5500)
ADMIN_PORT = int(os.environ.get("ACCOR_ADMIN_PORT") or 5055)
USER_PORT = int(os.environ.get("ACCOR_USER_PORT") or 5056)
FALLBACK_DEV_PORTS = [PREFERRED_DEV_PORT + i for i in range(0, 11)]
MAX_RETRIES = 3
CHECK_EVERY = int(os.environ.get("ACCOR_DEV_WATCH_INTERVAL") or 60)
PYTHON = sys.executable

_ALL_SERVICES = {
    "dev": {
        "port": PREFERRED_DEV_PORT,
        "script": ROOT / "run_dev.py",
        "pid_file": STATE_DIR / "run_dev.pid",
        "port_file": STATE_DIR / "run_dev.port",
        "log": Path(os.environ.get("ACCOR_DEV_LOG") or "/tmp/accor-run-dev.log"),
        "health": "/api/health",
        "args_extra": lambda port: ["--host", "0.0.0.0", "--port", str(port)],
        "public_required": True,
        "fallback_ports": FALLBACK_DEV_PORTS,
    },
    "admin": {
        "port": ADMIN_PORT,
        "script": ROOT / "run_admin.py",
        "pid_file": STATE_DIR / "run_admin.pid",
        "port_file": STATE_DIR / "run_admin.port",
        "log": Path("/tmp/accor-run-admin.log"),
        "health": "/api/health",
        "args_extra": lambda port: ["--host", "0.0.0.0", "--port", str(port)],
        "public_required": True,
        "fallback_ports": [ADMIN_PORT],
    },
    "user": {
        "port": USER_PORT,
        "script": ROOT / "run_user.py",
        "pid_file": STATE_DIR / "run_user.pid",
        "port_file": STATE_DIR / "run_user.port",
        "log": Path("/tmp/accor-run-user.log"),
        "health": "/api/health",
        "args_extra": lambda port: ["--host", "0.0.0.0", "--port", str(port)],
        "public_required": False,
        "fallback_ports": [USER_PORT],
    },
}


def _active_service_names() -> list[str]:
    """
    Services gérés par le watchdog.

    Env ``ACCOR_WD_SERVICES`` = liste CSV (ex. ``dev`` ou ``dev,admin,user``).
    Défaut : tous. Mode lab manuel : ``ACCOR_WD_SERVICES=dev`` pour laisser
    free les ports 5055/5056 à l'utilisateur.
    """
    raw = (os.environ.get("ACCOR_WD_SERVICES") or "").strip()
    if not raw:
        return list(_ALL_SERVICES.keys())
    names = [x.strip().lower() for x in raw.split(",") if x.strip()]
    out = [n for n in names if n in _ALL_SERVICES]
    return out or ["dev"]


# Vue filtrée (référencée partout dans le module)
SERVICES = {k: _ALL_SERVICES[k] for k in _active_service_names()}

_running = True
_service_ports: dict[str, int] = {
    "dev": PREFERRED_DEV_PORT,
    "admin": ADMIN_PORT,
    "user": USER_PORT,
}
_last_outbox: list[str] = []


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _git_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return Path(out.strip())
    except Exception:
        return ROOT.parent if (ROOT.parent / ".git").exists() else ROOT


def _git_readme_path() -> str:
    """Chemin README relatif à la racine git."""
    gr = _git_root()
    try:
        return str(README.resolve().relative_to(gr.resolve()))
    except Exception:
        return "accor/README.md"


def _run_git(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(_git_root()),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _resolve_cloudflared() -> Path | None:
    local = ROOT / "bin" / "cloudflared"
    if local.is_file() and os.access(local, os.X_OK):
        return local
    which = subprocess.run(
        ["command", "-v", "cloudflared"],
        shell=True,
        capture_output=True,
        text=True,
    )
    # fallback path search
    for p in ("/usr/local/bin/cloudflared", "/usr/bin/cloudflared"):
        if Path(p).is_file():
            return Path(p)
    try:
        out = subprocess.check_output(["which", "cloudflared"], text=True).strip()
        if out:
            return Path(out)
    except Exception:
        pass
    return None


# ── ports / process ──────────────────────────────────────────────────────────


def port_pids(port: int) -> list[int]:
    pids: set[int] = set()
    try:
        out = subprocess.check_output(
            ["ss", "-tlnp"], text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            if f":{port} " in line or line.rstrip().endswith(f":{port}"):
                for m in re.finditer(r"pid=(\d+)", line):
                    pids.add(int(m.group(1)))
    except Exception:
        pass
    if not pids:
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for part in out.split():
                if part.isdigit():
                    pids.add(int(part))
        except Exception:
            pass
    return sorted(pids)


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def kill_pids(pids: set[int], *, label: str = "") -> None:
    me = os.getpid()
    for pid in sorted(pids):
        if pid <= 1 or pid == me:
            continue
        try:
            _log(f"kill pid={pid} {label}")
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            _log(f"impossible de tuer {pid}: {exc}")
    time.sleep(0.7)
    for pid in sorted(pids):
        if pid <= 1 or pid == me:
            continue
        try:
            os.kill(pid, 0)
            _log(f"kill -9 pid={pid}")
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            pass
    time.sleep(0.3)


def kill_port_occupants(port: int, pid_file: Path | None = None) -> None:
    victims: set[int] = set(port_pids(port))
    if pid_file and pid_file.exists():
        try:
            victims.add(int(pid_file.read_text().strip()))
        except Exception:
            pass
    kill_pids(victims, label=f"(port {port})")


def http_ok(url: str, timeout: float = 4.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def health_ok(name: str, port: int | None = None) -> bool:
    cfg = SERVICES[name]
    port = port if port is not None else _service_ports.get(name, cfg["port"])
    return http_ok(f"http://127.0.0.1:{port}{cfg['health']}")


def lan_url(port: int) -> str:
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from accor.serve_utils import lan_ipv4_addresses

        ips = lan_ipv4_addresses()
        if ips:
            return f"http://{ips[0]}:{port}"
    except Exception:
        pass
    return f"http://127.0.0.1:{port}"


# ── services ─────────────────────────────────────────────────────────────────


def start_service(name: str, port: int) -> bool:
    cfg = SERVICES[name]
    script: Path = cfg["script"]
    if not script.is_file():
        _log(f"{name}: script absent {script}")
        return False
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path: Path = cfg["log"]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src")
        + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""),
    }
    # Ne pas laisser un ACCOR_PORT parent écraser admin/user
    env.pop("ACCOR_PORT", None)
    if name == "dev":
        env["ACCOR_DEV_PORT"] = str(port)

    args = [PYTHON, str(script), *cfg["args_extra"](port)]
    logf = open(log_path, "a", encoding="utf-8")
    logf.write(f"\n--- start {name} {_now_iso()} port={port} ---\n")
    logf.flush()
    proc = subprocess.Popen(
        args,
        cwd=str(ROOT),
        env=env,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    cfg["pid_file"].write_text(str(proc.pid) + "\n", encoding="utf-8")
    cfg["port_file"].write_text(str(port) + "\n", encoding="utf-8")
    _service_ports[name] = port
    _log(f"{name} démarré pid={proc.pid} port={port} log={log_path}")
    for _ in range(25):
        if health_ok(name, port):
            return True
        time.sleep(0.8)
        if proc.poll() is not None:
            _log(f"{name} mort immédiatement (code={proc.returncode})")
            return False
    _log(f"{name} health timeout sur :{port}")
    return False


def try_start_service(name: str) -> bool:
    cfg = SERVICES[name]
    ports = list(cfg.get("fallback_ports") or [cfg["port"]])
    for port in ports:
        for attempt in range(1, MAX_RETRIES + 1):
            _log(f"{name}: tentative {attempt}/{MAX_RETRIES} port {port}")
            if not port_free(port) or port_pids(port):
                kill_port_occupants(port, cfg["pid_file"])
            if not port_free(port):
                time.sleep(0.4)
                continue
            if start_service(name, port):
                return True
            kill_port_occupants(port, cfg["pid_file"])
            time.sleep(0.4)
    return False


def ensure_service(name: str) -> bool:
    cfg = SERVICES[name]
    # restore last known port
    pf: Path = cfg["port_file"]
    if pf.exists():
        try:
            p = int(pf.read_text().strip())
            if 1 <= p <= 65535:
                _service_ports[name] = p
        except Exception:
            pass
    port = _service_ports[name]
    if health_ok(name, port):
        return True
    # preferred port maybe still up
    if port != cfg["port"] and health_ok(name, cfg["port"]):
        _service_ports[name] = cfg["port"]
        pf.write_text(str(cfg["port"]) + "\n", encoding="utf-8")
        return True
    _log(f"{name} DOWN — redémarrage…")
    return try_start_service(name)


# ── tunnels Cloudflare ───────────────────────────────────────────────────────


def tunnel_url_file(name: str) -> Path:
    return STATE_DIR / f"tunnel_{name}.url"


def tunnel_pid_file(name: str) -> Path:
    return LOG_DIR / f"{name}.pid"


def tunnel_log_file(name: str) -> Path:
    return LOG_DIR / f"{name}.log"


def read_tunnel_url(name: str) -> str | None:
    f = tunnel_url_file(name)
    try:
        if not f.exists():
            return None
        url = f.read_text(encoding="utf-8").strip().rstrip("/")
        if url.startswith("http://") or url.startswith("https://"):
            return url
    except Exception:
        pass
    return None


def tunnel_process_alive(name: str) -> bool:
    pf = tunnel_pid_file(name)
    if not pf.exists():
        return False
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def public_health(name: str, *, timeout: float = 6.0) -> bool:
    url = read_tunnel_url(name)
    if not url:
        return False
    cfg = SERVICES.get(name)
    path = (cfg or {}).get("health") or "/"
    if http_ok(url + path, timeout=timeout):
        return True
    return http_ok(url + "/", timeout=timeout)


def _parse_tunnel_url_from_log(log_path: Path) -> str | None:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = re.findall(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com", text)
    return m[-1] if m else None


def start_tunnel(name: str, port: int) -> str | None:
    """Démarre un quick tunnel cloudflared ; retourne l'URL publique."""
    cf = _resolve_cloudflared()
    if not cf:
        _log("cloudflared introuvable (bin/cloudflared)")
        return None
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # kill previous
    if tunnel_process_alive(name):
        try:
            kill_pids({int(tunnel_pid_file(name).read_text().strip())}, label=f"tunnel {name}")
        except Exception:
            pass
    log_path = tunnel_log_file(name)
    log_path.write_text("", encoding="utf-8")
    logf = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [str(cf), "tunnel", "--url", f"http://127.0.0.1:{port}"],
        cwd=str(ROOT),
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    tunnel_pid_file(name).write_text(str(proc.pid) + "\n", encoding="utf-8")
    _log(f"tunnel {name} démarré pid={proc.pid} → :{port}")
    url = None
    for _ in range(40):
        time.sleep(0.5)
        url = _parse_tunnel_url_from_log(log_path)
        if url:
            tunnel_url_file(name).write_text(url + "\n", encoding="utf-8")
            _log(f"tunnel {name} public : {url}")
            return url
        if proc.poll() is not None:
            _log(f"tunnel {name} mort (code={proc.returncode})")
            return None
    _log(f"tunnel {name}: timeout URL")
    return None


def ensure_tunnel(name: str, *, check_public: bool = True) -> str | None:
    port = _service_ports.get(name, SERVICES[name]["port"])
    if not health_ok(name, port):
        return read_tunnel_url(name)
    # process cloudflared vivant + URL connue → OK (check public optionnel)
    if tunnel_process_alive(name):
        url = read_tunnel_url(name) or _parse_tunnel_url_from_log(tunnel_log_file(name))
        if url:
            tunnel_url_file(name).write_text(url + "\n", encoding="utf-8")
            if not check_public or public_health(name):
                return url
            _log(f"tunnel {name} process up mais URL morte → restart")
        else:
            _log(f"tunnel {name} process up sans URL dans le log → restart")
    else:
        _log(f"tunnel {name} absent/mort → start")
    return start_tunnel(name, port)


def public_url_for(name: str) -> str:
    u = read_tunnel_url(name)
    if u:
        return u
    return lan_url(_service_ports.get(name, SERVICES[name]["port"]))


# ── README ───────────────────────────────────────────────────────────────────

HEADER_KEYS = ("run_dev url", "run_admin url", "run_user url", "watchdog status", "run_dev note")

INBOX_SECTION = "## Watchdog inbox"
OUTBOX_SECTION = "## Watchdog outbox"


def _strip_managed_header(text: str) -> str:
    """Retire les lignes d'en-tête gérées par le watchdog."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    # drop leading blank + managed lines
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            # keep single blank after header later
            if out:
                break
            continue
        low = s.lower()
        if any(low.startswith(k + " :") or low.startswith(k + ":") for k in HEADER_KEYS):
            i += 1
            continue
        break
    out.extend(lines[i:])
    return "".join(out).lstrip("\n")


def _extract_section(text: str, title: str) -> tuple[str, str, str]:
    """Retourne (before, section_body_with_title, after)."""
    pat = re.compile(
        rf"(^|\n)({re.escape(title)}\s*\n)(.*?)(?=\n## |\Z)",
        re.S | re.M,
    )
    m = pat.search(text)
    if not m:
        return text, "", ""
    start = m.start(2) if m.group(1) == "" else m.start(2)
    # include leading newline handling
    sec_start = m.start() + (len(m.group(1)) if m.group(1) else 0)
    sec_end = m.end()
    before = text[:sec_start]
    section = text[sec_start:sec_end]
    after = text[sec_end:]
    return before, section, after


def _parse_cmds(text: str) -> list[str]:
    cmds: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.lower().startswith("watchdog>"):
            continue
        if re.search(r"#\s*DONE\b", s, re.I):
            continue
        body = s.split(">", 1)[1].strip()
        if body:
            cmds.append(body)
    return cmds


def _readme_header_urls(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines()[:20]:
        m = re.match(
            r"^(run_dev url|run_admin url|run_user url)\s*:\s*(\S+)",
            line.strip(),
            re.I,
        )
        if m:
            out[m.group(1).lower()] = m.group(2).rstrip("/")
    return out


def update_readme_urls(
    *,
    note: str | None = None,
    outbox_lines: list[str] | None = None,
    mark_cmds_done: list[str] | None = None,
    force: bool = False,
) -> bool:
    """Met à jour le README. Retourne True si le fichier a changé de façon
    significative (URL / consignes) — pas seulement un timestamp local."""
    if not README.exists():
        _log("README.md absent")
        return False
    text = README.read_text(encoding="utf-8")
    body = _strip_managed_header(text)

    dev_u = public_url_for("dev")
    admin_u = public_url_for("admin")
    user_u = public_url_for("user")
    prev = _readme_header_urls(text)
    urls_changed = (
        prev.get("run_dev url") != dev_u.rstrip("/")
        or prev.get("run_admin url") != admin_u.rstrip("/")
        or prev.get("run_user url") != user_u.rstrip("/")
    )
    meaningful = force or urls_changed or bool(outbox_lines) or bool(mark_cmds_done)

    st = (
        f"UP · interval={CHECK_EVERY}s · "
        f"ports dev={_service_ports['dev']} admin={_service_ports['admin']} "
        f"user={_service_ports['user']}"
    )
    header = (
        f"run_dev url : {dev_u}\n"
        f"run_admin url : {admin_u}\n"
        f"run_user url : {user_u}\n"
        f"watchdog status : {st}\n"
    )
    if note:
        header += f"run_dev note : {note}\n"


    # Ensure inbox/outbox sections exist
    if INBOX_SECTION not in body:
        body = body.rstrip() + (
            f"\n\n{INBOX_SECTION}\n\n"
            "<!-- Ajoutez une consigne par ligne : watchdog> restart admin | reexpose | note: … -->\n"
            "<!-- Le watchdog lit aussi le README distant (git pull/fetch) chaque minute. -->\n\n"
        )
    if OUTBOX_SECTION not in body:
        body = body.rstrip() + f"\n\n{OUTBOX_SECTION}\n\n_(vide)_\n"

    # Mark done cmds in inbox
    if mark_cmds_done:
        before, sec, after = _extract_section(body, INBOX_SECTION)
        if sec:
            new_sec_lines = []
            for line in sec.splitlines(keepends=True):
                stripped = line.strip()
                if stripped.lower().startswith("watchdog>"):
                    body_cmd = stripped.split(">", 1)[1].strip()
                    if any(
                        body_cmd == c or body_cmd.startswith(c)
                        for c in mark_cmds_done
                    ) and not re.search(r"#\s*DONE\b", stripped, re.I):
                        line = line.rstrip("\n") + f"  # DONE {_now_iso()}\n"
                        if not line.endswith("\n"):
                            line += "\n"
                new_sec_lines.append(line)
            body = before + "".join(new_sec_lines) + after

    if outbox_lines:
        before, sec, after = _extract_section(body, OUTBOX_SECTION)
        stamp = _now_iso()
        entries = "\n".join(f"- `{stamp}` {e}" for e in outbox_lines) + "\n"
        if sec:
            # insert after title line
            lines = sec.splitlines(keepends=True)
            # drop "_(vide)_"
            rest = []
            for i, ln in enumerate(lines):
                if i == 0:
                    rest.append(ln)
                    continue
                if ln.strip() == "_(vide)_":
                    continue
                rest.append(ln)
            # keep last ~40 entries
            content = "".join(rest[1:])
            new_sec = rest[0] + entries + content
            # trim old
            all_entries = [
                ln for ln in new_sec.splitlines(keepends=True) if ln.startswith("- `")
            ]
            head = [ln for ln in new_sec.splitlines(keepends=True) if not ln.startswith("- `")]
            kept = all_entries[:40]
            body = before + "".join(head[:1]) + "".join(kept) + (
                "".join(head[1:]) if len(head) > 1 else ""
            ) + after
        else:
            body = body.rstrip() + f"\n\n{OUTBOX_SECTION}\n\n{entries}"

    # Keep public URL table in § Accès if present
    def _sub_table_url(txt: str, label: str, url: str) -> str:
        # | **run_dev** ... | 5500 | url |
        pat = re.compile(
            rf"(\|\s*\*\*{re.escape(label)}\*\*[^\n|]*\|[^\n|]*\|\s*)(https?://[^\s|]+)(\s*\|)",
            re.I,
        )
        return pat.sub(rf"\g<1>{url}\g<3>", txt)

    body = _sub_table_url(body, "run_dev", dev_u)
    body = _sub_table_url(body, "Admin", admin_u)
    body = _sub_table_url(body, "User", user_u)

    new_text = header + "\n" + body.lstrip()
    if new_text == text:
        return False
    # Évite de dirty le README chaque minute si seules des lignes annexes bougent
    if not meaningful and not force:
        # sections inbox manquantes comptent comme meaningful
        if INBOX_SECTION in text and OUTBOX_SECTION in text:
            return False
    README.write_text(new_text, encoding="utf-8")
    _log(f"README mis à jour · dev={dev_u} admin={admin_u} meaningful={meaningful}")
    return meaningful


def git_push_readme(message: str | None = None) -> None:
    if os.environ.get("ACCOR_DEV_NO_PUSH", "").strip().lower() in {"1", "true", "yes"}:
        _log("push désactivé (ACCOR_DEV_NO_PUSH)")
        return
    rel = _git_readme_path()
    st = _run_git(["status", "--porcelain", rel])
    if not (st.stdout or "").strip():
        _log("git: README inchangé")
        return
    _run_git(["add", rel])
    msg = message or f"chore: public urls dev={public_url_for('dev')} admin={public_url_for('admin')}"
    c = _run_git(["commit", "-m", msg])
    if c.returncode != 0:
        _log(f"git commit: {(c.stderr or c.stdout or '')[:300]}")
        return
    for remote in ("github", "origin"):
        # push current branch
        br = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        branch = (br.stdout or "main").strip() or "main"
        p = _run_git(["push", remote, f"HEAD:refs/heads/{branch}"], timeout=120)
        if p.returncode == 0:
            _log(f"git push {remote} OK")
            return
        _log(f"git push {remote}: {(p.stderr or p.stdout or '')[:250]}")
    _log("git push: échec tous remotes")


def git_fetch_remote_readme() -> str | None:
    """Fetch et lit le README distant sans merger (pour consignes)."""
    for remote in ("github", "origin"):
        try:
            f = _run_git(["fetch", remote, "--quiet"], timeout=45)
        except subprocess.TimeoutExpired:
            _log(f"git fetch {remote}: timeout")
            continue
        if f.returncode != 0:
            _log(f"git fetch {remote}: {(f.stderr or '')[:200]}")
            continue
        for ref in (f"{remote}/main", f"{remote}/master", f"{remote}/HEAD"):
            s = _run_git(["show", f"{ref}:{_git_readme_path()}"], timeout=15)
            if s.returncode == 0 and s.stdout:
                return s.stdout
    return None


def git_pull_rebase() -> None:
    """Intègre les commits distants avant push (best-effort)."""
    for remote in ("github", "origin"):
        br = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        branch = (br.stdout or "main").strip() or "main"
        p = _run_git(["pull", "--rebase", remote, branch], timeout=120)
        if p.returncode == 0:
            _log(f"git pull --rebase {remote}/{branch} OK")
            return
        # abort failed rebase if any
        _run_git(["rebase", "--abort"])
        _log(f"git pull {remote}: {(p.stderr or p.stdout or '')[:200]}")


# ── consignes ────────────────────────────────────────────────────────────────


def execute_cmd(cmd: str) -> str:
    """Exécute une consigne ; retourne message outbox."""
    global _running
    c = cmd.strip()
    low = c.lower()
    _log(f"consigne: {c}")

    if low == "status":
        parts = []
        for name in ("dev", "admin", "user"):
            ok = health_ok(name)
            pub = read_tunnel_url(name) or "—"
            parts.append(f"{name}={'UP' if ok else 'DOWN'} public={pub}")
        return "status · " + " · ".join(parts)

    if low == "stop_watchdog_now":
        _running = False
        return "STOP_WATCHDOG_NOW reçu — arrêt du watchdog"

    if low.startswith("note:") or low.startswith("note "):
        return f"note enregistrée: {c.split(':', 1)[-1].strip() if ':' in c else c[5:].strip()}"

    if low.startswith("restart"):
        target = low.replace("restart", "", 1).strip() or "all"
        names = ["dev", "admin", "user"] if target in ("all", "*") else [target]
        results = []
        for name in names:
            if name not in SERVICES:
                results.append(f"{name}=inconnu")
                continue
            cfg = SERVICES[name]
            kill_port_occupants(_service_ports[name], cfg["pid_file"])
            ok = try_start_service(name)
            if ok and cfg.get("public_required"):
                ensure_tunnel(name)
            elif ok and name == "user":
                ensure_tunnel(name)
            results.append(f"{name}={'OK' if ok else 'FAIL'}")
        return "restart · " + ", ".join(results)

    if low.startswith("reexpose"):
        target = low.replace("reexpose", "", 1).strip() or "all"
        names = ["dev", "admin", "user"] if target in ("all", "*", "") else [target]
        results = []
        for name in names:
            if name not in SERVICES:
                results.append(f"{name}=inconnu")
                continue
            if not health_ok(name):
                ensure_service(name)
            url = start_tunnel(name, _service_ports[name])
            results.append(f"{name}={url or 'FAIL'}")
        return "reexpose · " + ", ".join(results)

    return f"commande inconnue: {c} (status|restart …|reexpose …|note: …|STOP_WATCHDOG_NOW)"


def process_remote_consignes() -> list[str]:
    remote = git_fetch_remote_readme()
    texts = []
    if remote:
        texts.append(remote)
    if README.exists():
        texts.append(README.read_text(encoding="utf-8"))
    # merge unique pending cmds (remote first priority)
    seen: set[str] = set()
    pending: list[str] = []
    for t in texts:
        for cmd in _parse_cmds(t):
            key = cmd.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            pending.append(cmd)
    if not pending:
        return []
    results = []
    done = []
    for cmd in pending:
        try:
            msg = execute_cmd(cmd)
        except Exception as exc:
            msg = f"erreur sur `{cmd}`: {exc}"
        results.append(msg)
        done.append(cmd)
    if results:
        update_readme_urls(outbox_lines=results, mark_cmds_done=done)
        git_pull_rebase()
        git_push_readme("chore: watchdog consignes exécutées")
    return results


# ── cycle principal ──────────────────────────────────────────────────────────


_cycle_n = 0


def cycle() -> None:
    global _cycle_n
    _cycle_n += 1
    # check HTTP public every 5th cycle (plus rapide sinon)
    check_public = (_cycle_n % 5 == 1)
    managed = list(SERVICES.keys())
    health_bits = " ".join(
        f"{n}={health_ok(n) if n in SERVICES else 'off'}" for n in ("dev", "admin", "user")
    )
    _log(f"cycle #{_cycle_n} · {health_bits} · managed={managed} · pub_check={check_public}")

    # 1) services
    for name in managed:
        try:
            ok = ensure_service(name)
            if not ok:
                _log(f"{name} toujours DOWN")
        except Exception as exc:
            _log(f"ensure_service {name}: {exc}")

    # 2) tunnels
    for name in managed:
        try:
            if name == "user" and not health_ok(name):
                continue
            ensure_tunnel(
                name,
                check_public=check_public
                or SERVICES[name].get("public_required", False)
                and not read_tunnel_url(name),
            )
        except Exception as exc:
            _log(f"ensure_tunnel {name}: {exc}")

    # 3) README urls
    try:
        changed = update_readme_urls()
        if changed:
            git_pull_rebase()
            git_push_readme()
        else:
            _log(
                f"urls ok · dev={public_url_for('dev')} · admin={public_url_for('admin')}"
            )
    except Exception as exc:
        _log(f"update_readme: {exc}")

    # 4) consignes distantes
    try:
        n = process_remote_consignes()
        if n:
            _log(f"{len(n)} consigne(s) exécutée(s)")
        else:
            _log("aucune consigne distante")
    except Exception as exc:
        _log(f"consignes: {exc}")


def _kill_stale_watchdog() -> None:
    if not WD_PID_FILE.exists():
        return
    try:
        old = int(WD_PID_FILE.read_text().strip())
    except Exception:
        return
    if old == os.getpid():
        return
    try:
        os.kill(old, 0)
    except ProcessLookupError:
        return
    except Exception:
        return
    _log(f"ancien watchdog pid={old} → SIGTERM")
    try:
        os.kill(old, signal.SIGTERM)
        time.sleep(1)
        os.kill(old, signal.SIGKILL)
    except Exception:
        pass


def main() -> None:
    global _running

    def _stop(*_a):
        global _running
        _running = False
        _log("signal stop reçu")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _kill_stale_watchdog()
    WD_PID_FILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")

    # restore ports
    for name, cfg in SERVICES.items():
        pf = cfg["port_file"]
        if pf.exists():
            try:
                _service_ports[name] = int(pf.read_text().strip())
            except Exception:
                pass

    _log(
        f"watchdog PERMANENT démarré pid={os.getpid()} "
        f"interval={CHECK_EVERY}s services={list(SERVICES.keys())} "
        f"cloudflared={_resolve_cloudflared()}"
    )
    try:
        cycle()
    except Exception as exc:
        _log(f"erreur cycle initial: {exc}")

    while _running:
        for _ in range(CHECK_EVERY):
            if not _running:
                break
            time.sleep(1)
        if not _running:
            break
        try:
            cycle()
        except Exception as exc:
            _log(f"erreur cycle: {exc}")

    _log("watchdog arrêté")
    try:
        WD_PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
