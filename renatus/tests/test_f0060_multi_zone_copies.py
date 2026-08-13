"""
F0060 / F0145 — multi-presence objet = symlink meme nom (meme id).

- share = symlink vers le fichier physique unique
- unshare = supprimer le lien si multi, refuse si seule presence
- save ecrit le fichier physique (visible via tous les liens)
- zones calculees depuis le FS
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0060_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0060" in text


def test_share_unshare_and_sync_save(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "m.duckdb", pipe))
    with client:
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "obj1",
                    "tab": "default",
                    "config": {
                        "type": "table",
                        "label": "Label1",
                        "name": "obj1",
                        "mode": "create_or_replace",
                        "requires": [],
                        "sql": "SELECT 1 AS n",
                    },
                },
            ).status_code
            == 200
        )
        # zone + share via objects save
        assert (
            client.post(
                "/gui/steps",
                json={
                    "name": "zone_a",
                    "tab": "default",
                    "config": {
                        "type": "zone",
                        "label": "ZA",
                        "objects": {"obj1": {}},
                    },
                },
            ).status_code
            == 200
        )
        # F0145: presence = symlink, master physique unique
        linked = pipe / "default" / "zone_a" / "obj1.yaml"
        master = pipe / "default" / "obj1.yaml"
        assert master.is_file() and not master.is_symlink()
        assert linked.is_file() and linked.is_symlink()
        assert linked.resolve() == master.resolve()

        st = client.get("/gui/step/obj1").json()
        zids = {z["id"] for z in st["zones"]}
        assert "default" in zids and "zone_a" in zids
        assert all(z.get("can_remove") for z in st["zones"])

        # modif label → meme contenu via tous les liens
        assert (
            client.put(
                "/gui/step/obj1",
                json={
                    "config": {
                        "type": "table",
                        "label": "Label10",
                        "name": "obj1",
                        "mode": "create_or_replace",
                        "requires": [],
                        "sql": "SELECT 1 AS n",
                    }
                },
            ).status_code
            == 200
        )
        for p in pipe.rglob("obj1.yaml"):
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            assert data["obj1"]["label"] == "Label10"

        # unshare zone_a
        r = client.post(
            "/gui/step/obj1/unshare-zone",
            json={"zone_tab": "zone_a"},
        )
        assert r.status_code == 200, r.text
        assert not linked.exists()
        st2 = client.get("/gui/step/obj1").json()
        assert not any(z["id"] == "zone_a" for z in st2["zones"])
        assert any(z["id"] == "default" for z in st2["zones"])
        # plus retirable (seule presence)
        assert all(not z.get("can_remove") for z in st2["zones"])

        # unshare sole → erreur
        bad = client.post(
            "/gui/step/obj1/unshare-zone",
            json={"zone_tab": "default"},
        )
        assert bad.status_code >= 400


def test_ui_f0060_strings():
    from tests.helpers.static_sources import read_all_js, read_index

    html = read_index()
    assert "copie" in html.lower() or "multi" in html.lower() or "disque" in html.lower()
    js = read_all_js()
    assert "unshare-zone" in js
    assert "can_remove" in js


def test_engine_allows_duplicate_id_files(tmp_path: Path):
    from renatus.pipeline.engine import ConnectionPipeline

    pipe = tmp_path / "p"
    pipe.mkdir()
    (pipe / "default").mkdir(parents=True, exist_ok=True)
    (pipe / "default" / "x.yaml").write_text(
        "o1:\n  type: table\n  label: A\n  mode: create_or_replace\n  requires: []\n  sql: SELECT 1\n",
        encoding="utf-8",
    )
    z = pipe / "default" / "z"
    z.mkdir(parents=True, exist_ok=True)
    (z / "o1.yaml").write_text(
        "o1:\n  type: table\n  label: A\n  mode: create_or_replace\n  requires: []\n  sql: SELECT 1\n",
        encoding="utf-8",
    )
    cp = ConnectionPipeline(str(tmp_path / "d.duckdb"), str(pipe))
    assert "o1" in cp.pipeline
    assert cp.pipeline["o1"]["label"] == "A"
