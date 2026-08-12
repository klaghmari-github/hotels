"""
F0055 — composant execute_python (script Python + venv projet ou custom).

AC:
  1. Factory reconnait type execute_python (pas collision avec execute SQL)
  2. Script simple s'execute via python local par defaut (F0068)
  3. venv custom en config respecte si fourni
  4. stdout/stderr ou statut d'echec propage correctement
  5. GUI: type registry + champs script/venv (API + static)
  6. Regression: type execute SQL toujours OK

Si le code n'est pas encore merge sur la branche, les tests dependants
sont skip (pas xfail permanent) pour permettre le travail en parallele.
"""

from __future__ import annotations

import os
import stat
import textwrap
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
FEATURES = REPO / "gestion_projet" / "features.csv"

# Type YAML attendu (plan F0055) — ne pas collisionner avec "execute" SQL
TYPE_PY = "execute_python"


# ---------------------------------------------------------------------------
# Readiness / helpers
# ---------------------------------------------------------------------------


def _registry_types() -> set[str]:
    try:
        from renatus.pipeline.steps import REGISTRY

        return set(REGISTRY.keys())
    except Exception:
        return set()


def _feature_ready() -> bool:
    return TYPE_PY in _registry_types()


requires_execute_python = pytest.mark.skipif(
    not _feature_ready(),
    reason=(
        f"F0055: type {TYPE_PY!r} absent du REGISTRY "
        "(code dev pas encore pret)"
    ),
)


