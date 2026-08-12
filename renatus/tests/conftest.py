"""
Fixtures pytest pour tests smoke renatus.

Toutes les bases et YAML sont sous tmp_path : jamais la vraie base hotels.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Racine projet temporaire (data/, pipeline/, models/ a creer via Paths)."""
    return tmp_path / "project"


@pytest.fixture
def paths(project_root: Path):
    """Paths configure sur un root temporaire et assure les dossiers de travail."""
    from renatus.pipeline import Paths

    return Paths(root=project_root).ensure()


@pytest.fixture
def empty_pipeline_dir(tmp_path: Path) -> Path:
    """
    Dossier pipeline vide (zero YAML).

    Depuis A0003 / gui bootstrap, un repertoire vide est autorise
    (pipeline = {}). On garde un YAML vide optionnel pour tests legacy
    qui preferent un fichier present.
    """
    pipeline_dir = tmp_path / "pipeline_empty"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    return pipeline_dir


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Chemin d'une base DuckDB temporaire (fichier non cree a l'avance)."""
    db_dir = tmp_path / "duckdb"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "test.duckdb"


@pytest.fixture
def simple_table_pipeline_dir(tmp_path: Path) -> Path:
    """
    Pipeline YAML minimal : une table SQL sans dependance.

    t_simple = SELECT 1 AS id, 'ok' AS label
    """
    pipeline_dir = tmp_path / "pipeline_simple"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    # F0101: monocomposant → fichier <id>.yaml (stem = id)
    (pipeline_dir / "t_simple.yaml").write_text(
        """
t_simple:
  type: table
  mode: create_if_not_exists
  requires: []
  sql: |-
    SELECT 1 AS id, 'ok' AS label
""".lstrip(),
        encoding="utf-8",
    )
    return pipeline_dir
