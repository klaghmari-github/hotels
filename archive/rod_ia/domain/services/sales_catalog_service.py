"""Catalogue TYPE / GAMME extrait du fichier ventes (pas de valeurs inventées)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


INVALID_TOKENS = frozenset({"", "#REF!", "#N/A", "N/A", "NAN", "NONE", "?"})


class SalesCatalogService:
    """Lit les catégories (TYPE) et sous-catégories (GAMME) depuis le CSV ventes."""

    def __init__(self, sales_path: Path) -> None:
        self.sales_path = Path(sales_path)

    @staticmethod
    def _is_valid_label(value: str) -> bool:
        token = str(value).strip()
        if not token:
            return False
        upper = token.upper()
        if upper in INVALID_TOKENS:
            return False
        if upper.startswith("#"):
            return False
        return True

    def load_catalog(self) -> dict:
        if not self.sales_path.exists():
            return {"types": [], "by_type": {}, "gammes": []}

        frame = pd.read_csv(
            self.sales_path,
            usecols=["TYPE", "GAMME"],
            dtype=str,
            low_memory=False,
        )
        frame = frame.dropna(subset=["TYPE", "GAMME"])
        frame["TYPE"] = frame["TYPE"].str.strip()
        frame["GAMME"] = frame["GAMME"].str.strip()
        frame = frame[
            frame["TYPE"].map(self._is_valid_label) & frame["GAMME"].map(self._is_valid_label)
        ]

        by_type: dict[str, list[str]] = {}
        for type_label, group in frame.groupby("TYPE", sort=True):
            gammes = sorted(group["GAMME"].unique().tolist())
            by_type[str(type_label)] = gammes

        gammes = sorted(frame["GAMME"].unique().tolist())
        types = sorted(by_type.keys())
        return {
            "types": types,
            "by_type": by_type,
            "gammes": gammes,
            "source": str(self.sales_path),
        }

    def save_reference(self, output_path: Path) -> dict:
        catalog = self.load_catalog()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        return catalog