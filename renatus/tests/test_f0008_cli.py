"""
Tests unitaires F0008 — CLI renatus (oneshot + REPL).

Bases et YAML uniquement sous tmp_path. Couvre:
  - oneshot p_table_view (lineage)
  - table_view sans lineage (erreur claire si absent)
  - process / process_with_requires (execute)
  - REPL via stdin mock
  - parsing argv et exit codes
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_pipeline(pipeline_dir: Path, content: dict) -> Path:
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    path = pipeline_dir / "cli.yaml"
    path.write_text(
        yaml.dump(content, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return pipeline_dir


def _mini_pipeline(tmp_path: Path) -> tuple[Path, Path]:
    """
    Mini pipeline pour CLI:
      t_sales  — table source
      v_sales  — vue dependante
      x_drop_rows — execute (DELETE, ou no-op safe)
    """
    pipeline_dir = tmp_path / "flow"
    db_path = tmp_path / "main.duckdb"
    _write_pipeline(
        pipeline_dir,
        {
            "t_sales": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": (
                    "SELECT * FROM (VALUES (1, 'a'), (2, 'b')) "
                    "AS t(id, label)"
                ),
            },
            "v_sales": {
                "type": "view",
                "mode": "create_or_replace",
                "requires": ["t_sales"],
                "sql": "SELECT id, label FROM t_sales ORDER BY id",
            },
            "x_drop_rows": {
                "type": "execute_sql",
                "requires": ["t_sales"],
                "sql": "DELETE FROM t_sales WHERE id = 2",
            },
        },
    )
    return db_path, pipeline_dir


# ---------------------------------------------------------------------------
# ResultPrinter
# ---------------------------------------------------------------------------


def test_result_printer_formats_relation(tmp_path: Path):
    from renatus.cli import ResultPrinter
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    out = io.StringIO()
    printer = ResultPrinter(out=out, max_rows=200)

    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=False)
    try:
        rel = cp.p_table_view("v_sales")
        printer.print_relation(rel)
    finally:
        cp.close()

    text = out.getvalue()
    assert "id" in text
    assert "label" in text
    assert "1" in text
    assert "a" in text
    assert "2 ligne" in text or "2 lignes" in text


def test_result_printer_truncates(tmp_path: Path):
    import duckdb

    from renatus.cli import ResultPrinter

    con = duckdb.connect()
    rel = con.sql(
        "SELECT i AS n FROM range(10) t(i)"
    )
    out = io.StringIO()
    printer = ResultPrinter(out=out, max_rows=3)
    printer.print_relation(rel)
    text = out.getvalue()
    assert "tronque" in text
    assert "3 lignes affichees" in text
    con.close()


# ---------------------------------------------------------------------------
# CommandRunner
# ---------------------------------------------------------------------------


def test_runner_p_table_view_creates_lineage(tmp_path: Path):
    from renatus.cli import CommandRunner
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=False)
    try:
        runner = CommandRunner(cp)
        result = runner.run(["p_table_view", "v_sales"])
        assert result.ok
        assert result.relation is not None
        rows = result.relation.fetchall()
        assert rows == [(1, "a"), (2, "b")]
        assert cp.table_exists("t_sales")
        assert cp.view_exists("v_sales")
    finally:
        cp.close()


def test_runner_table_view_missing_explicit_error(tmp_path: Path):
    from renatus.cli import CommandRunner
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=False)
    try:
        runner = CommandRunner(cp)
        with pytest.raises(LookupError) as exc_info:
            runner.run(["table_view", "v_achats"])
        msg = str(exc_info.value)
        assert "v_achats" in msg
        assert "absente" in msg.lower() or "absent" in msg.lower()
        # pas de creation lineage
        assert not cp.relation_exists("v_achats")
        assert not cp.relation_exists("t_sales")
    finally:
        cp.close()


def test_runner_table_view_existing(tmp_path: Path):
    from renatus.cli import CommandRunner
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=False)
    try:
        cp.p_table_view("v_sales")
        runner = CommandRunner(cp)
        result = runner.run(["table_view", "v_sales"])
        assert result.ok
        assert result.relation is not None
        assert result.relation.fetchall() == [(1, "a"), (2, "b")]
    finally:
        cp.close()


def test_runner_process_with_requires_execute(tmp_path: Path):
    from renatus.cli import CommandRunner
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=False)
    try:
        runner = CommandRunner(cp)
        # single token pipeline key
        result = runner.run(["x_drop_rows"])
        assert result.ok
        assert "OK" in (result.message or "")
        # t_sales creee par requires, puis ligne 2 supprimee
        rows = cp.con.execute(
            'SELECT id FROM "t_sales" ORDER BY id'
        ).fetchall()
        assert rows == [(1,)]
    finally:
        cp.close()


def test_runner_unknown_command(tmp_path: Path):
    from renatus.cli import CommandRunner
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=False)
    try:
        runner = CommandRunner(cp)
        result = runner.run(["foobar"])
        assert not result.ok
        assert "inconnue" in (result.message or "").lower()
    finally:
        cp.close()


def test_runner_help_and_quit(tmp_path: Path):
    from renatus.cli import CommandRunner
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=False)
    try:
        runner = CommandRunner(cp)
        help_r = runner.run(["help"])
        assert help_r.ok
        assert "p_table_view" in (help_r.message or "")

        quit_r = runner.run(["quit"])
        assert quit_r.ok
        assert quit_r.quit
    finally:
        cp.close()


# ---------------------------------------------------------------------------
# RenatusCli oneshot + REPL
# ---------------------------------------------------------------------------


def test_cli_oneshot_p_table_view(tmp_path: Path):
    from renatus.cli import RenatusCli, ResultPrinter

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    out = io.StringIO()
    err = io.StringIO()
    printer = ResultPrinter(out=out, err=err)

    cli = RenatusCli(
        db_path=db_path,
        pipeline_path=pipeline_dir,
        command_tokens=["p_table_view", "v_sales"],
        printer=printer,
    )
    code = cli.run()
    assert code == 0
    text = out.getvalue()
    assert "id" in text
    assert "a" in text
    assert err.getvalue() == ""


def test_cli_oneshot_table_view_missing_exit_1(tmp_path: Path):
    from renatus.cli import RenatusCli, ResultPrinter

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    out = io.StringIO()
    err = io.StringIO()
    printer = ResultPrinter(out=out, err=err)

    cli = RenatusCli(
        db_path=db_path,
        pipeline_path=pipeline_dir,
        command_tokens=["table_view", "v_achats"],
        printer=printer,
    )
    code = cli.run()
    assert code == 1
    assert "v_achats" in err.getvalue()


def test_cli_oneshot_execute_ok(tmp_path: Path):
    from renatus.cli import RenatusCli, ResultPrinter

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    out = io.StringIO()
    err = io.StringIO()
    printer = ResultPrinter(out=out, err=err)

    # d'abord creer t_sales via p_table_view
    code1 = RenatusCli(
        db_path=db_path,
        pipeline_path=pipeline_dir,
        command_tokens=["p_table_view", "t_sales"],
        printer=ResultPrinter(out=io.StringIO(), err=io.StringIO()),
    ).run()
    assert code1 == 0

    code2 = RenatusCli(
        db_path=db_path,
        pipeline_path=pipeline_dir,
        command_tokens=["x_drop_rows"],
        printer=printer,
    ).run()
    assert code2 == 0
    assert "OK" in out.getvalue()


def test_cli_repl_commands(tmp_path: Path):
    from renatus.cli import RenatusCli, ResultPrinter

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    out = io.StringIO()
    err = io.StringIO()
    printer = ResultPrinter(out=out, err=err)
    # sequence: p_table_view, table_view manquant, help, quit
    stdin = io.StringIO(
        "p_table_view v_sales\n"
        "table_view v_achats\n"
        "help\n"
        "quit\n"
    )

    code = RenatusCli(
        db_path=db_path,
        pipeline_path=pipeline_dir,
        command_tokens=[],
        printer=printer,
        stdin=stdin,
    ).run()
    assert code == 0
    combined = out.getvalue() + err.getvalue()
    assert "id" in combined or "a" in combined
    assert "v_achats" in err.getvalue()
    assert "p_table_view" in out.getvalue()  # help
    assert "Au revoir" in out.getvalue() or "quit" in combined.lower()


def test_cli_repl_eof_quits(tmp_path: Path):
    from renatus.cli import RenatusCli, ResultPrinter

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    out = io.StringIO()
    printer = ResultPrinter(out=out, err=io.StringIO())
    stdin = io.StringIO("")  # EOF immediat

    code = RenatusCli(
        db_path=db_path,
        pipeline_path=pipeline_dir,
        command_tokens=[],
        printer=printer,
        stdin=stdin,
    ).run()
    assert code == 0


# ---------------------------------------------------------------------------
# main() / argv
# ---------------------------------------------------------------------------


def test_main_oneshot_exit_0(tmp_path: Path):
    from renatus.cli import main

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    code = main(
        [
            str(db_path),
            str(pipeline_dir),
            "p_table_view",
            "v_sales",
        ]
    )
    assert code == 0


def test_main_missing_args_raises_system_exit():
    from renatus.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0


def test_parse_line_simple():
    from renatus.cli import RenatusCli

    assert RenatusCli.parse_line("  p_table_view  v_sales  ") == [
        "p_table_view",
        "v_sales",
    ]
    assert RenatusCli.parse_line("") == []
    assert RenatusCli.parse_line("   ") == []


# ---------------------------------------------------------------------------
# Complements mission testeur : multi-yaml, effets base, entrypoints
# ---------------------------------------------------------------------------


def test_multi_yaml_folder_loaded_via_cli(tmp_path: Path):
    """
    Deux fichiers YAML dans le meme dossier : CLI charge les deux
    (merge engine load_pipeline) et peut materialiser des etapes croisees.
    """
    from renatus.cli import main
    from renatus.pipeline import ConnectionPipeline

    pipeline_dir = tmp_path / "flow"
    pipeline_dir.mkdir()
    db_path = tmp_path / "multi.duckdb"

    # F0101: monocomposant = fichier stem = id
    (pipeline_dir / "t_root.yaml").write_text(
        yaml.dump(
            {
                "t_root": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 10 AS n",
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    (pipeline_dir / "v_from_root.yaml").write_text(
        yaml.dump(
            {
                "v_from_root": {
                    "type": "view",
                    "mode": "create_or_replace",
                    "requires": ["t_root"],
                    "sql": "SELECT n * 2 AS n FROM t_root",
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    (pipeline_dir / "x_bump.yaml").write_text(
        yaml.dump(
            {
                "x_bump": {
                    "type": "execute_sql",
                    "requires": ["t_root"],
                    "sql": (
                        "CREATE OR REPLACE TABLE t_root AS "
                        "SELECT n + 1 AS n FROM t_root"
                    ),
                },
            },
            default_flow_style=False,
        ),
        encoding="utf-8",
    )

    code = main(
        [str(db_path), str(pipeline_dir), "p_table_view", "v_from_root"]
    )
    assert code == 0

    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=True)
    try:
        assert "t_root" in cp.pipeline
        assert "v_from_root" in cp.pipeline
        assert "x_bump" in cp.pipeline
        assert cp.table_exists("t_root")
        assert cp.view_exists("v_from_root")
        assert cp.table_view("v_from_root").fetchall() == [(20,)]
    finally:
        cp.close()

    code2 = main([str(db_path), str(pipeline_dir), "x_bump"])
    assert code2 == 0

    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=True)
    try:
        # t_root recréee a n+1 = 11 (depuis 10)
        assert cp.con.execute('SELECT n FROM "t_root"').fetchone() == (11,)
    finally:
        cp.close()


def test_table_view_oneshot_does_not_create_missing_table(tmp_path: Path):
    """
    Via main(): table_view sur relation absente → code 1 et base sans table.
    """
    from renatus.cli import main
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    code = main([str(db_path), str(pipeline_dir), "table_view", "v_sales"])
    assert code == 1

    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=True)
    try:
        assert not cp.relation_exists("v_sales")
        assert not cp.relation_exists("t_sales")
    finally:
        cp.close()


def test_process_execute_via_main_modifies_db(tmp_path: Path):
    """Via main(): x_drop_rows modifie durablement la base."""
    from renatus.cli import main
    from renatus.pipeline import ConnectionPipeline

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    assert main([str(db_path), str(pipeline_dir), "p_table_view", "t_sales"]) == 0
    assert main([str(db_path), str(pipeline_dir), "x_drop_rows"]) == 0

    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=True)
    try:
        rows = cp.con.execute(
            'SELECT id, label FROM "t_sales" ORDER BY id'
        ).fetchall()
        assert rows == [(1, "a")]
    finally:
        cp.close()


def test_invalid_argv_incomplete_command(tmp_path: Path):
    """p_table_view sans nom → exit != 0."""
    from renatus.cli import main

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    code = main([str(db_path), str(pipeline_dir), "p_table_view"])
    assert code != 0


def test_renatus_py_shim_and_pyproject_entrypoint():
    """Livrables structurels : shim racine + entrypoint project.scripts."""
    root = Path(__file__).resolve().parents[1]
    assert (root / "renatus.py").is_file()
    assert (root / "src" / "renatus" / "cli.py").is_file()
    assert (root / "src" / "renatus" / "__main__.py").is_file()
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.scripts]" in text
    assert "renatus.cli:main" in text.replace(" ", "")


# ---------------------------------------------------------------------------
# Mission testeur : CSV + YAML, objet pipeline inconnu, subprocess, isolation
# ---------------------------------------------------------------------------


def test_oneshot_p_table_view_from_csv_mini_project(tmp_path: Path):
    """
    Mini projet YAML + CSV sous tmp_path :
    `p_table_view t_people` materialise et affiche les lignes du CSV.
    """
    from renatus.cli import main
    from renatus.pipeline import ConnectionPipeline

    project = tmp_path / "proj_csv"
    pipeline_dir = project / "flow"
    pipeline_dir.mkdir(parents=True)
    csv_path = project / "input" / "people.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("id,name\n1,alice\n2,bob\n", encoding="utf-8")

    (pipeline_dir / "people.yaml").write_text(
        yaml.dump(
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
            default_flow_style=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    db_path = project / "db.duckdb"
    # Isolation stricte : tout sous tmp_path
    assert str(db_path).startswith(str(tmp_path))
    assert str(pipeline_dir).startswith(str(tmp_path))

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        code = main(
            [str(db_path), str(pipeline_dir), "p_table_view", "t_people"]
        )

    assert code == 0, f"stderr={buf_err.getvalue()!r} stdout={buf_out.getvalue()!r}"
    combined = buf_out.getvalue() + buf_err.getvalue()
    assert "alice" in combined
    assert "bob" in combined

    cp = ConnectionPipeline(db_path, pipeline_dir, read_only=True)
    try:
        assert cp.table_exists("t_people")
        rows = sorted(cp.table_view("t_people").fetchall())
        assert rows == [(1, "alice"), (2, "bob")]
    finally:
        cp.close()


def test_unknown_pipeline_object_exits_nonzero(tmp_path: Path):
    """p_table_view / etape sur objet absent du YAML → exit != 0."""
    from renatus.cli import main

    db_path, pipeline_dir = _mini_pipeline(tmp_path)

    code_ptv = main(
        [str(db_path), str(pipeline_dir), "p_table_view", "no_such_object"]
    )
    assert code_ptv != 0

    code_step = main([str(db_path), str(pipeline_dir), "no_such_step"])
    assert code_step != 0


def test_main_missing_pipeline_dir_arg():
    """Un seul argument (db) → SystemExit != 0 (args insuffisants)."""
    from renatus.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["only_db.duckdb"])
    assert exc_info.value.code != 0


def test_subprocess_renatus_py_oneshot(tmp_path: Path):
    """
    Integration : `python renatus.py <db> <pipelines> p_table_view v_sales`.
    Verifie le lanceur racine reel (pas seulement l'API main).
    """
    import subprocess
    import sys

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    root = Path(__file__).resolve().parents[1]
    script = root / "renatus.py"

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            str(db_path),
            str(pipeline_dir),
            "p_table_view",
            "v_sales",
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    assert proc.returncode == 0, (
        f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "a" in proc.stdout or "b" in proc.stdout


def test_subprocess_renatus_py_repl_quit(tmp_path: Path):
    """REPL via renatus.py : stdin help + quit → exit 0."""
    import subprocess
    import sys

    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    root = Path(__file__).resolve().parents[1]
    script = root / "renatus.py"

    proc = subprocess.run(
        [sys.executable, str(script), str(db_path), str(pipeline_dir)],
        input="help\nquit\n",
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    assert proc.returncode == 0, (
        f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert "p_table_view" in combined or "help" in combined


def test_isolation_paths_only_tmp(tmp_path: Path):
    """Garantit que les chemins de test ne pointent pas vers data/ hotels."""
    db_path, pipeline_dir = _mini_pipeline(tmp_path)
    root = Path(__file__).resolve().parents[1]
    hotels_db = root / "data" / "duckdb"
    assert hotels_db not in db_path.parents
    assert str(tmp_path) in str(db_path.resolve())
    assert str(tmp_path) in str(pipeline_dir.resolve())
