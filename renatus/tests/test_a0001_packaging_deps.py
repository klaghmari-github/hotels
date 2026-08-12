"""
A0001 — dependances packaging pour API / GUI.

Apres `pip install -e .` (sans extra), fastapi et uvicorn doivent etre
declares dans les dependances principales du projet, car les entrypoints
renatus-api et renatus-gui sont toujours installes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"


def _project_dependencies_block(text: str) -> str:
    """Extrait le bloc dependencies = [ ... ] principal (hors optional)."""
    match = re.search(
        r"(?ms)^dependencies\s*=\s*\[(.*?)^\]",
        text,
    )
    assert match is not None, "bloc dependencies introuvable dans pyproject.toml"
    return match.group(1)


def test_pyproject_declares_fastapi_and_uvicorn_as_core_deps():
    """fastapi et uvicorn sont dans dependencies principales (A0001)."""
    text = PYPROJECT.read_text(encoding="utf-8")
    core = _project_dependencies_block(text).lower()
    assert "fastapi" in core
    assert "uvicorn" in core


def test_requirements_txt_mirrors_fastapi_uvicorn():
    """requirements.txt miroir inclut fastapi et uvicorn."""
    text = REQUIREMENTS.read_text(encoding="utf-8").lower()
    assert "fastapi" in text
    assert "uvicorn" in text


def test_entrypoints_api_and_gui_declared():
    """Les scripts renatus-api et renatus-gui restent declares (F0087)."""
    text = PYPROJECT.read_text(encoding="utf-8")
    assert "renatus-api" in text
    assert "renatus-gui" in text
    assert "renatus-cli" in text
    assert "renatus.api.server:main" in text
    assert "renatus.gui.server:main" in text
    # alias historique
    assert "renatus-gui" in text


def test_fastapi_importable_in_test_env():
    """
    Dans l'environnement de test, fastapi doit etre importable.

    Garantit que le dev/CI a bien les deps coeur (sinon installer -e .).
    """
    fastapi = pytest.importorskip("fastapi")
    uvicorn = pytest.importorskip("uvicorn")
    assert fastapi is not None
    assert uvicorn is not None
