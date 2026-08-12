"""
Tests unitaires F0009 — API HTTP renatus (FastAPI TestClient).

Bases et YAML uniquement sous tmp_path. Couvre (mission testeur):
  - demarrage app avec db + pipeline tmp
  - GET /health
  - liste des etapes pipeline (GET /pipeline/steps)
  - POST /p_table_view/{name} rows + lineage
  - GET /table_view/{name} 404 sans creer
  - GET /table_view apres p_table_view → 200
  - POST process (side effect)
  - POST process_with_requires
  - GET /relations/{name}/exists
  - erreurs 404 objet inconnu, 400/422 args invalides
  - max_rows query param (limit fonctionnel)
  - p_iteration sequential
  - isolation hors data/ hotels

Contrat HTTP actuel (src/renatus/api/app.py) :
  GET  /health
  GET  /pipeline/steps
  GET  /relations/{name}/exists
  POST /p_table_view/{name}?max_rows=
  GET  /p_table_view/{name}
  GET  /table_view/{name}?max_rows=
  POST /process/{name}
  POST /process_with_requires/{name}
  POST /p_iteration/{name}

Factory : create_app(db_path, pipelines_dir, read_only=False)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_yaml(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(content, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def _mini_api_project(tmp_path: Path) -> tuple[Path, Path]:
    """
    Mini projet API sous tmp_path:
      input/people.csv
      pipelines/api.yaml (tables, vue, execute, iteration)
    Retourne (db_path, pipeline_dir).
    """
    project = tmp_path / "proj_api"
    pipeline_dir = project / "flow"
    input_dir = project / "input"
    input_dir.mkdir(parents=True)
    pipeline_dir.mkdir(parents=True)

    (input_dir / "people.csv").write_text(
        "id,name\n1,alice\n2,bob\n",
        encoding="utf-8",
    )

    _write_yaml(
        pipeline_dir / "api.yaml",
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

    db_path = tmp_path / "api.duckdb"
    return db_path, pipeline_dir


def _make_client(tmp_path: Path):
    """TestClient + fixture (lifespan via context manager)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from renatus.api import create_app

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    app = create_app(db_path, pipeline_dir, read_only=False)
    return TestClient(app), db_path, pipeline_dir


# ---------------------------------------------------------------------------
# Service / runtime (sans HTTP)
# ---------------------------------------------------------------------------


def test_runtime_health_and_list_steps(tmp_path: Path):
    from renatus.api import RenatusApiRuntime

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    with RenatusApiRuntime(db_path, pipeline_dir) as runtime:
        svc = runtime.service
        health = svc.health(
            runtime.db_path, runtime.pipelines_dir, runtime.read_only
        )
        assert health.status == "ok"
        assert health.step_count >= 5
        assert Path(health.db_path).resolve() == db_path.resolve()

        listing = svc.list_steps()
        names = {s.name for s in listing.steps}
        assert {"t_sales", "v_sales", "x_drop_rows", "i_run"} <= names
        by_name = {s.name: s for s in listing.steps}
        assert by_name["v_sales"].type == "view"
        assert by_name["v_sales"].requires == ["t_sales"]
        assert listing.count == len(listing.steps)


def test_service_relation_and_p_table_view(tmp_path: Path):
    from renatus.api import RenatusApiRuntime

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    with RenatusApiRuntime(db_path, pipeline_dir) as runtime:
        svc = runtime.service
        info = svc.relation_exists("t_sales")
        assert info.exists is False

        body = svc.p_table_view("v_sales")
        assert body.ok is True
        assert body.columns == ["id", "label"]
        assert body.rows == [[1, "a"], [2, "b"]]
        assert body.row_count == 2
        assert body.truncated is False
        assert svc.relation_exists("t_sales").exists is True
        # kind si expose
        kind = getattr(svc.relation_exists("t_sales"), "kind", None)
        if kind is not None:
            assert kind == "table"

        limited = svc.p_table_view("v_sales", max_rows=1)
        assert limited.row_count == 1
        assert limited.truncated is True
        assert limited.rows == [[1, "a"]]


