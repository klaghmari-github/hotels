"""Chemins par défaut du package ``prepare``.

Conserve l'organisation Input/Output/Explore par étape (consignes),
tout en exposant des chemins importables depuis le code Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Racine du package prepare/ (ce fichier y vit)
PACKAGE_DIR = Path(__file__).resolve().parent
# Racine projet (parent de prepare/)
PROJECT_ROOT = PACKAGE_DIR.parent


@dataclass(frozen=True)
class PreparePaths:
    """Chemins Input/Output de chaque étape du pipeline."""

    root: Path = PACKAGE_DIR

    @property
    def rod_input(self) -> Path:
        return self.root / "RodPrep" / "Input"

    @property
    def rod_output(self) -> Path:
        return self.root / "RodPrep" / "Output"

    @property
    def meteo_input(self) -> Path:
        return self.root / "MeteoPrep" / "Input"

    @property
    def meteo_output(self) -> Path:
        return self.root / "MeteoPrep" / "Output"

    @property
    def proximity_input(self) -> Path:
        return self.root / "ProximityPrep" / "Input"

    @property
    def proximity_output(self) -> Path:
        return self.root / "ProximityPrep" / "Output"

    @property
    def sales_input(self) -> Path:
        return self.root / "SalesPrep" / "Input"

    @property
    def sales_output(self) -> Path:
        return self.root / "SalesPrep" / "Output"

    @property
    def all_input(self) -> Path:
        return self.root / "AllPrep" / "Input"

    @property
    def all_output(self) -> Path:
        return self.root / "AllPrep" / "Output"

    def as_dict(self) -> dict[str, Path]:
        return {
            "rod_input": self.rod_input,
            "rod_output": self.rod_output,
            "meteo_input": self.meteo_input,
            "meteo_output": self.meteo_output,
            "prox_input": self.proximity_input,
            "prox_output": self.proximity_output,
            "sales_input": self.sales_input,
            "sales_output": self.sales_output,
            "all_input": self.all_input,
            "all_output": self.all_output,
        }


def default_paths(root: Path | None = None) -> PreparePaths:
    """Retourne les chemins prepare (racine optionnelle pour tests)."""
    if root is None:
        return PreparePaths()
    return PreparePaths(root=Path(root))
