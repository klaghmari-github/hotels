"""
Console Grok Web (run_dev) — interface navigateur pour discuter avec Grok
sur le projet Accor (headless ``grok -p``).

Lancer
------
  python run_dev.py
  python run_dev.py --port 5500
  accor-dev

Port défaut : **5500** (watchdog), host 0.0.0.0 (réseau).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template_string, request, stream_with_context

from accor.cache_bust import register_cache_bust
from accor.data_io import PROJECT_ROOT, STATIC_DIR
from accor.serve_utils import (
    default_host,
    default_port,
    lan_ipv4_addresses,
    print_listen_banner,
    run_flask_app,
)

DEV_PORT_DEFAULT = 5500
PROJECT_CWD = PROJECT_ROOT.parent if PROJECT_ROOT.name == "accor" else PROJECT_ROOT
# session web dédiée (stable) sous le cwd hotels
WEB_SESSION_FILE = PROJECT_ROOT / "data" / "dev_console" / "web_session_id.txt"
CHAT_LOG = PROJECT_ROOT / "data" / "dev_console" / "chat.jsonl"
STATE_DIR = PROJECT_ROOT / "data" / "dev_console"

_lock = threading.Lock()
_busy = False
_last_error: str | None = None

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
register_cache_bust(app, STATIC_DIR)


def _ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _web_session_id() -> str:
    _ensure_dirs()
    if WEB_SESSION_FILE.exists():
        sid = WEB_SESSION_FILE.read_text(encoding="utf-8").strip()
        if sid:
            return sid
    # UUID v4 ok for -s in many versions; headless may want UUID
    sid = str(uuid.uuid4())
    WEB_SESSION_FILE.write_text(sid + "\n", encoding="utf-8")
    return sid


def _append_log(role: str, content: str, **extra: Any) -> dict[str, Any]:
    _ensure_dirs()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "content": content,
        **extra,
    }
    with _lock:
        with CHAT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _read_log(limit: int = 200) -> list[dict[str, Any]]:
    if not CHAT_LOG.exists():
        return []
    lines = CHAT_LOG.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _find_grok_bin() -> str:
    return os.environ.get("GROK_BIN") or "grok"


def _run_grok(prompt: str, *, timeout: int = 600) -> dict[str, Any]:
    """
    Appelle Grok en headless sur le cwd projet.
    Utilise une session dédiée web (reprise si possible).
    """
    global _last_error
    grok = _find_grok_bin()
    cwd = str(PROJECT_CWD)
    sid = _web_session_id()

    # Prefer continue dedicated session via --resume if dir exists, else -s new
    session_dir = (
        Path.home()
        / ".grok"
        / "sessions"
        / ("%2F".join(cwd.strip("/").split("/")).replace("/", "%2F") if False else "")
    )
    # encoded cwd as Grok does: quote path
    from urllib.parse import quote

    enc = quote(cwd, safe="")
    sess_root = Path.home() / ".grok" / "sessions" / enc
    resume = (sess_root / sid).is_dir()

    cmd = [
        grok,
        "-p",
        prompt,
        "--cwd",
        cwd,
        "--output-format",
        "plain",
        "--no-auto-update",
    ]
    if resume:
        cmd.extend(["--resume", sid])
    else:
        cmd.extend(["--session-id", sid])

    # permission: allow tools but not full yolo by default; allow env override
    if os.environ.get("ACCOR_DEV_YOLO", "").strip() in {"1", "true", "yes"}:
        cmd.append("--always-approve")
    else:
        # headless often needs permission mode
        cmd.extend(["--permission-mode", "bypassPermissions"])

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env={**os.environ, "GROK_AGENT": os.environ.get("GROK_AGENT", "1")},
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0 and not out:
            _last_error = err or f"exit {proc.returncode}"
            return {
                "ok": False,
                "error": _last_error,
                "stderr": err[-2000:],
                "duration_s": round(time.time() - t0, 2),
                "session_id": sid,
            }
        # strip ANSI
        out_clean = re.sub(r"\x1b\[[0-9;]*m", "", out)
        return {
            "ok": True,
            "content": out_clean or "(réponse vide)",
            "stderr": err[-1000:] if err else "",
            "duration_s": round(time.time() - t0, 2),
            "session_id": sid,
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        _last_error = f"Timeout après {timeout}s"
        return {"ok": False, "error": _last_error, "session_id": sid}
    except FileNotFoundError:
        _last_error = f"Binaire grok introuvable ({grok}). Installez Grok Build TUI."
        return {"ok": False, "error": _last_error}
    except Exception as exc:
        _last_error = str(exc)
        return {"ok": False, "error": _last_error, "session_id": sid}


def _read_session_tail(n: int = 50) -> list[dict[str, Any]]:
    """Lit les derniers updates de la session web Grok (si présente)."""
    from urllib.parse import quote

    cwd = str(PROJECT_CWD)
    enc = quote(cwd, safe="")
    sid = _web_session_id()
    path = Path.home() / ".grok" / "sessions" / enc / sid / "updates.jsonl"
    if not path.exists():
        # try active TUI session for same cwd
        active = Path.home() / ".grok" / "active_sessions.json"
        if active.exists():
            try:
                data = json.loads(active.read_text(encoding="utf-8"))
                for item in data if isinstance(data, list) else []:
                    if item.get("cwd") == cwd:
                        sid2 = item.get("session_id")
                        p2 = Path.home() / ".grok" / "sessions" / enc / str(sid2) / "updates.jsonl"
                        if p2.exists():
                            path = p2
                            break
            except Exception:
                pass
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ── HTML UI ──────────────────────────────────────────────────────────────

DEV_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Accor · Grok Dev Console</title>
  <link rel="stylesheet" href="{{ asset('shared/css/tokens.css') }}" />
  <style>
    :root {
      --bg: #0c1017;
      --panel: #141a24;
      --ink: #e8eef7;
      --muted: #8b97a8;
      --line: rgba(255,255,255,.08);
      --accent: #c9a227;
      --user: #1e3a5f;
      --assistant: #1a2433;
      --ok: #34d399;
      --err: #f87171;
      --font: "DM Sans", system-ui, sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; height: 100%; background: var(--bg); color: var(--ink); font-family: var(--font); }
    body {
      display: grid;
      grid-template-rows: auto 1fr auto;
      min-height: 100vh;
    }
    header {
      display: flex; align-items: center; justify-content: space-between;
      padding: .85rem 1.25rem;
      background: linear-gradient(180deg, #151d2e, #0f1520);
      border-bottom: 1px solid var(--line);
    }
    .brand { display: flex; gap: .75rem; align-items: center; }
    .mark {
      width: 36px; height: 36px; border-radius: 10px;
      background: linear-gradient(135deg, var(--accent), #e0c15a);
      color: #1a1405; font-weight: 800; display: grid; place-items: center;
    }
    .brand strong { letter-spacing: .06em; }
    .brand small { color: var(--muted); display: block; font-size: .75rem; }
    .chips { display: flex; gap: .4rem; flex-wrap: wrap; }
    .chip {
      font-size: .72rem; padding: .25rem .6rem; border-radius: 999px;
      border: 1px solid var(--line); color: var(--muted);
    }
    .chip.ok { color: var(--ok); border-color: rgba(52,211,153,.35); }
    .chip.busy { color: #fbbf24; border-color: rgba(251,191,36,.35); }
    main {
      overflow: auto;
      padding: 1rem 1.25rem 1.5rem;
      display: flex; flex-direction: column; gap: .85rem;
    }
    .msg {
      max-width: min(860px, 100%);
      padding: .9rem 1.05rem;
      border-radius: 14px;
      border: 1px solid var(--line);
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .msg.user { align-self: flex-end; background: var(--user); }
    .msg.assistant { align-self: flex-start; background: var(--assistant); }
    .msg.system { align-self: center; background: transparent; color: var(--muted); font-size: .85rem; border-style: dashed; }
    .msg .meta { font-size: .7rem; color: var(--muted); margin-bottom: .35rem; }
    .msg.error { border-color: rgba(248,113,113,.4); color: #fecaca; }
    footer {
      border-top: 1px solid var(--line);
      padding: .85rem 1.25rem 1.1rem;
      background: #0f1520;
    }
    .composer {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: .65rem;
      max-width: 960px;
      margin: 0 auto;
    }
    textarea {
      width: 100%; min-height: 72px; max-height: 200px;
      resize: vertical; border-radius: 12px; border: 1px solid var(--line);
      background: var(--panel); color: var(--ink); font: inherit;
      padding: .75rem .9rem;
    }
    textarea:focus { outline: 2px solid rgba(201,162,39,.35); }
    button.send {
      border: 0; border-radius: 12px; padding: 0 1.2rem;
      background: linear-gradient(135deg, var(--accent), #e0c15a);
      color: #1a1405; font-weight: 700; cursor: pointer;
      font-size: .95rem;
    }
    button.send:disabled { opacity: .45; cursor: not-allowed; }
    .links { display: flex; gap: .75rem; flex-wrap: wrap; margin-top: .55rem; font-size: .78rem; }
    .links a { color: #93c5fd; }
    .progress {
      display: none; max-width: 960px; margin: 0 auto .65rem;
      padding: .55rem .75rem; border-radius: 10px;
      background: rgba(251,191,36,.08); border: 1px solid rgba(251,191,36,.25);
      font-size: .85rem; color: #fcd34d;
    }
    .progress.on { display: block; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="mark">G</div>
      <div>
        <strong>GROK DEV CONSOLE</strong>
        <small>Accor · chat headless sur le dépôt hotels</small>
      </div>
    </div>
    <div class="chips">
      <span class="chip" id="chip-url">—</span>
      <span class="chip" id="chip-session">session —</span>
      <span class="chip" id="chip-status">idle</span>
    </div>
  </header>
  <main id="feed"></main>
  <footer>
    <div class="progress" id="progress">Grok réfléchit… (outils autorisés, cela peut prendre du temps)</div>
    <div class="composer">
      <textarea id="input" placeholder="Écrire à Grok… (Entrée = envoyer, Shift+Entrée = ligne)"></textarea>
      <button type="button" class="send" id="btn-send">Envoyer</button>
    </div>
    <div class="links">
      <a id="link-admin" href="http://127.0.0.1:5055" target="_blank">Admin :5055</a>
      <a id="link-user" href="http://127.0.0.1:5056" target="_blank">User :5056</a>
      <span class="chip" style="border:0">Les messages passent par <code>grok -p</code> (session web dédiée).</span>
    </div>
  </footer>
  <script>
    const feed = document.getElementById("feed");
    const input = document.getElementById("input");
    const btn = document.getElementById("btn-send");
    const progress = document.getElementById("progress");
    const chipStatus = document.getElementById("chip-status");
    const chipSession = document.getElementById("chip-session");
    const chipUrl = document.getElementById("chip-url");

    function esc(s) {
      return String(s ?? "").replace(/[&<>"']/g, c => ({
        "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
      })[c]);
    }
    function addMsg(role, content, meta, isErr) {
      const div = document.createElement("div");
      div.className = "msg " + role + (isErr ? " error" : "");
      const m = meta ? `<div class="meta">${esc(meta)}</div>` : "";
      div.innerHTML = m + esc(content);
      feed.appendChild(div);
      feed.scrollTop = feed.scrollHeight;
    }
    async function loadHistory() {
      const r = await fetch("/api/history");
      const data = await r.json();
      feed.innerHTML = "";
      (data.messages || []).forEach(m => {
        addMsg(m.role, m.content, m.ts || "", !!m.error);
      });
      if (data.session_id) chipSession.textContent = "session " + data.session_id.slice(0, 8) + "…";
    }
    async function loadStatus() {
      try {
        const r = await fetch("/api/health");
        const d = await r.json();
        chipUrl.textContent = d.public_url || d.url || location.origin;
        chipStatus.textContent = d.busy ? "busy" : "idle";
        chipStatus.className = "chip " + (d.busy ? "busy" : "ok");
        if (d.lan_urls && d.lan_urls[0]) {
          document.getElementById("link-admin").href = d.lan_urls[0].replace(/:\\d+$/, ":5055");
          document.getElementById("link-user").href = d.lan_urls[0].replace(/:\\d+$/, ":5056");
        }
      } catch (e) {
        chipStatus.textContent = "down";
      }
    }
    async function send() {
      const text = input.value.trim();
      if (!text) return;
      btn.disabled = true;
      progress.classList.add("on");
      chipStatus.textContent = "busy";
      chipStatus.className = "chip busy";
      addMsg("user", text, new Date().toISOString());
      input.value = "";
      try {
        const r = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
        const d = await r.json();
        if (!d.ok) {
          addMsg("assistant", d.error || "Erreur", "error", true);
        } else {
          addMsg("assistant", d.content, `ok · ${d.duration_s || "?"}s · ${d.session_id || ""}`.trim());
        }
      } catch (e) {
        addMsg("assistant", String(e), "network", true);
      } finally {
        btn.disabled = false;
        progress.classList.remove("on");
        chipStatus.textContent = "idle";
        chipStatus.className = "chip ok";
        loadStatus();
      }
    }
    btn.addEventListener("click", send);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    addMsg("system", "Console Grok Dev — les messages sont envoyés à Grok (headless) sur le projet Accor.");
    loadHistory();
    loadStatus();
    setInterval(loadStatus, 15000);
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    from flask import render_template_string as rts

    # asset() is injected by cache_bust context processor
    return rts(DEV_HTML)


@app.get("/api/health")
def health():
    lan = lan_ipv4_addresses()
    port = int(os.environ.get("ACCOR_DEV_PORT") or DEV_PORT_DEFAULT)
    urls = [f"http://{ip}:{port}" for ip in lan]
    return jsonify(
        {
            "ok": True,
            "app": "accor-dev-console",
            "busy": _busy,
            "last_error": _last_error,
            "session_id": _web_session_id() if STATE_DIR.exists() else None,
            "url": f"http://127.0.0.1:{port}",
            "lan_urls": urls,
            "public_url": urls[0] if urls else f"http://127.0.0.1:{port}",
            "cwd": str(PROJECT_CWD),
        }
    )


@app.get("/api/history")
def history():
    return jsonify(
        {
            "ok": True,
            "messages": _read_log(300),
            "session_id": _web_session_id(),
        }
    )


@app.get("/api/session/tail")
def session_tail():
    return jsonify({"ok": True, "updates": _read_session_tail(80)})


@app.post("/api/chat")
def chat():
    global _busy
    body = request.get_json(force=True, silent=True) or {}
    message = str(body.get("message") or body.get("prompt") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message requis"}), 400
    if _busy:
        return jsonify({"ok": False, "error": "Grok est déjà en train de répondre. Réessayez."}), 409

    _append_log("user", message)
    _busy = True
    try:
        result = _run_grok(message)
        if result.get("ok"):
            _append_log(
                "assistant",
                result["content"],
                duration_s=result.get("duration_s"),
                session_id=result.get("session_id"),
            )
            return jsonify(result)
        _append_log("assistant", result.get("error") or "error", error=True)
        return jsonify(result), 500
    finally:
        _busy = False


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Accor · Grok Dev Console (web)")
    parser.add_argument("--host", default=default_host())
    parser.add_argument("--port", type=int, default=default_port(DEV_PORT_DEFAULT))
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    os.environ["ACCOR_DEV_PORT"] = str(args.port)
    _ensure_dirs()
    print_listen_banner("Accor · Grok Dev Console (run_dev)", args.host, args.port)
    print(f"  Session web id : {_web_session_id()}")
    print(f"  Chat log       : {CHAT_LOG}")
    print()
    run_flask_app(app, host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
