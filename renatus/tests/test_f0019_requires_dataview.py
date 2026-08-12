"""
F0019 — requires multi-select graphique + apercu prerequis dans DataView.

Verifie:
  - HTML: picker requires (pas seulement champ texte virgule)
  - JS: renderRequiresPicker, previewRequireSource, sync YAML
  - API: preview d une source prerequis apres build
  - PUT step avec requires persiste le YAML
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
STYLE = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


def test_feature_f0019_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0019" in features
    assert "requires" in features.lower() or "prerequis" in features.lower()


def test_html_has_requires_picker():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-testid="cfg-requires-picker"' in html
    assert 'id="cfg-requires-picker"' in html
    assert 'data-testid="cfg-requires"' in html
    # champs iteration avec testids
    assert 'data-testid="cfg-target"' in html
    assert 'data-testid="cfg-scenarios"' in html
    assert 'data-testid="cfg-step-view"' in html
    assert 'data-testid="cfg-script"' in html
    # F0021: label court "Requires" (plus de texte "Sources prerequis")
    assert "Requires" in html or "requires" in html


def test_js_requires_picker_and_preview():
    js = read_all_js()
    assert "renderRequiresPicker" in js
    assert "previewRequireSource" in js
    assert "getSelectedRequires" in js
    assert "dataviewIsPrereq" in js
    # F0095: toggle via addRequire/removeRequire (compat onRequireCheckboxChange)
    assert "onRequireCheckboxChange" in js or "addRequire" in js
    assert "asPrereq" in js
    # sync YAML utilise getSelectedRequires (ou registry StepType F0053)
    assert (
        "config.requires = getSelectedRequires()" in js
        or "readSelectedRequires" in js
        or "requires = getSelectedRequires()" in js
    )
    # ajout require = apercu DataView
    assert "previewRequireSource" in js
    # F0095: edition via dialog zone
    assert "openRequiresEditor" in js


def test_css_requires_picker_styles():
    css = STYLE.read_text(encoding="utf-8")
    assert ".requires-picker" in css or ".requires-selected" in css
    assert "require-chip" in css
    assert "dataview-source" in css or ".is-preview" in css or "requires-edit" in css


def _write_pipeline(path: Path, steps: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(steps, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


def test_put_requires_syncs_yaml(tmp_path: Path):
    """Sauvegarder requires via API → YAML contient la liste."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    _write_pipeline(
        pipe / "default" / "pipeline.yaml",
        {
            "df_src": {"type": "dataframe", "file": "input/a.csv"},
            "t_out": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": "SELECT 1 AS id",
            },
        },
    )
    client = TestClient(create_gui_app(tmp_path / "x.duckdb", pipe))
    with client:
        r = client.put(
            "/gui/step/t_out",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": ["df_src"],
                    "sql": "SELECT * FROM df_src",
                }
            },
        )
        assert r.status_code == 200, r.text
        # YamlStepStore peut ecrire t_out.yaml ou mettre a jour le fichier d origine
        raw_files = list(pipe.rglob("*.yaml"))
        found = False
        for f in raw_files:
            cfg_all = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            if "t_out" in cfg_all:
                assert cfg_all["t_out"]["requires"] == ["df_src"]
                assert cfg_all["t_out"]["type"] == "table"
                found = True
            elif cfg_all.get("type") == "table" and "requires" in cfg_all:
                # format step-only (un seul objet)
                assert cfg_all["requires"] == ["df_src"]
                found = True
        assert found, f"t_out non trouve dans {raw_files}"

        g = client.get("/gui/graph").json()
        edges = g.get("edges") or []
        assert any(
            (e.get("from") or e.get("from_")) == "df_src" and e.get("to") == "t_out"
            for e in edges
        )


def test_preview_prereq_after_build(tmp_path: Path):
    """Build dataframe puis preview: DataView renvoie des lignes (prerequis)."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    inp = tmp_path / "input"
    inp.mkdir()
    (inp / "people.csv").write_text(
        "id,name\n1,Alice\n2,Bob\n3,Cara\n", encoding="utf-8"
    )
    _write_pipeline(
        pipe / "default" / "pipeline.yaml",
        {
            "df_people": {
                "type": "dataframe",
                "file": "input/people.csv",
            },
            "t_people": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": ["df_people"],
                "sql": "SELECT * FROM df_people",
            },
        },
    )
    client = TestClient(create_gui_app(tmp_path / "p.duckdb", pipe))
    with client:
        # Build la source prerequis seule
        b = client.post("/gui/build/df_people?limit=3")
        assert b.status_code == 200, b.text
        prev = client.get("/gui/preview/df_people?limit=3")
        assert prev.status_code == 200, prev.text
        data = prev.json()
        assert data.get("exists") is True or data.get("row_count", 0) >= 1
        assert len(data.get("columns") or []) >= 1
        assert len(data.get("rows") or []) >= 1
        assert len(data["rows"]) <= 3

        # Build table dependante + preview table
        b2 = client.post("/gui/build/t_people?limit=3")
        assert b2.status_code == 200, b2.text
        prev2 = client.get("/gui/preview/t_people?limit=3")
        assert prev2.status_code == 200
        assert (prev2.json().get("row_count") or 0) >= 1


def test_graph_lists_all_candidates_for_requires(tmp_path: Path):
    """Le graphe expose les noeuds utilisables comme sources prerequis."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    _write_pipeline(
        pipe / "default" / "pipeline.yaml",
        {
            "df_a": {"type": "dataframe", "file": "input/x.csv"},
            "t_b": {
                "type": "table",
                "mode": "create_or_replace",
                "requires": [],
                "sql": "SELECT 1 AS id",
            },
            "v_c": {
                "type": "view",
                "mode": "create_or_replace",
                "requires": [],
                "sql": "SELECT 1 AS id",
            },
            "x_d": {
                "type": "execute_sql",
                "requires": [],
                "sql": "SELECT 1",
            },
        },
    )

    client = TestClient(create_gui_app(tmp_path / "g.duckdb", pipe))
    with client:
        g = client.get("/gui/graph").json()
        ids = {n["id"] for n in g["nodes"]}
        assert ids == {"df_a", "t_b", "v_c", "x_d"}
        types = {n["id"]: n["type"] for n in g["nodes"]}
        assert types["df_a"] == "dataframe"
        assert types["t_b"] == "table"


def test_iteration_default_and_fields_in_tools():
    """Les tools gui exposent les champs iteration / requires."""
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app
    from pathlib import Path as P

    # tools endpoint ne depend pas du workspace reel pour la liste
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = P(td)
        pipe = root / "flow"
        pipe.mkdir()
        client = TestClient(create_gui_app(root / "d.duckdb", pipe))
        with client:
            tools = client.get("/gui/tools").json()["tools"]
            by_type = {t["type"]: t for t in tools}
            for typ in ("table", "view", "execute_sql", "iterate"):
                assert typ in by_type
                fields = by_type[typ].get("fields") or []
                assert "requires" in fields
            assert "target" in by_type["iterate"]["fields"]
            assert "scenarios" in by_type["iterate"]["fields"]


def test_html_served_contains_picker(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "s.duckdb", pipe))
    with client:
        html = client.get("/").text
        assert "cfg-requires-picker" in html
        assert "cfg-requires" in html
