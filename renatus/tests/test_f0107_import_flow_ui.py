"""F0107 — import flux UI: dropzone, browse, selects/cartes stylés."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from renatus.gui.app import create_gui_app
from tests.helpers.static_sources import read_all_js, read_css, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0107_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0107" in text


def test_html_import_dropzone_and_conflict_cards():
    html = read_index()
    assert 'data-testid="import-flow-dropzone"' in html
    assert 'data-testid="import-flow-file-picker"' in html
    assert 'data-testid="import-flow-dir-picker"' in html
    assert 'data-testid="import-flow-browse-file"' in html
    assert 'data-testid="import-flow-browse-dir"' in html
    assert 'data-testid="import-flow-conflict-cards"' in html
    assert "renatus-select" in html
    assert "import-flow-dialog" in html
    # select conflict toujours present (miroir / tests API)
    assert 'data-testid="import-flow-conflict"' in html


def test_js_import_dropzone_upload():
    js = read_all_js()
    assert "wireImportDropzone" in js or "import-flow-dropzone" in js
    assert "handleYamlFile" in js or "import_flow" in js
    assert "handleDirectoryFiles" in js or "webkitRelativePath" in js
    assert "getConflictStrategy" in js or "import-flow-conflict" in js
    assert "relative_path" in js
    assert "import_flow" in js


def test_css_import_flow_styled():
    css = read_css()
    assert "import-flow-dialog" in css
    assert "renatus-select" in css
    assert "import-flow-conflict-card" in css
    assert "import-flow-dropzone" in css


def test_upload_relative_path_for_bundle(tmp_path: Path):
    """F0107: upload avec relative_path reconstitue l arborescence."""
    pipe = tmp_path / "flow"
    pipe.mkdir()
    (pipe / "default").mkdir()
    (pipe / "default.yaml").write_text(
        "default:\n  type: zone\n  label: default\n  objects: {}\n",
        encoding="utf-8",
    )
    client = TestClient(create_gui_app(tmp_path / "a.duckdb", pipe))
    with client:
        content = yaml.dump(
            {
                "extra": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "script": "SELECT 1 AS n",
                }
            }
        ).encode("utf-8")
        r = client.post(
            "/gui/upload?subdir=import_flow",
            files={"file": ("extra.yaml", content, "application/x-yaml")},
            data={"relative_path": "bundle_demo/sub/extra.yaml"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "bundle_demo/sub/extra.yaml" in body.get("path", "")
        abs_path = Path(body["absolute"])
        assert abs_path.is_file()
        # import depuis le chemin absolu
        imp = client.post(
            "/gui/import/flow",
            json={
                "source": body["absolute"],
                "target_tab": "default",
                "conflict": "keep_both",
                "dry_run": False,
            },
        )
        assert imp.status_code == 200, imp.text
        assert "extra" in {
            n["id"]
            for n in client.get("/gui/graph?tab=main").json()["nodes"]
            if not n.get("external")
        }
