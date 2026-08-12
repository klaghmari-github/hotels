"""F0078 — type execute renomme execute_sql + alias legacy."""

from __future__ import annotations
from pathlib import Path

import yaml

from renatus.pipeline.steps import REGISTRY, create_step, normalize_step_type, tools_catalog

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0078_registered():
    assert "F0078" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_registry_execute_sql_not_bare_execute():
    assert "execute_sql" in REGISTRY
    assert "execute" not in REGISTRY


def test_legacy_execute_alias():
    assert normalize_step_type("execute") == "execute_sql"
    step = create_step("e", {"type": "execute", "script": "SELECT 1"})
    assert step.type == "execute_sql"
    assert step.to_config()["type"] == "execute_sql"


def test_tools_catalog_has_execute_sql():
    types = [t["type"] for t in tools_catalog()]
    assert "execute_sql" in types
    assert "execute" not in types


def test_load_legacy_yaml(tmp_path: Path):
    from renatus.pipeline import ConnectionPipeline

    pipe = tmp_path / "p"
    pipe.mkdir()
    (pipe / "default" / "x.yaml").write_text(
        "x:\n  type: execute\n  requires: []\n  script: SELECT 1\n",
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(tmp_path / "d.duckdb"), pipe)
    try:
        assert cp.pipeline["x"]["type"] == "execute_sql"
        cp.process("x")
    finally:
        cp.close()


def test_ui_execute_sql():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert "execute_sql" in html
    js = read_all_js()
    assert 'super("execute_sql")' in js or "execute_sql" in js
    assert "palette-" in js