def test_service_csv_dataframe_lineage(tmp_path: Path):
    from renatus.api import RenatusApiRuntime

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    with RenatusApiRuntime(db_path, pipeline_dir) as runtime:
        body = runtime.service.p_table_view("t_people")
        assert body.rows == [[1, "alice"], [2, "bob"]]
        assert "name" in body.columns


def test_service_table_view_missing_then_ok(tmp_path: Path):
    from renatus.api import RenatusApiRuntime

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    with RenatusApiRuntime(db_path, pipeline_dir) as runtime:
        svc = runtime.service
        with pytest.raises(LookupError) as exc_info:
            svc.table_view("v_sales")
        assert "v_sales" in str(exc_info.value)
        assert svc.relation_exists("t_sales").exists is False

        svc.p_table_view("v_sales")
        body = svc.table_view("v_sales")
        assert body.rows == [[1, "a"], [2, "b"]]


def test_service_process_and_process_with_requires(tmp_path: Path):
    from renatus.api import RenatusApiRuntime

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    with RenatusApiRuntime(db_path, pipeline_dir) as runtime:
        svc = runtime.service
        msg = svc.process("t_sales")
        assert msg.ok is True
        assert msg.action == "process"
        assert svc.relation_exists("t_sales").exists is True
        assert svc.relation_exists("v_sales").exists is False

        svc.process("t_sales")
        msg2 = svc.process_with_requires("x_drop_rows")
        assert msg2.ok is True
        assert msg2.action == "process_with_requires"
        rows = svc.table_view("t_sales").rows
        assert rows == [[1, "a"]]


def test_service_p_iteration(tmp_path: Path):
    from renatus.api import RenatusApiRuntime

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    with RenatusApiRuntime(db_path, pipeline_dir) as runtime:
        msg = runtime.service.p_iteration("i_run")
        assert msg.ok is True
        assert msg.action == "p_iteration"
        body = runtime.service.p_table_view("t_results")
        assert sorted(r[0] for r in body.rows) == [1, 2, 3]


def test_service_errors(tmp_path: Path):
    from renatus.api import RenatusApiRuntime

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    with RenatusApiRuntime(db_path, pipeline_dir) as runtime:
        svc = runtime.service
        with pytest.raises(KeyError):
            svc.p_table_view("no_such_step")
        with pytest.raises(TypeError):
            svc.p_table_view("x_drop_rows")
        with pytest.raises(TypeError):
            svc.p_iteration("v_sales")
        with pytest.raises(ValueError):
            svc.p_table_view("v_sales", max_rows=0)


def test_serializer_truncates():
    from renatus.api import RelationSerializer

    class _FakeRel:
        description = [("n",)]

        def limit(self, n: int):
            return self

        def fetchall(self):
            return [(i,) for i in range(5)]

    ser = RelationSerializer(max_rows=3)
    body = ser.serialize(_FakeRel(), "t", max_rows=2)
    assert body.row_count == 2
    assert body.truncated is True
    assert body.rows == [[0], [1]]


def test_service_isolation_tmp_only(tmp_path: Path):
    from renatus.api import RenatusApiRuntime

    db_path, pipeline_dir = _mini_api_project(tmp_path)
    with RenatusApiRuntime(db_path, pipeline_dir) as runtime:
        health = runtime.service.health(
            runtime.db_path, runtime.pipelines_dir, False
        )
        assert str(tmp_path.resolve()) in health.db_path
        assert "data/duckdb" not in health.db_path.replace("\\", "/")
        pipe = getattr(health, "pipelines_dir", None) or getattr(
            health, "pipeline_path", ""
        )
        assert str(tmp_path.resolve()) in str(pipe)


# ---------------------------------------------------------------------------
# HTTP FastAPI (TestClient)
# ---------------------------------------------------------------------------


def test_http_health(tmp_path: Path):
    client, db_path, pipeline_dir = _make_client(tmp_path)
    with client:
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in {"ok", "up"}
        assert data["step_count"] >= 5
        assert data["read_only"] is False
        assert Path(data["db_path"]).resolve() == db_path.resolve()
        pipe = data.get("pipelines_dir") or data.get("pipeline_path")
        assert Path(pipe).resolve() == pipeline_dir.resolve()


