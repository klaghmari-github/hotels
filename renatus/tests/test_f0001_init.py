"""
Tests smoke F0001 — initialisation du package renatus.

Cible : imports, exports API publique, Paths configurable,
ouverture ConnectionPipeline sur YAML minimal, materialisation legere.
Pas de couverture fonctionnelle complete (reserve a F0002).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_import_package():
    """Import renatus et renatus.pipeline reussit."""
    import renatus
    import renatus.pipeline

    assert renatus is not None
    assert renatus.pipeline is not None
    assert hasattr(renatus, "__version__")
    assert renatus.__version__


def test_public_api_exports():
    """ConnectionPipeline, PipelineFactory, Paths, DependencyTree accessibles."""
    import renatus
    from renatus import (
        ConnectionPipeline,
        DependencyTree,
        Paths,
        PipelineFactory,
    )
    from renatus.pipeline import (
        ConnectionPipeline as CP2,
        DependencyTree as DT2,
        Paths as Paths2,
        PipelineFactory as PF2,
    )

    for name, obj in (
        ("ConnectionPipeline", ConnectionPipeline),
        ("PipelineFactory", PipelineFactory),
        ("Paths", Paths),
        ("DependencyTree", DependencyTree),
    ):
        assert obj is not None, name
        assert callable(obj) or isinstance(obj, type), name
        assert getattr(renatus, name) is obj

    # Reexports pipeline coherents
    assert CP2 is ConnectionPipeline
    assert PF2 is PipelineFactory
    assert Paths2 is Paths
    assert DT2 is DependencyTree


def test_paths_configurable(project_root: Path):
    """
    Paths(root=tmpdir) est generique (A0002) : pas d'arborescence hotels.

    ensure() ne cree plus de dossiers vides metier (sim_v1, models ml, ...).
    ensure_db_parent() cree uniquement le parent de la base DuckDB.
    """
    from renatus.pipeline import Paths

    paths = Paths(root=project_root).ensure()

    assert paths.root == project_root.resolve()
    assert paths.main_db == paths.duckdb_main / "main.duckdb"
    assert paths.pipeline == paths.root / "pipeline"

    # ensure() ne materialise pas data/ ni models/
    assert not paths.data.is_dir()
    assert not paths.models.is_dir()
    assert not hasattr(paths, "output_sim_v1")
    assert not hasattr(paths, "output_sim_v2")
    assert not hasattr(paths, "models_catboost")

    db = paths.ensure_db_parent()
    assert db == paths.main_db
    assert paths.duckdb_main.is_dir()
    # toujours pas d'arborescence hotels
    assert not (paths.output / "sim_v1").exists()
    assert not (paths.models / "catboost").exists()


def test_connection_pipeline_empty_yaml(
    temp_db_path: Path,
    empty_pipeline_dir: Path,
):
    """
    Ouvrir ConnectionPipeline sur DuckDB temporaire + YAML minimal sans crash.

    Note: un dossier pipeline sans aucun YAML leve FileNotFoundError
    (moteur actuel). On utilise un fichier empty.yaml = {}.
    """
    from renatus.pipeline import ConnectionPipeline

    pipeline = ConnectionPipeline(
        temp_db_path,
        empty_pipeline_dir,
        read_only=False,
    )
    try:
        assert pipeline.pipeline == {}
        assert pipeline.tree is not None
        # Connexion DuckDB utilisable
        row = pipeline.con.execute("SELECT 1 AS x").fetchone()
        assert row is not None
        assert row[0] == 1
    finally:
        pipeline.close()


def test_connection_pipeline_materialize_simple_table(
    temp_db_path: Path,
    simple_table_pipeline_dir: Path,
):
    """
    YAML minimal table SQL : materialisation via process_with_requires / p_table_view.
    """
    from renatus.pipeline import ConnectionPipeline

    pipeline = ConnectionPipeline(
        temp_db_path,
        simple_table_pipeline_dir,
        read_only=False,
    )
    try:
        assert "t_simple" in pipeline.pipeline
        assert pipeline.pipeline["t_simple"]["type"] == "table"

        pipeline.process_with_requires("t_simple")
        assert pipeline.table_exists("t_simple")

        rows = pipeline.con.execute(
            'SELECT id, label FROM "t_simple"'
        ).fetchall()
        assert rows == [(1, "ok")]

        # p_table_view reutilise la table deja creee (mode create_if_not_exists)
        rel = pipeline.p_table_view("t_simple")
        df = rel.df()
        assert list(df.columns) == ["id", "label"]
        assert len(df) == 1
        assert int(df.iloc[0]["id"]) == 1
        assert str(df.iloc[0]["label"]) == "ok"
    finally:
        pipeline.close()


def test_pipeline_factory_open_with_tmp_paths(
    project_root: Path,
    empty_pipeline_dir: Path,
):
    """
    PipelineFactory.open() avec Paths(root=tmpdir) et pipeline YAML minimal.

    On pointe paths.pipeline vers le dossier YAML de test pour rester
    isole de tout YAML metier du depot.
    """
    from renatus.pipeline import Paths, PipelineFactory

    paths = Paths(root=project_root).ensure()
    # Remplace le dossier pipeline par le YAML minimal de test
    if paths.pipeline.exists() and not paths.pipeline.is_symlink():
        # s'assurer que le dossier existe puis y copier empty.yaml
        paths.pipeline.mkdir(parents=True, exist_ok=True)
    else:
        paths.pipeline.mkdir(parents=True, exist_ok=True)
    (paths.pipeline / "empty.yaml").write_text("{}\n", encoding="utf-8")

    factory = PipelineFactory(paths=paths)
    conn = factory.open(read_only=False, rebuild=True)
    try:
        assert conn.pipeline == {}
        assert conn.con is not None
    finally:
        conn.close()
