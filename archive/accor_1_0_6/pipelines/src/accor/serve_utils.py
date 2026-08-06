"""
Utilitaires de lancement serveur (admin / user).

* Host par défaut ``0.0.0.0`` : accessible sur le LAN (et internet si
  ports ouverts / tunnel).
* Variables d'environnement : ``ACCOR_HOST``, ``ACCOR_PORT``.
* Affiche les URL locales + LAN au démarrage.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any


def default_host() -> str:
    """Host d'écoute : ACCOR_HOST ou 0.0.0.0 (toutes les interfaces)."""
    return (os.environ.get("ACCOR_HOST") or "0.0.0.0").strip() or "0.0.0.0"


def default_port(fallback: int) -> int:
    raw = (os.environ.get("ACCOR_PORT") or "").strip()
    if raw.isdigit():
        return int(raw)
    return int(fallback)


def lan_ipv4_addresses() -> list[str]:
    """Adresses IPv4 non-loopback de la machine (meilleur effort)."""
    found: set[str] = set()
    try:
        # Connexion UDP « fantôme » pour résoudre l'IP sortante
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                found.add(ip)
        finally:
            s.close()
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                found.add(ip)
    except OSError:
        pass
    return sorted(found)


def print_listen_banner(app_name: str, host: str, port: int) -> None:
    """Message de démarrage avec URL locale + LAN."""
    print(f"\n{'═' * 56}")
    print(f"  {app_name}")
    print(f"{'═' * 56}")
    if host in ("0.0.0.0", "::", ""):
        print(f"  Local   →  http://127.0.0.1:{port}")
        lan = lan_ipv4_addresses()
        if lan:
            for ip in lan:
                print(f"  Réseau  →  http://{ip}:{port}")
        else:
            print(f"  Réseau  →  http://<IP-de-ce-PC>:{port}")
        print(f"  Bind    →  {host}:{port} (toutes interfaces)")
    else:
        print(f"  URL     →  http://{host}:{port}")
    print()
    print("  Accès public (Internet) : ouvrir le port routeur/firewall")
    print("  ou lancer un tunnel, ex. :")
    print(f"    cloudflared tunnel --url http://127.0.0.1:{port}")
    print(f"    ngrok http {port}")
    print(f"{'═' * 56}\n")


class PrefixMiddleware:
    """
    Monte l'app Flask sous un préfixe d'URL (ex. ``/studio``).

    Apache reverse-proxy envoie ``/studio/...`` ; on expose SCRIPT_NAME
    et on réduit PATH_INFO pour les routes Flask internes.
    """

    def __init__(self, wsgi_app: Any, prefix: str) -> None:
        self.wsgi_app = wsgi_app
        p = (prefix or "").strip().rstrip("/")
        self.prefix = p if p.startswith("/") else (f"/{p}" if p else "")

    def __call__(self, environ: dict, start_response: Any) -> Any:
        if not self.prefix:
            return self.wsgi_app(environ, start_response)
        path = environ.get("PATH_INFO") or ""
        if path == self.prefix or path.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = (
                (environ.get("SCRIPT_NAME") or "").rstrip("/") + self.prefix
            )
            rest = path[len(self.prefix) :] or "/"
            environ["PATH_INFO"] = rest
        return self.wsgi_app(environ, start_response)


def apply_url_prefix(app: Any) -> None:
    """Applique ``ACCOR_URL_PREFIX`` sur ``app.wsgi_app`` si défini."""
    import os

    prefix = (os.environ.get("ACCOR_URL_PREFIX") or "").strip()
    if not prefix:
        return
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    prefix = prefix.rstrip("/") or prefix
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on", "y")


def _python_watch_files() -> list[str]:
    """Fichiers .py à surveiller pour le reloader Flask."""
    try:
        from archive.accor_1_0_6.pipelines.src.accor.data_io import PROJECT_ROOT

        root = PROJECT_ROOT
    except Exception:
        root = Path(__file__).resolve().parents[2]
    files: list[str] = []
    src = root / "src" / "accor"
    if src.is_dir():
        for p in src.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            files.append(str(p))
    for name in ("run_admin.py", "run_user.py", "run_dev.py"):
        cand = root / name
        if cand.is_file():
            files.append(str(cand))
    return files


def run_flask_app(app: Any, *, host: str, port: int, debug: bool = False) -> None:
    """
    Lance Flask.

    * ``threaded=True`` pour plusieurs clients réseau.
    * Rechargement auto du process si le **backend** (.py) change :
      - actif par défaut en local (``ACCOR_RELOAD=1``)
      - désactiver en prod PM2 : ``ACCOR_RELOAD=0`` (PM2 watch à la place)
    * Templates HTML : ``TEMPLATES_AUTO_RELOAD`` (via cache_bust) sans restart.
    * Respecte ``ACCOR_URL_PREFIX`` (ex. admin derrière ``/studio``).
    """
    # Prod derrière PM2 : ACCOR_RELOAD=0. Local : reloader par défaut.
    use_reloader = bool(debug) or _env_flag("ACCOR_RELOAD", default=True)
    apply_url_prefix(app)

    extra = _python_watch_files() if use_reloader else None
    if use_reloader:
        print(
            f"  Reload  →  ON (ACCOR_RELOAD) · {len(extra or [])} fichiers .py surveillés"
        )
    else:
        print(
            "  Reload  →  OFF (ACCOR_RELOAD=0) — redémarrage géré par PM2 / process manager"
        )

    app.run(
        host=host,
        port=port,
        debug=debug,
        threaded=True,
        use_reloader=use_reloader,
        extra_files=extra or None,
    )
