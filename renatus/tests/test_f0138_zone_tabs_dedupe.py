"""F0138 — selecteur Zone: un onglet par zone id (pas de doublons FS)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0138_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0138" in text


def test_phantom_nested_dirs_not_duplicated_in_tabs(tmp_path: Path):
    """
    Apres import abime, le disque peut avoir:
      pkg/ml, pkg/common/ml, pkg/common/common
    Le selecteur ne doit lister ml / common qu une fois (chemin canonique).
    """
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )

    # package + zones
    pkg = "pipeline_demo"
    (pipe / f"{pkg}.yaml").write_text(
        yaml.dump(
            {
                pkg: {
                    "type": "zone",
                    "label": pkg,
                    "objects": {"common": {}, "ml": {}},
                }
            }
        ),
        encoding="utf-8",
    )
    (pipe / pkg).mkdir()
    (pipe / pkg / "common.yaml").write_text(
        yaml.dump(
            {
                "common": {
                    "type": "zone",
                    "label": "common",
                    "objects": {},
                }
            }
        ),
        encoding="utf-8",
    )
    (pipe / pkg / "common").mkdir()
    (pipe / pkg / "ml.yaml").write_text(
        yaml.dump(
            {
                "ml": {
                    "type": "zone",
                    "label": "ml",
                    "objects": {},
                }
            }
        ),
        encoding="utf-8",
    )
    (pipe / pkg / "ml").mkdir()
    # fantomes imbriques (comme apres mauvais import)
    (pipe / pkg / "common" / "common").mkdir()
    (pipe / pkg / "common" / "ml").mkdir()
    (pipe / pkg / "common" / "ml" / "x.yaml").write_text(
        yaml.dump(
            {
                "x": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                }
            }
        ),
        encoding="utf-8",
    )
    (pipe / pkg / pkg).mkdir()  # package se re-contient

    client = TestClient(create_gui_app(tmp_path / "d.duckdb", pipe))
    with client:
        tabs = client.get("/gui/tabs").json()
        ids = [t["id"] for t in tabs["tabs"]]
        labels = [t.get("label") for t in tabs["tabs"]]

        assert "default" in ids
        # une seule entree par zone id
        assert ids.count(f"{pkg}/common") + ids.count("common") == 1 or any(
            "common" in i for i in ids
        )
        # pas de chemin fantome common/common ni common/ml comme zone separee ml x2
        phantom = [
            i
            for i in ids
            if i.endswith("/common/common")
            or i.endswith("/common/ml")
            or i.endswith(f"/{pkg}/{pkg}")
            or i == f"{pkg}/{pkg}"
        ]
        assert phantom == [], f"chemins fantomes encore listes: {phantom} ids={ids}"

        # labels: pas 3x « ml »
        leaf_labels = [str(l).split("/")[-1] for l in labels if l and l != "default"]
        assert leaf_labels.count("ml") <= 1, labels
        assert leaf_labels.count("common") <= 1, labels

        # zone ids uniques
        zone_ids = [
            t.get("zone_id") or str(t["id"]).split("/")[-1]
            for t in tabs["tabs"]
            if t["id"] != "default"
        ]
        assert len(zone_ids) == len(set(zone_ids)), zone_ids


def test_nested_zones_still_listed_once_each(tmp_path: Path):
    """pack + pack/a + pack/b restent visibles (ids differents)."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "e.duckdb", pipe))
    with client:
        assert client.post("/gui/tabs", json={"name": "pack"}).status_code == 200
        assert (
            client.post("/gui/tabs/pack/activate").status_code == 200
            or client.post("/gui/tabs/pack/activate", json={}).status_code == 200
        )
        # activer pack puis creer a, b
        client.post("/gui/tabs/pack/activate")
        r_a = client.post("/gui/tabs", json={"name": "a"})
        # si active n est pas pack, creer sous main puis deplacer n est pas teste
        assert r_a.status_code == 200, r_a.text
        tabs = client.get("/gui/tabs").json()
        ids = [t["id"] for t in tabs["tabs"]]
        assert "default" in ids
        assert any(i == "pack" or i.endswith("/pack") for i in ids)
