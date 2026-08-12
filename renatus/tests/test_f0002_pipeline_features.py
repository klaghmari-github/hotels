"""
Tests unitaires F0002 — fonctionnalites pipeline.

Chaque cas cible une feature pipeline (dataframe, chaine table/vue,
requires recursifs, execute, iteration sequential, modes create).
Bases et fichiers uniquement sous tmp_path : jamais la base hotels.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def _write_pipeline(pipeline_dir: Path, name: str, content: dict) -> Path:
    """
    Ecrit le pipeline (1 fichier <id>.yaml par step — F0101).

    ``name`` conserve pour compat d appel ; ignore pour le nom de fichier
    si content a plusieurs cles, un fichier par cle.
    """
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    if not content:
        (pipeline_dir / f"{name}.yaml").write_text("{}\n", encoding="utf-8")
        return pipeline_dir
    for sid, cfg in content.items():
        path = pipeline_dir / f"{sid}.yaml"
        path.write_text(
            yaml.dump(
                {sid: cfg},
                default_flow_style=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
    return pipeline_dir


def _open_pipeline(db_path: Path, pipeline_dir: Path):
    from renatus.pipeline import ConnectionPipeline

    return ConnectionPipeline(db_path, pipeline_dir, read_only=False)


# ---------------------------------------------------------------------------
# 1. dataframe depuis fichier CSV
# ---------------------------------------------------------------------------


def test_dataframe_from_csv_then_table_select(tmp_path: Path):
    """
    YAML type dataframe + CSV, puis table SELECT * FROM df.
    Verifie le contenu materialise.
    """
    project = tmp_path / "proj_df"
    pipeline_dir = project / "pipeline"
    csv_path = project / "input" / "people.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text(
        "id,name\n1,alice\n2,bob\n",
        encoding="utf-8",
    )

    # project_dir = parent du dossier pipeline => project
    _write_pipeline(
        pipeline_dir,
        "df",
        {
            "df_people": {
                "type": "dataframe",
                "file": "input/people.csv",
            },
            "t_people": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_people"],
                "sql": "SELECT * FROM df_people ORDER BY id",
            },
        },
    )

    db_path = tmp_path / "df.duckdb"
    pipeline = _open_pipeline(db_path, pipeline_dir)
    try:
        rel = pipeline.p_table_view("t_people")
        rows = rel.fetchall()
        cols = [d[0] for d in rel.description]

        assert "id" in cols
        assert "name" in cols
        assert rows == [(1, "alice"), (2, "bob")]
        assert pipeline.table_exists("t_people")
    finally:
        pipeline.close()


# ---------------------------------------------------------------------------
# 2. table/vue a partir d'une autre table/vue (chaine)
# ---------------------------------------------------------------------------


def test_table_view_chain_t_a_v_b_t_c(tmp_path: Path):
    """Chaine t_a -> v_b -> t_c : chaque etape lit la precedente."""
    pipeline_dir = tmp_path / "pipeline_chain"
    _write_pipeline(
        pipeline_dir,
        "chain",
        {
            "t_a": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": (
                    "SELECT * FROM (VALUES (10, 'x'), (20, 'y')) "
                    "AS t(id, label)"
                ),
            },
            "v_b": {
                "type": "view",
                "mode": "create_or_replace",
                "requires": ["t_a"],
                "sql": "SELECT id, label FROM t_a WHERE id >= 10",
            },
            "t_c": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["v_b"],
                "sql": "SELECT id, label FROM v_b ORDER BY id",
            },
        },
    )

    db_path = tmp_path / "chain.duckdb"
    pipeline = _open_pipeline(db_path, pipeline_dir)
    try:
        pipeline.p_table_view("t_c")
        rows = pipeline.con.execute(
            'SELECT id, label FROM "t_c" ORDER BY id'
        ).fetchall()
        assert rows == [(10, "x"), (20, "y")]
        assert pipeline.table_exists("t_a")
        assert pipeline.view_exists("v_b")
        assert pipeline.table_exists("t_c")
    finally:
        pipeline.close()


# ---------------------------------------------------------------------------
# 3. dependances non encore creees (creation recursive)
# ---------------------------------------------------------------------------


def test_p_table_view_creates_missing_ancestors(tmp_path: Path):
    """
    p_table_view sur une table dont les requires n'existent pas encore :
    le moteur cree recursivement les ancetres.
    """
    pipeline_dir = tmp_path / "pipeline_deps"
    _write_pipeline(
        pipeline_dir,
        "deps",
        {
            "t_root": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": "SELECT 42 AS value",
            },
            "v_mid": {
                "type": "view",
                "mode": "create_or_replace",
                "requires": ["t_root"],
                "sql": "SELECT value * 2 AS value FROM t_root",
            },
            "t_leaf": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["v_mid"],
                "sql": "SELECT value FROM v_mid",
            },
        },
    )

    db_path = tmp_path / "deps.duckdb"
    pipeline = _open_pipeline(db_path, pipeline_dir)
    try:
        # Aucune relation en base avant l'appel
        assert not pipeline.relation_exists("t_root")
        assert not pipeline.relation_exists("v_mid")
        assert not pipeline.relation_exists("t_leaf")

        pipeline.p_table_view("t_leaf")

        assert pipeline.table_exists("t_root")
        assert pipeline.view_exists("v_mid")
        assert pipeline.table_exists("t_leaf")
        row = pipeline.con.execute(
            'SELECT value FROM "t_leaf"'
        ).fetchone()
        assert row is not None
        assert row[0] == 84
    finally:
        pipeline.close()


# ---------------------------------------------------------------------------
# 4. execute SQL sans creation de table/vue
# ---------------------------------------------------------------------------


def test_execute_sql_side_effect_no_relation(tmp_path: Path):
    """
    Type execute : effet de bord (INSERT) sans que l'objet execute
    soit une relation (table/vue).
    """
    pipeline_dir = tmp_path / "pipeline_exec"
    _write_pipeline(
        pipeline_dir,
        "exec",
        {
            "t_dest": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": (
                    "SELECT CAST(NULL AS INTEGER) AS id, "
                    "CAST(NULL AS VARCHAR) AS label "
                    "WHERE 1 = 0"
                ),
            },
            "x_insert_row": {
                "type": "execute_sql",
                "requires": ["t_dest"],
                "sql": (
                    "INSERT INTO t_dest "
                    "SELECT 7 AS id, 'side' AS label"
                ),
            },
        },
    )

    db_path = tmp_path / "exec.duckdb"
    pipeline = _open_pipeline(db_path, pipeline_dir)
    try:
        pipeline.process_with_requires("x_insert_row")

        # Effet de bord visible
        rows = pipeline.con.execute(
            'SELECT id, label FROM "t_dest"'
        ).fetchall()
        assert rows == [(7, "side")]

        # L'objet execute n'est pas une table ni une vue
        assert not pipeline.table_exists("x_insert_row")
        assert not pipeline.view_exists("x_insert_row")
        assert not pipeline.relation_exists("x_insert_row")

        # p_table_view refuse un execute
        with pytest.raises(TypeError):
            pipeline.p_table_view("x_insert_row")
    finally:
        pipeline.close()


# ---------------------------------------------------------------------------
# 5. iteration sequential
# ---------------------------------------------------------------------------


def test_iteration_sequential_one_row_per_scenario(tmp_path: Path):
    """
    Iteration sequential : scenarios -> step_view -> target execute INSERT.
    La table resultat contient une ligne par scenario.
    """
    pipeline_dir = tmp_path / "pipeline_iter"
    # step_view est cree dynamiquement par replace_step_view (TEMP VIEW) :
    # il ne doit PAS figurer dans requires (sinon validation pipeline echoue).
    _write_pipeline(
        pipeline_dir,
        "iter",
        {
            "t_scenarios": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": (
                    "SELECT * FROM (VALUES (1), (2), (3)) "
                    "AS t(scenario_id)"
                ),
            },
            "t_results": {
                "type": "table",
                "mode": "create_if_not_exists",
                "requires": [],
                "sql": (
                    "SELECT CAST(NULL AS INTEGER) AS scenario_id "
                    "WHERE 1 = 0"
                ),
            },
            "x_insert": {
                "type": "execute_sql",
                "requires": ["t_results"],
                "sql": (
                    "INSERT INTO t_results "
                    "SELECT scenario_id FROM v_step"
                ),
            },
            "i_run": {
                "type": "iteration",
                "execution": "sequential",
                "requires": ["t_scenarios", "t_results"],
                "scenarios": "t_scenarios",
                "step_view": "v_step",
                "target": "x_insert",
                "order_by": ["scenario_id"],
            },
        },
    )

    db_path = tmp_path / "iter.duckdb"
    pipeline = _open_pipeline(db_path, pipeline_dir)
    try:
        pipeline.p_iteration("i_run")

        rows = pipeline.con.execute(
            'SELECT scenario_id FROM "t_results" ORDER BY scenario_id'
        ).fetchall()
        assert rows == [(1,), (2,), (3,)]

        # L'iteration n'est pas une relation
        assert not pipeline.relation_exists("i_run")
    finally:
        pipeline.close()


# ---------------------------------------------------------------------------
# 6. Bonus : create_or_replace vs create_if_not_exists
# ---------------------------------------------------------------------------


def test_create_if_not_exists_skips_when_present(tmp_path: Path):
    """
    mode create_if_not_exists : si la table existe deja, pas de recreation.
    Les lignes ajoutees manuellement restent.
    """
    pipeline_dir = tmp_path / "pipeline_cin"
    _write_pipeline(
        pipeline_dir,
        "cin",
        {
            "t_cin": {
                "type": "table",
                "mode": "create_if_not_exists",
                "requires": [],
                "sql": "SELECT 1 AS id",
            },
        },
    )

    db_path = tmp_path / "cin.duckdb"
    pipeline = _open_pipeline(db_path, pipeline_dir)
    try:
        pipeline.process_with_requires("t_cin")
        assert pipeline.con.execute(
            'SELECT id FROM "t_cin"'
        ).fetchall() == [(1,)]

        # Mutation hors pipeline
        pipeline.con.execute(
            'INSERT INTO "t_cin" SELECT 99 AS id'
        )
        assert pipeline.con.execute(
            'SELECT COUNT(*) FROM "t_cin"'
        ).fetchone()[0] == 2

        # Reprocess : ne doit pas ecraser
        pipeline.process_with_requires("t_cin")
        rows = pipeline.con.execute(
            'SELECT id FROM "t_cin" ORDER BY id'
        ).fetchall()
        assert rows == [(1,), (99,)]
    finally:
        pipeline.close()


def test_create_or_replace_rebuilds_table(tmp_path: Path):
    """
    mode create_or_replace : recree la table a chaque process.
    Les lignes ajoutees manuellement disparaissent.
    """
    pipeline_dir = tmp_path / "pipeline_cor"
    _write_pipeline(
        pipeline_dir,
        "cor",
        {
            "t_cor": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": "SELECT 1 AS id",
            },
        },
    )

    db_path = tmp_path / "cor.duckdb"
    pipeline = _open_pipeline(db_path, pipeline_dir)
    try:
        pipeline.process_with_requires("t_cor")
        pipeline.con.execute(
            'INSERT INTO "t_cor" SELECT 99 AS id'
        )
        assert pipeline.con.execute(
            'SELECT COUNT(*) FROM "t_cor"'
        ).fetchone()[0] == 2

        # Reprocess : recreation depuis le SQL pipeline
        pipeline.process_with_requires("t_cor")
        rows = pipeline.con.execute(
            'SELECT id FROM "t_cor" ORDER BY id'
        ).fetchall()
        assert rows == [(1,)]
    finally:
        pipeline.close()
