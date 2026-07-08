"""Nettoyage des noms de colonnes pour les exports."""

from __future__ import annotations

import re
import unicodedata


def sanitize_column_name(name: str) -> str:
    """Remplace caractères spéciaux et apostrophes par des underscores."""
    text = unicodedata.normalize("NFKD", str(name))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.replace("'", "_").replace("%", "pct")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_").lower()
    return text or "col"


def sanitize_dataframe_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for col in columns:
        base = sanitize_column_name(col)
        if base in seen:
            seen[base] += 1
            base = f"{base}_{seen[base]}"
        else:
            seen[base] = 0
        result.append(base)
    return result