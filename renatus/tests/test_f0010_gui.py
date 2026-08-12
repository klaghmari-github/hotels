"""
Tests unitaires F0010 — GUI web renatus (TestClient + tmp_path).

Couvre (mission testeur):
  - GET / (ou /gui) retourne HTML gui
  - POST /gui/connect avec chemins tmp
  - GET /gui/graph: nodes et edges coherents avec requires
  - GET/PUT /gui/step: modification persistee (relire fichier YAML)
  - POST /gui/build: rows pour table generee
  - GET /gui/result apres build
  - erreurs 400/404
  - static assets (css/js) 200 si presentes
  - isolation hors data/duckdb hotels
  - regression F0009 API

Contrat HTTP (src/renatus/gui/app.py) :
  GET  / | /gui | /gui/
  POST /gui/connect          body: {db_path, pipeline_path, read_only?}
  GET  /gui/graph
  GET  /gui/step/{name}
  PUT  /gui/step/{name}      body: {config: {...}}
  POST /gui/build/{name}?limit=&max_rows=
  GET  /gui/result/{name}
  GET  /health
  GET  /gui/static/...

Factory : create_gui_app(db_path, pipeline_path, read_only=False)
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


def _mini_gui_project(tmp_path: Path) -> tuple[Path, Path]:
    """
    Mini projet sous tmp_path:
      input/people.csv
      pipelines/gui.yaml
    Retourne (db_path, pipeline_dir).
    """
    project = tmp_path / "proj_gui"
    pipeline_dir = project / "flow"
    input_dir = project / "input"
    input_dir.mkdir(parents=True)
    pipeline_dir.mkdir(parents=True)

    (input_dir / "people.csv").write_text(
        "id,name\n1,alice\n2,bob\n",
        encoding="utf-8",
    )

    _write_yaml(
        pipeline_dir / "gui.yaml",
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
        },
    )

    db_path = tmp_path / "gui.duckdb"
    return db_path, pipeline_dir


def _make_client(tmp_path: Path):
    """TestClient gui pre-connecte (lifespan via context manager)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from renatus.gui import create_gui_app

    db_path, pipeline_dir = _mini_gui_project(tmp_path)
    app = create_gui_app(db_path, pipeline_dir, read_only=False)
    return TestClient(app), db_path, pipeline_dir


# ---------------------------------------------------------------------------
# Package / factory
# ---------------------------------------------------------------------------


def test_gui_package_exports():
    pytest.importorskip("fastapi")
    import renatus.gui as gui

    for name in (
        "create_gui_app",
        "GuiApp",
        "GuiService",
        "YamlStepStore",
    ):
        assert hasattr(gui, name), f"export manquant: {name}"


def test_yaml_step_store_roundtrip(tmp_path: Path):
    from renatus.gui import YamlStepStore

    _, pipeline_dir = _mini_gui_project(tmp_path)
    store = YamlStepStore(pipeline_dir)
    assert store.origin_of("v_sales") is not None
    path = store.save_step(
        "v_sales",
        {
            "type": "view",
            "mode": "create_or_replace",
            "requires": ["t_sales"],
            "sql": "SELECT id FROM t_sales",
        },
    )
    # F0031: un composant = un fichier <id>.yaml
    assert path.name == "v_sales.yaml"
    reloaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert list(reloaded.keys()) == ["v_sales"]
    assert reloaded["v_sales"]["script"] == "SELECT id FROM t_sales"
    assert reloaded["v_sales"].get("label") == "v_sales"
    # les autres steps restent dans le bundle legacy (F0082: sous main/)
    bundle_path = pipeline_dir / "default" / "gui.yaml"
    if not bundle_path.is_file():
        bundle_path = pipeline_dir / "gui.yaml"
    bundle = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
    assert "v_sales" not in bundle
    assert "t_sales" in bundle
    assert "x_drop_rows" in bundle


# ---------------------------------------------------------------------------
# HTML / page gui
# ---------------------------------------------------------------------------


def test_gui_html_root_and_gui(tmp_path: Path):
    """GET / et /gui retournent du HTML gui."""
    client, _, _ = _make_client(tmp_path)
    with client:
        for path in ("/", "/gui", "/gui/"):
            r = client.get(path)
            assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
            ctype = r.headers.get("content-type", "")
            assert "html" in ctype.lower() or r.text.lstrip().lower().startswith(
                ("<!doctype", "<html")
            ), f"non-HTML sur {path}: {ctype!r}"
            body_l = r.text.lower()
            assert any(
                tok in body_l
                for tok in ("gui", "renatus", "pipeline", "graph", "step")
            ), f"HTML sans marqueur gui sur {path}"