def _write_yaml(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(content, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def _project_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    """
    Racine projet tmp avec pipelines/ + .venv/bin/python mocke.
    Retourne (project_dir, pipe_dir, db_path).
    """
    project = tmp_path / "project"
    pipe = project / "flow"
    pipe.mkdir(parents=True)
    return project, pipe, project / "f0055.duckdb"


def _install_mock_python(
    venv_dir: Path,
    marker_file: Path,
    *,
    tag: str = "default",
    exit_code_env: str | None = None,
) -> Path:
    """
    Cree un faux interpreteur venv/bin/python (shell) qui:
      - ecrit tag + args dans marker_file
      - si -c <code> : execute le code avec le vrai python systeme
      - sinon rejoue les args avec le vrai python

    Permet de prouver quel venv a ete selectionne sans creer un vrai venv.
    """
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    py = bin_dir / "python"
    real_py = REPO / ".venv" / "bin" / "python"
    if not real_py.is_file():
        import shutil

        real_py = Path(
            shutil.which("python3") or shutil.which("python") or "/usr/bin/python3"
        )

    # Script shell portable: log tag, puis delegue au vrai python
    body = textwrap.dedent(
        f"""\
        #!/bin/sh
        MARKER={marker_file!s}
        TAG={tag!s}
        REAL={real_py!s}
        # log: TAG puis ligne args
        printf '%s\\n' "$TAG" >> "$MARKER"
        printf '%s\\n' "$*" >> "$MARKER"
        exec "$REAL" "$@"
        """
    )
    py.write_text(body, encoding="utf-8")
    py.chmod(py.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return py


def _open_pipeline(db: Path, pipe: Path):
    from renatus.pipeline.engine import ConnectionPipeline

    return ConnectionPipeline(str(db), str(pipe))


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


def test_feature_f0055_registered():
    text = FEATURES.read_text(encoding="utf-8")
    assert "F0055" in text
    assert "python" in text.lower()


# ---------------------------------------------------------------------------
# AC1 — factory / type distinct de execute SQL
# ---------------------------------------------------------------------------


@requires_execute_python
def test_factory_recognizes_execute_python():
    from renatus.pipeline.steps import (
        REGISTRY,
        ExecuteStep,
        StepFactory,
        allowed_types,
        create_step,
    )

    assert TYPE_PY in REGISTRY
    assert TYPE_PY in allowed_types()
    assert TYPE_PY in StepFactory.allowed_types()

    # Pas de collision: execute SQL reste mappe sur ExecuteStep
    assert REGISTRY["execute_sql"] is ExecuteStep
    assert REGISTRY[TYPE_PY] is not ExecuteStep

    step = create_step(
        "py1",
        {
            "type": TYPE_PY,
            "script": "print(1)",
        },
    )
    assert step.type == TYPE_PY
    assert step.id == "py1"
    assert step.relation_name() is None
    assert step.should_process(None) is True


@requires_execute_python
def test_factory_rejects_unknown_still():
    from renatus.pipeline.steps import create_step

    with pytest.raises(ValueError, match="Type invalide"):
        create_step("x", {"type": "not_a_real_type_xyz"})


@requires_execute_python
def test_tool_meta_and_catalog_include_execute_python():
    from renatus.pipeline.steps import tools_catalog
    from renatus.gui.service import GuiService

    catalog = tools_catalog()
    types = {t["type"] for t in catalog}
    assert TYPE_PY in types
    assert "execute_sql" in types  # SQL toujours present

    entry = next(t for t in catalog if t["type"] == TYPE_PY)
    fields = entry.get("fields") or []
    # zone script + venv (noms possibles: script, venv / venv_path)
    field_str = " ".join(str(f) for f in fields).lower()
    assert "script" in field_str
    assert "venv" in field_str

    gui = GuiService.tools_catalog()
    assert {t["type"] for t in gui} == types


# ---------------------------------------------------------------------------
# AC2 — execution via python local par defaut (F0068)
# ---------------------------------------------------------------------------


@requires_execute_python
def test_script_runs_with_local_python_by_default(tmp_path: Path):
    """Sans venv en config: utilise sys.executable (python local)."""
    import sys

    from renatus.pipeline.steps.python_action import resolve_venv_python

    project, pipe, db = _project_layout(tmp_path)
    # .venv projet present mais NE DOIT PAS etre utilise si venv vide
    marker_venv = project / "venv_used.log"
    _install_mock_python(project / ".venv", marker_venv, tag="PROJECT_VENV")

    out_file = project / "hello_out.txt"
    script = (
        f"from pathlib import Path\n"
        f"Path({str(out_file)!r}).write_text('hello-f0055', encoding='utf-8')\n"
    )
    _write_yaml(
        pipe / "default" / "py_hello.yaml",
        {
            "py_hello": {
                "type": TYPE_PY,
                "script": script,
            }
        },
    )

    # resolution defaut = python local
    resolved = resolve_venv_python(project, None)
    assert resolved.resolve() == Path(sys.executable).resolve()

    cp = _open_pipeline(db, pipe)
    try:
        cp.process("py_hello")
        result = (getattr(cp, "python_run_results", None) or {}).get(
            "py_hello"
        ) or {}
    finally:
        cp.close()

    assert out_file.is_file(), "script n a pas ecrit le fichier de preuve"
    assert out_file.read_text(encoding="utf-8") == "hello-f0055"
    # mock .venv non invoque
    assert not marker_venv.is_file()
    if result.get("python"):
        assert Path(result["python"]).resolve() == Path(
            sys.executable
        ).resolve()


@requires_execute_python
def test_script_runs_via_process_with_requires(tmp_path: Path):
    project, pipe, db = _project_layout(tmp_path)

    out = project / "ok.txt"
    # F0101: monocomposant py_ok.yaml
    _write_yaml(
        pipe / "default" / "py_ok.yaml",
        {
            "py_ok": {
                "type": TYPE_PY,
                "requires": [],
                "script": (
                    f"open({str(out)!r}, 'w').write('ok')\n"
                ),
            }
        },
    )
    cp = _open_pipeline(db, pipe)
    try:
        cp.process_with_requires("py_ok")
    finally:
        cp.close()
    assert out.read_text() == "ok"


# ---------------------------------------------------------------------------
# AC3 — venv custom
# ---------------------------------------------------------------------------


@requires_execute_python
def test_custom_venv_config_respected(tmp_path: Path):
    project, pipe, db = _project_layout(tmp_path)
    # .venv projet (ne doit PAS etre utilise)
    marker_proj = project / "proj.log"
    _install_mock_python(project / ".venv", marker_proj, tag="PROJECT")

    custom = project / "venvs" / "custom"
    marker_custom = project / "custom.log"
    _install_mock_python(custom, marker_custom, tag="CUSTOM")

    out = project / "from_custom.txt"
    script = f"open({str(out)!r}, 'w').write('custom')\n"

    # venv relatif au projet (chemin courant dans les configs renatus)
    cfg_venv = "venvs/custom"
    _write_yaml(
        pipe / "default" / "py_custom.yaml",
        {
            "py_custom": {
                "type": TYPE_PY,
                "script": script,
                "venv": cfg_venv,
            }
        },
    )

    cp = _open_pipeline(db, pipe)
    try:
        cp.process("py_custom")
    finally:
        cp.close()

    assert out.is_file() and out.read_text() == "custom"
    assert marker_custom.is_file(), "venv custom non utilise"
    assert "CUSTOM" in marker_custom.read_text(encoding="utf-8")
    # le venv projet ne doit pas avoir ete appele
    if marker_proj.is_file():
        assert "PROJECT" not in marker_proj.read_text(encoding="utf-8")


@requires_execute_python
def test_custom_venv_absolute_path(tmp_path: Path):
    project, pipe, db = _project_layout(tmp_path)
    custom = tmp_path / "abs_venv"
    marker = tmp_path / "abs.log"
    _install_mock_python(custom, marker, tag="ABS")

    out = project / "abs_out.txt"
    _write_yaml(
        pipe / "default" / "py_abs.yaml",
        {
            "py_abs": {
                "type": TYPE_PY,
                "script": f"open({str(out)!r}, 'w').write('abs')\n",
                "venv": str(custom),
            }
        },
    )
    cp = _open_pipeline(db, pipe)
    try:
        cp.process("py_abs")
    finally:
        cp.close()
    assert out.read_text() == "abs"
    assert marker.is_file() and "ABS" in marker.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC4 — echec propage (exit non-zero / exception)
# ---------------------------------------------------------------------------


@requires_execute_python
def test_nonzero_exit_raises(tmp_path: Path):
    project, pipe, db = _project_layout(tmp_path)
    marker = project / "m.log"
    _install_mock_python(project / ".venv", marker, tag="PV")

    _write_yaml(
        pipe / "default" / "py_fail.yaml",
        {
            "py_fail": {
                "type": TYPE_PY,
                "script": "import sys; sys.exit(2)\n",
            }
        },
    )
    cp = _open_pipeline(db, pipe)
    try:
        with pytest.raises(Exception) as excinfo:
            cp.process("py_fail")
        msg = str(excinfo.value).lower()
        # message doit evoquer echec / exit / returncode / stderr
        assert any(
            k in msg
            for k in (
                "exit",
                "return",
                "fail",
                "error",
                "code",
                "2",
                "nonzero",
                "non-zero",
                "status",
            )
        ), f"message d echec trop opaque: {excinfo.value!r}"
    finally:
        cp.close()


@requires_execute_python
def test_python_exception_propagates(tmp_path: Path):
    project, pipe, db = _project_layout(tmp_path)
    marker = project / "m2.log"
    _install_mock_python(project / ".venv", marker, tag="PV")

    _write_yaml(
        pipe / "default" / "py_exc.yaml",
        {
            "py_exc": {
                "type": TYPE_PY,
                "script": "raise RuntimeError('boom-f0055')\n",
            }
        },
    )
    cp = _open_pipeline(db, pipe)
    try:
        with pytest.raises(Exception) as excinfo:
            cp.process("py_exc")
        blob = str(excinfo.value)
        # stderr ou message devrait contenir l'erreur runtime
        assert (
            "boom-f0055" in blob
            or "RuntimeError" in blob
            or "exit" in blob.lower()
            or "return" in blob.lower()
            or "fail" in blob.lower()
        ), f"exception non propagee clairement: {blob!r}"
    finally:
        cp.close()


@requires_execute_python
def test_stdout_or_result_available_on_success(tmp_path: Path):
    """
    Succes: process ne leve pas; stdout capture sur step.last_result si expose.
    """
    project, pipe, db = _project_layout(tmp_path)
    marker = project / "m3.log"
    _install_mock_python(project / ".venv", marker, tag="PV")

    _write_yaml(
        pipe / "default" / "py_print.yaml",
        {
            "py_print": {
                "type": TYPE_PY,
                "script": "print('stdout-f0055-ok')\n",
            }
        },
    )
    cp = _open_pipeline(db, pipe)
    try:
        # ne doit pas lever
        cp.process("py_print")
        # L'implementation F0055 stocke last_result sur l'instance processée.
        # get_step() recree une instance : on re-process via create_step direct
        # pour inspecter last_result si besoin.
        from renatus.pipeline.steps import create_step

        step = create_step(
            "py_print",
            {
                "type": TYPE_PY,
                "script": "print('stdout-f0055-ok')\n",
            },
        )
        step.process(cp)
        assert hasattr(step, "last_result")
        assert step.last_result["returncode"] == 0
        assert "stdout-f0055-ok" in (step.last_result.get("stdout") or "")
    finally:
        cp.close()


# ---------------------------------------------------------------------------
# AC5 — GUI static + API
# ---------------------------------------------------------------------------


@requires_execute_python
def test_gui_static_registry_and_fields():
    from tests.helpers.static_sources import read_all_js, read_index

    js = read_all_js()
    assert TYPE_PY in js or "ExecutePython" in js
    # registry front
    assert "execute_python" in js or "ExecutePythonStepType" in js
    # champs config
    assert "script" in js
    assert "venv" in js

    html = read_index()
    # data-testid pour zone script / venv si presents dans le DOM
    # (tolere implementation via reutilisation cfg-script renommee)
    has_script_testid = (
        'data-testid="cfg-script"' in html
        or 'data-testid="cfg-python-script"' in html
        or 'id="cfg-script"' in html
        or 'id="field-script"' in html
    )
    has_venv_testid = (
        'data-testid="cfg-venv"' in html
        or 'data-testid="cfg-python-venv"' in html
        or 'id="cfg-venv"' in html
        or 'id="field-venv"' in html
    )
    # Au minimum le type doit etre dans le select
    assert (
        f'value="{TYPE_PY}"' in html
        or TYPE_PY in html
        or "execute_python" in js
    )
    # Si DOM dedie: verifier data-testid (recommandation F0013)
    if "field-script" in html or "cfg-script" in html:
        assert has_script_testid, "champ script sans data-testid"
    if "field-venv" in html or "cfg-venv" in html:
        assert has_venv_testid, "champ venv sans data-testid"


@requires_execute_python
def test_gui_create_step_api_yaml(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    project, pipe, db = _project_layout(tmp_path)
    # mock venv pour build eventuel
    _install_mock_python(project / ".venv", project / "api.log", tag="API")

    client = TestClient(create_gui_app(db, pipe))
    with client:
        # tools
        tools = client.get("/gui/tools").json()
        tool_types = {t["type"] for t in tools.get("tools", tools) if isinstance(t, dict)}
        if not tool_types and isinstance(tools, list):
            tool_types = {t["type"] for t in tools}
        assert TYPE_PY in tool_types or any(
            TYPE_PY in str(t) for t in (tools if isinstance(tools, list) else [tools])
        )

        r = client.post(
            "/gui/steps",
            json={
                "name": "py_api",
                "config": {
                    "type": TYPE_PY,
                    "script": "print(42)",
                    "venv": "",
                },
            },
        )
        assert r.status_code == 200, r.text
        # F0082: steps main sous flow/default/
        ypath = pipe / "default" / "py_api.yaml"
        assert ypath.is_file()
        body = yaml.safe_load(ypath.read_text(encoding="utf-8"))
        assert body["py_api"]["type"] == TYPE_PY
        assert "print(42)" in body["py_api"].get("script", "")

        g = client.get("/gui/graph?tab=main").json()
        nodes = {n["id"]: n for n in g["nodes"]}
        assert "py_api" in nodes
        assert nodes["py_api"]["type"] == TYPE_PY


@requires_execute_python
def test_gui_icons_mention_execute_python():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    # picto ou couleur pour le type (peut reutiliser execute)
    assert (
        TYPE_PY in js
        or "execute_python" in js
        or "ExecutePython" in js
    )


# ---------------------------------------------------------------------------
# AC6 — regression execute SQL
# ---------------------------------------------------------------------------


def test_regression_execute_sql_still_ok(tmp_path: Path):
    """Type execute SQL intact (meme si execute_python absent)."""
    from renatus.pipeline.engine import ConnectionPipeline
    from renatus.pipeline.steps import REGISTRY, create_step

    assert "execute_sql" in REGISTRY
    step = create_step("e1", {"type": "execute_sql", "sql": "SELECT 1"})
    assert step.type == "execute_sql"
    assert step.relation_name() is None

    project, pipe, db = _project_layout(tmp_path)
    _write_yaml(
        pipe / "default" / "sql_exec.yaml",
        {
            "t_dest": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": (
                    "SELECT CAST(NULL AS INTEGER) AS id "
                    "WHERE 1 = 0"
                ),
            },
            "x_ins": {
                "type": "execute_sql",
                "requires": ["t_dest"],
                "sql": "INSERT INTO t_dest SELECT 55 AS id",
            },
        },
    )
    cp = ConnectionPipeline(str(db), str(pipe))
    try:
        cp.process_with_requires("x_ins")
        rows = cp.con.execute("SELECT id FROM t_dest").fetchall()
        assert rows == [(55,)]
        assert not cp.table_exists("x_ins")
    finally:
        cp.close()


@requires_execute_python
def test_execute_and_execute_python_coexist_in_pipeline(tmp_path: Path):
    project, pipe, db = _project_layout(tmp_path)
    marker = project / "co.log"
    _install_mock_python(project / ".venv", marker, tag="CO")
    out = project / "co_out.txt"

    _write_yaml(
        pipe / "default" / "both.yaml",
        {
            "t_dest": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": (
                    "SELECT CAST(NULL AS INTEGER) AS n WHERE 1 = 0"
                ),
            },
            "x_sql": {
                "type": "execute_sql",
                "requires": ["t_dest"],
                "sql": "INSERT INTO t_dest SELECT 1 AS n",
            },
            "py_side": {
                "type": TYPE_PY,
                "requires": ["x_sql"],
                "script": f"open({str(out)!r}, 'w').write('both')\n",
            },
        },
    )
    cp = _open_pipeline(db, pipe)
    try:
        cp.process_with_requires("py_side")
        assert cp.con.execute("SELECT n FROM t_dest").fetchall() == [(1,)]
        assert out.read_text() == "both"
    finally:
        cp.close()


# ---------------------------------------------------------------------------
# build_action / hooks GUI
# ---------------------------------------------------------------------------


@requires_execute_python
def test_build_action_execute_python():
    from renatus.pipeline.steps import create_step

    step = create_step(
        "py",
        {"type": TYPE_PY, "script": "print(1)"},
    )
    # comme execute SQL: process_with_requires, pas de relation tabulaire
    assert step.build_action() in (
        "process_with_requires",
        "execute_python",
        "p_execute_python",
    )
    assert step.has_tabular_result() is False
    assert step.produces_relation() is False
    assert step.relation_name() is None
