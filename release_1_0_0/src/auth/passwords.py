"""
Hachage des mots de passe admin.

Technique : bcrypt (OWASP / industrie) — sel unique par hash,
cout adaptatif, jamais de stockage du mot de passe en clair.
"""

from __future__ import annotations

import bcrypt

# cout bcrypt (2^12 rounds) — equilibre secu / latence login
_BCRYPT_ROUNDS = 12

# Hash factice pour egaliser le temps de reponse si l'utilisateur n'existe pas
_DUMMY_HASH = bcrypt.hashpw(b"__timing_pad__", bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode(
    "ascii"
)


def hash_password(password: str) -> str:
    """Retourne le hash bcrypt (utf-8) a stocker en base."""
    if not password:
        raise ValueError("Mot de passe vide")
    raw = password.encode("utf-8")
    # bcrypt tronque a 72 octets
    if len(raw) > 72:
        raw = raw[:72]
    hashed = bcrypt.hashpw(raw, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return hashed.decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Compare le mot de passe fourni au hash stocke (timing-safe via bcrypt)."""
    if not password or not password_hash:
        return False
    try:
        raw = password.encode("utf-8")
        if len(raw) > 72:
            raw = raw[:72]
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
