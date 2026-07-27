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


def run_flask_app(app: Any, *, host: str, port: int, debug: bool = False) -> None:
    """
    Lance Flask en mode développement.

    ``threaded=True`` pour plusieurs clients réseau.
    Pas de reloader multi-process si host public (évite doubles binds).
    """
    use_reloader = bool(debug) and host in ("127.0.0.1", "localhost")
    app.run(
        host=host,
        port=port,
        debug=debug,
        threaded=True,
        use_reloader=use_reloader,
    )
