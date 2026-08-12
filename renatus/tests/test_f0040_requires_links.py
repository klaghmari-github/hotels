"""
F0040 — requires = liens vers composants pipeline (id YAML + label affiche).

- requires stocke l id de step (cle YAML), pas le name de relation SQL
- UI affiche le label et ouvre la config au clic
- le type peut changer (view→table); le require reste l id
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
CSS = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


def test_feature_f0040_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0040" in features


def test_ui_requires_links_to_components():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-testid="cfg-requires-selected"' in html
    # F0066: plus de micro-hint sous Requires — label + chips suffisent
    assert "Requires" in html

    js = read_all_js()
    assert "openRequireComponent" in js
    assert "renderRequiresSelected" in js
    assert "require-link" in js
    assert "require-chip" in js
    # F0095: stocke l id YAML (pas le label) via mirror / editor
    assert (
        "setRequiresMirror" in js
        and ("_requiresEditList.push(stepId)" in js or "reqs.push(stepId)" in js)
    )
    # ouvre la config (pas seulement preview)
    assert "selectStep(stepId)" in js or "selectStep(stepId)" in js.replace(
        " ", ""
    )

    css = CSS.read_text(encoding="utf-8")
    assert "require-chip" in css
    assert "require-link" in css


def test_engine_requires_uses_step_id_not_relation_name(tmp_path: Path):
    """
    requires reference la cle YAML (id), meme si config.name (relation SQL)
    et label sont differents. Type peut etre view puis table.
    """
    from renatus.pipeline.engine import ConnectionPipeline

    db = tmp_path / "r.duckdb"
    pipe = tmp_path / "flow"
    pipe.mkdir()

    # source: id=src_step, label humain, relation SQL explicite
    (pipe / "default" / "src_step.yaml").write_text(
        yaml.dump(
            {
                "src_step": {
                    "type": "table",
                    "label": "Ma source",
                    "name": "rel_physique",  # relation SQL != id
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 7 AS n",
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    # dependant: requires l id src_step, PAS rel_physique
    (pipe / "default" / "child.yaml").write_text(
        yaml.dump(
            {
                "child": {
                    "type": "view",
                    "label": "Vue enfant",
                    # name physique explicite (distinct du label) — F0048 / F0053
                    "name": "child",
                    "mode": "create_or_replace",
                    "requires": ["src_step"],
                    "sql": "SELECT n FROM rel_physique",
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    cp = ConnectionPipeline(str(db), str(pipe))
    assert "src_step" in cp.pipeline
    assert cp.pipeline["child"]["requires"] == ["src_step"]
    assert cp.relation_name("src_step") == "rel_physique"
    assert cp.relation_name("child") == "child"

    cp.process_with_requires("child")
    rows = cp.con.sql("SELECT n FROM child").fetchall()
    assert rows == [(7,)]

    # transformer src: label + type (table reste table, SQL change)
    # require id pipeline reste src_step (pas le label ni la relation)
    (pipe / "default" / "src_step.yaml").write_text(
        yaml.dump(
            {
                "src_step": {
                    "type": "table",
                    "label": "Ma source renommee",
                    "name": "rel_physique",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 9 AS n",
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    # recharger pipeline
    cp2 = ConnectionPipeline(str(db), str(pipe))
    assert cp2.pipeline["src_step"]["label"] == "Ma source renommee"
    assert cp2.pipeline["child"]["requires"] == ["src_step"]
    cp2.process_with_requires("child")
    rows2 = cp2.con.sql("SELECT n FROM child").fetchall()
    assert rows2 == [(9,)]


def test_gui_persists_require_step_id(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "s.duckdb", pipe))
    with client:
        client.post(
            "/gui/steps",
            json={
                "name": "id_source",
                "config": {
                    "type": "table",
                    "label": "Label Source",
                    "name": "sql_rel",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS x",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "id_child",
                "config": {
                    "type": "table",
                    "label": "Label Child",
                    "mode": "create_or_replace",
                    "requires": ["id_source"],
                    "sql": "SELECT x FROM sql_rel",
                },
            },
        )
        step = client.get("/gui/step/id_child").json()
        assert step["config"]["requires"] == ["id_source"]
        # pas le label ni la relation
        assert "Label Source" not in (step["config"].get("requires") or [])
        assert "sql_rel" not in (step["config"].get("requires") or [])

        raw = yaml.safe_load(
            (pipe / "default" / "id_child.yaml").read_text(encoding="utf-8")
        )
        assert raw["id_child"]["requires"] == ["id_source"]

        # catalog expose label pour l UI
        g = client.get("/gui/graph?tab=*").json()
        by_id = {n["id"]: n for n in g.get("catalog") or g.get("nodes") or []}
        assert by_id["id_source"]["label"] == "Label Source"