def test_http_pipeline_steps(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.get("/pipeline/steps")
        assert r.status_code == 200
        data = r.json()
        names = {s["name"] for s in data["steps"]}
        assert {"t_sales", "v_sales", "x_drop_rows", "i_run"} <= names
        by_name = {s["name"]: s for s in data["steps"]}
        assert by_name["v_sales"]["type"] == "view"
        assert by_name["v_sales"]["requires"] == ["t_sales"]
        assert data["count"] == len(data["steps"])


def test_http_p_table_view_lineage_and_rows(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/p_table_view/v_sales")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["columns"] == ["id", "label"]
        assert data["rows"] == [[1, "a"], [2, "b"]]
        assert data["row_count"] == 2
        assert data["truncated"] is False

        # lineage materialise
        ex = client.get("/relations/t_sales/exists").json()
        assert ex["exists"] is True
        assert ex["name"] == "t_sales"
        assert client.get("/relations/v_sales/exists").json()["exists"] is True


def test_http_p_table_view_get_equivalent(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.get("/p_table_view/v_sales")
        assert r.status_code == 200
        assert r.json()["rows"] == [[1, "a"], [2, "b"]]


def test_http_p_table_view_csv(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/p_table_view/t_people")
        assert r.status_code == 200
        assert r.json()["rows"] == [[1, "alice"], [2, "bob"]]


def test_http_p_table_view_max_rows(tmp_path: Path):
    """Query param max_rows (= limit mission)."""
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/p_table_view/v_sales?max_rows=1")
        assert r.status_code == 200
        data = r.json()
        assert data["row_count"] == 1
        assert data["truncated"] is True
        assert data["rows"] == [[1, "a"]]


def test_http_table_view_404_without_create(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.get("/table_view/v_sales")
        assert r.status_code == 404
        body = r.json()
        assert body.get("ok") is False
        err = body.get("error") or body.get("detail") or ""
        assert "v_sales" in err
        # pas de lineage
        assert (
            client.get("/relations/t_sales/exists").json()["exists"] is False
        )
        assert (
            client.get("/relations/v_sales/exists").json()["exists"] is False
        )


def test_http_table_view_after_p_table_view(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        assert client.post("/p_table_view/v_sales").status_code == 200
        r = client.get("/table_view/v_sales")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["rows"] == [[1, "a"], [2, "b"]]


def test_http_table_view_max_rows(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        client.post("/p_table_view/v_sales")
        r = client.get("/table_view/v_sales?max_rows=1")
        assert r.status_code == 200
        data = r.json()
        assert data["row_count"] == 1
        assert data["truncated"] is True


def test_http_process_side_effect(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/process/t_sales")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["action"] == "process"
        assert (
            client.get("/relations/t_sales/exists").json()["exists"] is True
        )
        assert (
            client.get("/relations/v_sales/exists").json()["exists"] is False
        )

        # side effect DELETE
        r2 = client.post("/process/x_drop_rows")
        assert r2.status_code == 200
        rows = client.get("/table_view/t_sales").json()["rows"]
        assert rows == [[1, "a"]]


def test_http_process_with_requires(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/process_with_requires/x_drop_rows")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["action"] == "process_with_requires"
        rows = client.get("/table_view/t_sales").json()["rows"]
        assert rows == [[1, "a"]]


def test_http_p_iteration(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/p_iteration/i_run")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["action"] == "p_iteration"
        rows = client.post("/p_table_view/t_results").json()["rows"]
        assert sorted(row[0] for row in rows) == [1, 2, 3]


def test_http_relations_exists(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.get("/relations/v_sales/exists")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "v_sales"
        assert data["exists"] is False

        client.post("/p_table_view/v_sales")
        r2 = client.get("/relations/v_sales/exists")
        assert r2.json()["exists"] is True


def test_http_error_unknown_404(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        for method, path in (
            ("post", "/p_table_view/no_such_step"),
            ("post", "/process/no_such_step"),
            ("post", "/process_with_requires/no_such_step"),
            ("post", "/p_iteration/no_such_step"),
        ):
            r = getattr(client, method)(path)
            assert r.status_code == 404, path
            body = r.json()
            assert body.get("ok") is False
            err = body.get("error") or body.get("detail") or ""
            assert "no_such_step" in err


def test_http_error_invalid_type_400(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/p_table_view/x_drop_rows")
        assert r.status_code == 400
        body = r.json()
        assert body.get("ok") is False
        err = body.get("error") or body.get("detail") or ""
        assert (
            "x_drop_rows" in err
            or "table" in err.lower()
            or "vue" in err.lower()
        )

        r2 = client.post("/p_iteration/t_sales")
        assert r2.status_code == 400


def test_http_max_rows_invalid_rejected(tmp_path: Path):
    """max_rows < 1 : FastAPI Query(ge=1) → 422 (ou 400 service)."""
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/p_table_view/v_sales?max_rows=0")
        assert r.status_code in {400, 422}
        r2 = client.get("/table_view/v_sales?max_rows=-3")
        assert r2.status_code in {400, 422}
        r3 = client.post("/p_table_view/v_sales?max_rows=abc")
        assert r3.status_code in {400, 422}


def test_http_isolation_never_hotels_db(tmp_path: Path):
    client, db_path, pipeline_dir = _make_client(tmp_path)
    with client:
        data = client.get("/health").json()
        db = data["db_path"]
        pipe = data.get("pipelines_dir") or data.get("pipeline_path")
        tmp_res = str(tmp_path.resolve())
        assert tmp_res in db
        assert "data/duckdb" not in db.replace("\\", "/")
        assert tmp_res in pipe
        assert Path(db).resolve() == db_path.resolve()
        assert Path(pipe).resolve() == pipeline_dir.resolve()


# ---------------------------------------------------------------------------
# Package / entrypoints
# ---------------------------------------------------------------------------


def test_api_package_exports():
    pytest.importorskip("fastapi")
    import renatus.api as api

    for name in (
        "create_app",
        "create_app_from_paths",
        "RenatusApiApp",
        "RenatusApiRuntime",
        "PipelineApiService",
        "RelationSerializer",
        "HealthResponse",
        "RelationDataResponse",
    ):
        assert hasattr(api, name), f"export manquant: {name}"


def test_server_parser_and_missing_pipeline(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from renatus.api.server import build_parser, main

    parser = build_parser()
    args = parser.parse_args(
        ["/tmp/db.duckdb", "/tmp/pipes", "--host", "0.0.0.0", "--port", "9001"]
    )
    assert args.db_path == "/tmp/db.duckdb"
    assert args.pipeline_path == "/tmp/pipes"
    assert args.host == "0.0.0.0"
    assert args.port == 9001

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)

    missing = tmp_path / "no_such_pipeline_dir_xyz_f0009"
    code = main(
        [str(tmp_path / "sub" / "no_db.duckdb"), str(missing), "--no-create"]
    )
    assert code == 1

    code = main([str(tmp_path / "api.duckdb"), str(tmp_path / "api_pipes")])
    assert code == 0
    assert (tmp_path / "api_pipes").is_dir()


def test_create_app_from_paths(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from renatus.api import create_app_from_paths

    db_path, pipeline_dir = _mini_api_project(tmp_path / "from_paths")
    app = create_app_from_paths(
        str(db_path),
        str(pipeline_dir),
        read_only=False,
    )
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        r = client.post("/p_table_view/v_sales")
        assert r.status_code == 200
        assert r.json()["rows"] == [[1, "a"], [2, "b"]]


def test_entrypoint_renatus_api_declared():
    import importlib.metadata

    eps = importlib.metadata.entry_points()
    if hasattr(eps, "select"):
        scripts = eps.select(group="console_scripts")
    else:
        scripts = eps.get("console_scripts", [])
    names = {ep.name for ep in scripts}
    assert "renatus-api" in names
