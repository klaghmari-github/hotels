"""
Stockage SQLite des comptes admin.

Schema minimal :
  admin_users(username PK, password_hash, created_at)

Seul le hash bcrypt est conserve — jamais le mot de passe en clair.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.auth.passwords import _DUMMY_HASH, hash_password, verify_password

# Compte initial (cree uniquement si la base est vide / utilisateur absent)
DEFAULT_ADMIN_USERNAME = "adixon"
DEFAULT_ADMIN_PASSWORD = "adixon!2026"


class AuthStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_users (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            con.commit()
        self.ensure_default_admin()

    def ensure_default_admin(self) -> None:
        """Initialise l'utilisateur adixon si absent."""
        if self.get_user(DEFAULT_ADMIN_USERNAME) is not None:
            return
        self.create_user(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)

    def get_user(self, username: str) -> dict | None:
        uname = (username or "").strip()
        if not uname:
            return None
        with self._connect() as con:
            row = con.execute(
                "SELECT username, password_hash, created_at FROM admin_users WHERE username = ?",
                (uname,),
            ).fetchone()
        if not row:
            return None
        return {
            "username": row["username"],
            "password_hash": row["password_hash"],
            "created_at": row["created_at"],
        }

    def create_user(self, username: str, password: str) -> None:
        uname = (username or "").strip()
        if not uname:
            raise ValueError("Nom d'utilisateur vide")
        if not password:
            raise ValueError("Mot de passe vide")
        ph = hash_password(password)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO admin_users (username, password_hash, created_at)
                VALUES (?, ?, ?)
                """,
                (uname, ph, now),
            )
            con.commit()

    def authenticate(self, username: str, password: str) -> str | None:
        """
        Verifie login/mot de passe.
        Retourne le username canonique en cas de succes, sinon None.
        """
        user = self.get_user(username)
        if not user:
            # comparaison factice pour limiter le timing oracle sur user inexistant
            verify_password(password or "x", _DUMMY_HASH)
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        return str(user["username"])
