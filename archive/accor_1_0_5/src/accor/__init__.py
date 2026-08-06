"""
Package Accor ROD.

Contient :
  - le studio admin (Flask, datasets Excel, modèles XGBoost)
  - le simulateur directeur (parcours ROD SIMPLY / LIBERTY / CONNECTED)

Les chemins data / models / static / templates sont résolus depuis l’emplacement
du package, pas depuis le répertoire de lancement. Voir data_io pour le détail.
"""

from __future__ import annotations

from archive.accor_1_0_5.src.accor.data_io import (
    DATA_DIR,
    MODELS_DIR,
    PACKAGE_DIR,
    PROJECT_ROOT,
    STATIC_DIR,
    TEMPLATES_DIR,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "PACKAGE_DIR",
    "PROJECT_ROOT",
    "DATA_DIR",
    "MODELS_DIR",
    "STATIC_DIR",
    "TEMPLATES_DIR",
]
