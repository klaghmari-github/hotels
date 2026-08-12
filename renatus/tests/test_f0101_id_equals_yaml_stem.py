"""F0101 — id composant = shortname du fichier YAML (stem)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from renatus.gui.yaml_store import YamlStepStore
from renatus.pipeline.engine import ConnectionPipeline

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0101_registered():
    assert "F0101" in (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )


def test_normalize_step_id_strips_path_and_extension():
    n = YamlStepStore.normalize_step_id
    assert n("df_sales") == "df_sales"
    assert n("main/df_sales") == "df_sales"
    assert n("a/b/c/view_1.yaml") == "view_1"
    assert n("zone_x.yml") == "zone_x"
    assert n("  etl/sub/t1.YAML  ") == "t1"
    assert YamlStepStore.step_id_from_yaml_path(
        Path("/flow/default/my_step.yaml")
    ) == "my_step"
    try:
        n("")
        assert False
    except ValueError:
        pass
    try:
        n("..")
        assert False
    except ValueError:
        pass


def test_create_and_put_use_stem_filename(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "x.duckdb", pipe))
    with client:
        r = client.post(
            "/gui/steps",
            json={
                "name": "main/weird_id.yaml",  # normalise → weird_id
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                },
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == "weird_id" or body["name"] == "weird_id"
        # fichier = weird_id.yaml sous main/
        found = list(pipe.rglob("weird_id.yaml"))
        assert len(found) == 1
        raw = yaml.safe_load(found[0].read_text(encoding="utf-8"))
        assert list(raw.keys()) == ["weird_id"]
        # get_step par id stem
        st = client.get("/gui/step/weird_id").json()
        assert st["id"] == "weird_id" or st["name"] == "weird_id"


def test_load_heals_yaml_key_to_match_stem(tmp_path: Path):
    """Fichier t_sales.yaml avec cle YAML 'wrong_key' → id t_sales apres load."""
    pipe = tmp_path / "flow"
    main = pipe / "default"
    main.mkdir(parents=True)
    f = main / "t_sales.yaml"
    f.write_text(
        yaml.dump(
            {
                "wrong_key": {
                    "type": "table",
                    "label": "Sales",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    # zone main
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(tmp_path / "h.duckdb"), str(pipe))
    assert "t_sales" in cp.pipeline
    assert "wrong_key" not in cp.pipeline
    # fichier reecrit avec la bonne cle
    raw = yaml.safe_load(f.read_text(encoding="utf-8"))
    assert list(raw.keys()) == ["t_sales"]
    assert raw["t_sales"]["type"] == "table"


def test_store_default_path_is_id_yaml(tmp_path: Path):
    pipe = tmp_path / "flow"
    pipe.mkdir()
    store = YamlStepStore(pipe)
    p = store.default_path_for("my_df", tab="default", step_type="dataframe")
    assert p.name == "my_df.yaml"
    assert "default" in p.parts
    p2 = store.default_path_for(
        "sub/folder/z1.yaml", tab="default", step_type="zone"
    )
    assert p2.name == "z1.yaml"