# ---------------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------------


def test_gui_connect_tmp_paths(tmp_path: Path):
    """POST /gui/connect avec chemins tmp (reconnect)."""
    client, db_path, pipeline_dir = _make_client(tmp_path)
    with client:
        # deja connecte via factory ; reconnecte explicitement
        r = client.post(
            "/gui/connect",
            json={
                "db_path": str(db_path),
                "pipeline_path": str(pipeline_dir),
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert Path(data["db_path"]).resolve() == db_path.resolve()
        pipe = data.get("pipeline_path") or data.get("pipelines_dir")
        assert Path(pipe).resolve() == pipeline_dir.resolve()
        assert data.get("step_count", 0) >= 4


def test_gui_connect_missing_pipeline_creates_workspace(tmp_path: Path):
    """A0003: connect vers chemins absents → creation + ok."""
    client, db_path, _ = _make_client(tmp_path)
    new_pipe = tmp_path / "no_such_pipelines_xyz"
    new_db = tmp_path / "other_db" / "other.duckdb"
    with client:
        r = client.post(
            "/gui/connect",
            json={
                "db_path": str(new_db),
                "pipeline_path": str(new_pipe),
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert new_pipe.is_dir()
        assert new_db.parent.is_dir()


def test_gui_health(tmp_path: Path):
    client, db_path, pipeline_dir = _make_client(tmp_path)
    with client:
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True or data.get("status") in {"ok", "up"}
        assert Path(data["db_path"]).resolve() == db_path.resolve()
        pipe = data.get("pipeline_path") or data.get("pipelines_dir")
        assert Path(pipe).resolve() == pipeline_dir.resolve()


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def test_gui_graph_nodes_edges_requires(tmp_path: Path):
    """GET /gui/graph: nodes + edges coherents avec requires YAML."""
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.get("/gui/graph")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        nodes = data["nodes"]
        edges = data["edges"]
        ids = {n["id"] for n in nodes}
        assert {"t_sales", "v_sales", "t_people", "df_people", "x_drop_rows"} <= ids

        by_id = {n["id"]: n for n in nodes}
        assert by_id["v_sales"]["type"] == "view"
        assert by_id["t_sales"]["type"] == "table"

        # edges: from=dependance, to=etape dependante
        pairs = {(e["from"], e["to"]) for e in edges}
        assert ("t_sales", "v_sales") in pairs
        assert ("df_people", "t_people") in pairs
        assert ("t_sales", "x_drop_rows") in pairs


# ---------------------------------------------------------------------------
# GET / PUT step — persistance YAML
# ---------------------------------------------------------------------------


def test_gui_get_step(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.get("/gui/step/v_sales")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["name"] == "v_sales"
        cfg = data["config"]
        assert cfg["type"] == "view"
        assert "t_sales" in (cfg.get("requires") or [])
        assert data.get("file_origin")


def test_gui_put_step_persists_yaml(tmp_path: Path):
    """PUT /gui/step → modification visible en relisant le fichier YAML."""
    client, _, pipeline_dir = _make_client(tmp_path)
    # F0082: bundle legacy migre sous flow/default/
    yaml_file = pipeline_dir / "default" / "gui.yaml"
    if not yaml_file.is_file():
        yaml_file = pipeline_dir / "gui.yaml"
    original = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    sql_or_script = original["v_sales"].get("script") or original["v_sales"].get("sql") or ""
    assert "SELECT id" in sql_or_script

    new_sql = "SELECT id, label FROM t_sales WHERE id = 1 ORDER BY id"
    with client:
        r_get = client.get("/gui/step/v_sales")
        assert r_get.status_code == 200
        cfg = dict(r_get.json()["config"])
        cfg["script"] = new_sql

        r_put = client.put("/gui/step/v_sales", json={"config": cfg})
        assert r_put.status_code == 200, r_put.text
        body = r_put.json()
        assert body.get("ok") is True
        assert body.get("name") == "v_sales"
        assert body.get("id") == "v_sales"

        # F0031: relecture dans <id>.yaml (un composant = un fichier)
        dedicated = pipeline_dir / "default" / "v_sales.yaml"
        if not dedicated.is_file():
            dedicated = pipeline_dir / "v_sales.yaml"
        assert dedicated.is_file(), "v_sales doit etre extrait vers v_sales.yaml"
        reloaded_step = yaml.safe_load(
            dedicated.read_text(encoding="utf-8")
        )
        assert reloaded_step["v_sales"]["script"].strip() == new_sql.strip()
        # autres steps restent dans le bundle legacy
        reloaded_bundle = yaml.safe_load(
            yaml_file.read_text(encoding="utf-8")
        )
        assert "v_sales" not in reloaded_bundle
        assert "t_sales" in reloaded_bundle
        assert "x_drop_rows" in reloaded_bundle

        # GET reflet
        r2 = client.get("/gui/step/v_sales")
        assert r2.status_code == 200
        assert "id = 1" in r2.json()["config"]["script"]


def test_gui_put_step_invalid_type_400(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.put(
            "/gui/step/v_sales",
            json={"config": {"type": "not_a_real_type", "sql": "SELECT 1"}},
        )
        assert r.status_code == 400, r.text
        body = r.json()
        assert body.get("ok") is False


# ---------------------------------------------------------------------------
# Build + result
# ---------------------------------------------------------------------------


def test_gui_build_returns_rows(tmp_path: Path):
    """POST /gui/build: rows pour vue generee."""
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/gui/build/v_sales")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["action"] == "p_table_view"
        assert data["has_result"] is True
        assert data["columns"] == ["id", "label"]
        assert data["rows"] == [[1, "a"], [2, "b"]]
        assert data["row_count"] == 2
        assert data["truncated"] is False


def test_gui_result_after_build(tmp_path: Path):
    """GET /gui/result apres build → 200 avec donnees (sans re-lineage)."""
    client, _, _ = _make_client(tmp_path)
    with client:
        assert client.post("/gui/build/v_sales").status_code == 200
        r = client.get("/gui/result/v_sales")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["rows"] == [[1, "a"], [2, "b"]]


def test_gui_result_404_without_build(tmp_path: Path):
    """result sans materialisation → 404 (table_view sans lineage)."""
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.get("/gui/result/v_sales")
        assert r.status_code == 404, r.text
        body = r.json()
        assert body.get("ok") is False


def test_gui_build_csv_dataframe_chain(tmp_path: Path):
    """build t_people depuis CSV via requires df_people."""
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/gui/build/t_people")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["rows"] == [[1, "alice"], [2, "bob"]]


def test_gui_build_execute_process(tmp_path: Path):
    """build sur execute → process_with_requires (pas de rows)."""
    client, _, _ = _make_client(tmp_path)
    with client:
        # materialiser t_sales d'abord via build table
        assert client.post("/gui/build/t_sales").status_code == 200
        r = client.post("/gui/build/x_drop_rows")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["action"] == "process_with_requires"
        assert data["has_result"] is False
        # side effect: id=2 supprime
        rows = client.get("/gui/result/t_sales").json()["rows"]
        assert rows == [[1, "a"]]


def test_gui_build_max_rows(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        r = client.post("/gui/build/v_sales?max_rows=1")
        assert r.status_code == 200
        data = r.json()
        assert data["row_count"] == 1
        assert data["truncated"] is True
        assert data["rows"] == [[1, "a"]]


# ---------------------------------------------------------------------------
# Erreurs 400 / 404
# ---------------------------------------------------------------------------


def test_gui_errors_404_unknown_step(tmp_path: Path):
    client, _, _ = _make_client(tmp_path)
    with client:
        for method, path in (
            ("get", "/gui/step/no_such_step_xyz"),
            ("post", "/gui/build/no_such_step_xyz"),
            ("get", "/gui/result/no_such_step_xyz"),
        ):
            r = getattr(client, method)(path)
            assert r.status_code == 404, f"{path}: {r.status_code} {r.text}"
            body = r.json()
            assert body.get("ok") is False
            err = body.get("error") or body.get("detail") or ""
            assert "no_such" in err.lower() or "absent" in err.lower() or err


def test_gui_put_can_create_new_step(tmp_path: Path):
    """
    PUT sur step absente : le store peut creer un nouveau YAML
    (comportement actuel save_step). Accepte 200 creation ou 404 refus.
    """
    client, _, pipeline_dir = _make_client(tmp_path)
    with client:
        r = client.put(
            "/gui/step/t_brand_new",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 42 AS x",
                }
            },
        )
        assert r.status_code in {200, 404, 400}, r.text
        if r.status_code == 200:
            # build de la nouvelle step
            r2 = client.post("/gui/build/t_brand_new")
            assert r2.status_code == 200, r2.text
            assert r2.json()["rows"] == [[42]]


# ---------------------------------------------------------------------------
# Static assets
# ---------------------------------------------------------------------------


def test_gui_static_assets(tmp_path: Path):
    """
    Static css/js sous /gui/static/ : 200 si presentes.
    index.html est servi via / et /gui.
    """
    client, _, _ = _make_client(tmp_path)
    static_dir = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "renatus"
        / "gui"
        / "static"
    )
    with client:
        # index doit exister pour les tests HTML
        assert (static_dir / "index.html").is_file() or client.get("/").status_code == 200

        candidates = []
        if static_dir.is_dir():
            for p in static_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".css", ".js", ".html"}:
                    rel = p.relative_to(static_dir).as_posix()
                    candidates.append(f"/gui/static/{rel}")

        # fallback noms conventionnels
        for name in (
            "gui.css",
            "gui.js",
            "app.css",
            "app.js",
            "main.css",
            "main.js",
            "style.css",
            "index.html",
        ):
            url = f"/gui/static/{name}"
            if url not in candidates:
                candidates.append(url)

        found = []
        for path in candidates:
            r = client.get(path)
            if r.status_code == 200 and len(r.content) > 0:
                found.append(path)

        # Au minimum, si des css/js sont dans static/, ils doivent repondre 200
        css_js_on_disk = [
            p
            for p in static_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".css", ".js"}
        ]
        if css_js_on_disk:
            for p in css_js_on_disk:
                rel = p.relative_to(static_dir).as_posix()
                r = client.get(f"/gui/static/{rel}")
                assert r.status_code == 200, f"/gui/static/{rel}"
                assert len(r.content) > 0
        elif not found:
            # HTML peut etre inline-only : skip soft pour css/js
            r_html = client.get("/")
            if r_html.status_code == 200 and (
                ".css" in r_html.text or ".js" in r_html.text or "<style" in r_html.text
            ):
                return
            pytest.skip("Aucun asset css/js (gui HTML inline acceptable)")


# ---------------------------------------------------------------------------
# Isolation + regression F0009
# ---------------------------------------------------------------------------


def test_gui_isolation_tmp_only(tmp_path: Path):
    client, db_path, pipeline_dir = _make_client(tmp_path)
    with client:
        data = client.get("/health").json()
        db = data["db_path"]
        pipe = data.get("pipeline_path") or data.get("pipelines_dir")
        tmp_res = str(tmp_path.resolve())
        assert tmp_res in db
        assert "data/duckdb" not in db.replace("\\", "/")
        assert tmp_res in pipe
        assert Path(db).resolve() == db_path.resolve()
        assert Path(pipe).resolve() == pipeline_dir.resolve()


def test_f0009_api_regression(tmp_path: Path):
    """API F0009 create_app reste fonctionnelle (regression)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from renatus.api import create_app

    db_path, pipeline_dir = _mini_gui_project(tmp_path / "f0009_reg")
    app = create_app(db_path, pipeline_dir, read_only=False)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        r = client.post("/p_table_view/v_sales")
        assert r.status_code == 200
        assert r.json()["rows"] == [[1, "a"], [2, "b"]]
        assert client.get("/table_view/no_such_relation_xyz").status_code == 404


def test_server_parser_renatus_gui(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from renatus.gui.server import build_parser, main

    parser = build_parser()
    args = parser.parse_args(
        ["/tmp/db.duckdb", "/tmp/pipes", "--host", "0.0.0.0", "--port", "9002"]
    )
    # F0026: args positionnels regroupes dans paths
    assert list(args.paths) == ["/tmp/db.duckdb", "/tmp/pipes"]
    assert args.port == 9002

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)

    # --no-create sur chemin absent → code 1
    missing = tmp_path / "absent_pipes_f0010"
    code = main(
        [
            str(tmp_path / "sub" / "no_db.duckdb"),
            str(missing),
            "--no-create",
        ]
    )
    assert code == 1

    # creation par defaut
    code = main([str(tmp_path / "created.duckdb"), str(tmp_path / "pipes_ok")])
    assert code == 0
    assert (tmp_path / "pipes_ok").is_dir()


def test_entrypoint_renatus_gui_declared():
    """Console script renatus-gui declare dans pyproject."""
    import importlib.metadata

    eps = importlib.metadata.entry_points()
    if hasattr(eps, "select"):
        scripts = eps.select(group="console_scripts")
    else:
        scripts = eps.get("console_scripts", [])
    names = {ep.name for ep in scripts}
    # editable install peut ne pas etre a jour : verifier aussi pyproject
    if "renatus-gui" not in names:
        pyproject = (
            Path(__file__).resolve().parents[1] / "pyproject.toml"
        )
        text = pyproject.read_text(encoding="utf-8")
        assert "renatus-gui" in text
        assert "renatus.gui.server:main" in text
    else:
        assert "renatus-gui" in names
