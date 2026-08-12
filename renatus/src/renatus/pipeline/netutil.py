"""
Utilitaires reseau pour demarrage serveur (gui / api).
"""

from __future__ import annotations

import socket


def is_port_free(host: str, port: int) -> bool:
    """True si on peut bind le couple host:port en TCP."""
    family = socket.AF_INET6 if ":" in host and host != "localhost" else socket.AF_INET
    # 127.0.0.1 et 0.0.0.0 -> IPv4
    if host in {"0.0.0.0", "127.0.0.1", "localhost"}:
        family = socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host if host != "localhost" else "127.0.0.1", port))
        return True
    except OSError:
        return False


def find_free_port(
    host: str,
    preferred: int,
    *,
    max_tries: int = 50,
    strict: bool = False,
) -> int:
    """
    Retourne preferred s'il est libre, sinon le prochain port libre.

    Si strict=True (utilisateur a force un port occupe), leve OSError.
    """
    if is_port_free(host, preferred):
        return preferred
    if strict:
        raise OSError(
            f"Adresse deja utilisee: {host}:{preferred}. "
            f"Liberer le port ou choisir --port <autre>."
        )
    for offset in range(1, max_tries + 1):
        candidate = preferred + offset
        if candidate > 65535:
            break
        if is_port_free(host, candidate):
            return candidate
    raise OSError(
        f"Aucun port libre entre {preferred} et "
        f"{min(preferred + max_tries, 65535)} sur {host}."
    )
