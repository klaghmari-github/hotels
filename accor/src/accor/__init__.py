"""
Package Accor ROD — data studio admin + simulateur user.

Donnees runtime : <project>/data, <project>/models
Assets web     : <project>/static, <project>/templates
"""

from __future__ import annotations

from accor.data_io import (
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
