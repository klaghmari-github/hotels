"""
Integration Flask : sessions admin, login/logout, garde des routes.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Flask,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)

from src.auth.store import AuthStore

SESSION_USER_KEY = "admin_user"

# Prefixe / chemins proteges (hors login)
_ADMIN_PAGE_PREFIXES = (
    "/admin",
    "/eval",
    "/compare",
    "/predict",
    "/hotels",
)
_ADMIN_API_PREFIXES = ("/api/admin",)
_PUBLIC_EXACT = frozenset(
    {
        "/admin/login",
    }
)


def _secret_key_path(paths_root: Path) -> Path:
    return paths_root / "data" / "auth" / "flask_secret.key"


def load_or_create_secret_key(paths_root: Path) -> str:
    """
    Cle de signature des cookies de session.
    Priorite : env FLASK_SECRET_KEY, sinon fichier persistant, sinon generation.
    """
    env = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
    if env:
        return env
    path = _secret_key_path(paths_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        key = path.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_urlsafe(48)
    path.write_text(key + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def is_admin_logged_in() -> bool:
    return bool(session.get(SESSION_USER_KEY))


def current_admin_user() -> str | None:
    u = session.get(SESSION_USER_KEY)
    return str(u) if u else None


def login_admin(username: str) -> None:
    session.clear()
    session[SESSION_USER_KEY] = username
    session.permanent = True


def logout_admin() -> None:
    session.clear()


def _is_safe_next(target: str | None) -> bool:
    """Evite les open-redirect (next doit rester relatif local)."""
    if not target:
        return False
    t = target.strip()
    if not t.startswith("/") or t.startswith("//"):
        return False
    parsed = urlparse(t)
    return not parsed.scheme and not parsed.netloc


def _path_requires_admin(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return False
    # login sous /admin/login deja exclu
    if path.startswith("/admin/login"):
        return False
    for p in _ADMIN_API_PREFIXES:
        if path == p or path.startswith(p + "/"):
            return True
    for p in _ADMIN_PAGE_PREFIXES:
        if path == p or path.startswith(p + "/"):
            return True
    return False


def register_auth(app: Flask, *, paths_root: Path, auth_store: AuthStore) -> AuthStore:
    """Configure secret, session, routes login/logout et garde before_request."""
    app.secret_key = load_or_create_secret_key(paths_root)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Secure=True uniquement derriere HTTPS (dev local en http)
        SESSION_COOKIE_SECURE=bool(os.environ.get("FLASK_SESSION_SECURE")),
        PERMANENT_SESSION_LIFETIME=60 * 60 * 12,  # 12 h
    )
    app.extensions["auth_store"] = auth_store

    @app.before_request
    def _guard_admin_routes():
        path = request.path or "/"
        if not _path_requires_admin(path):
            return None
        if is_admin_logged_in():
            return None
        # API → 401 JSON
        if path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Authentification admin requise"}), 401
        # Pages → login
        nxt = path
        if request.query_string:
            nxt = f"{path}?{request.query_string.decode('utf-8', errors='ignore')}"
        return redirect(url_for("admin_login", next=nxt))

    return auth_store


def auth_db_path(paths_root: Path) -> Path:
    return paths_root / "data" / "auth" / "admin_users.sqlite"
