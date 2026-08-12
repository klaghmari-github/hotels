"""
F0035 — changelogs globaux (correction F0033).

- Timeline git globale (pas par composant)
- Clic commit: fichiers + diff du fichier focus
- Apply file: restaure un fichier (nouveau commit)
- Apply all: snapshot complet au commit (nouveau commit)
- Jamais de reset/revert: forward-only
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"


def test_feature_f0035_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0035" in features


def test_ui_global_changelogs():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-testid="btn-global-changelogs"' in html
    assert 'data-testid="tab-changelogs"' in html
    assert 'data-testid="changelog-timeline"' in html
    assert 'data-testid="changelog-files"' in html
    assert 'data-testid="btn-changelog-apply-file"' in html
    assert 'data-testid="btn-changelog-apply-all"' in html
    assert "Apply file" in html
    assert "Apply all" in html

    js = read_all_js()
    assert "/gui/changelog" in js
    assert "loadGlobalChangelog" in js
    assert 'mode: isFile ? "file" : "all"' in js or 'mode: "file"' in js
    assert "applyChangelog" in js
    # plus d API par step
    assert "/gui/step/" not in js or "/changelog" in js
    assert '"/gui/step/" + encodeURIComponent(stepId) + "/changelog"' not in js


def test_global_log_and_snapshot_apply(tmp_path: Path):
    from renatus.pipeline.project_git import ProjectGit

    root = tmp_path / "g"
    root.mkdir()
    git = ProjectGit(root)
    git.init_repository()
    pipe = root / "flow"
    pipe.mkdir()
    a = pipe / "default" / "a.yaml"
    b = pipe / "default" / "b.yaml"
    a.write_text(
        "a:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  sql: SELECT 1\n  label: a\n",
        encoding="utf-8",
    )
    assert git.commit_all("add a") is True
    b.write_text(
        "b:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  sql: SELECT 2\n  label: b\n",
        encoding="utf-8",
    )
    assert git.commit_all("add b") is True
    a.write_text(
        "a:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  sql: SELECT 99\n  label: a\n",
        encoding="utf-8",
    )
    assert git.commit_all("update a") is True

    log = git.global_log(limit=20)
    assert len(log) >= 3
    # recent first
    assert "update a" in log[0]["subject"]
    assert "flow/a.yaml" in log[0]["files"]
    assert log[0]["file_count"] >= 1

    # trouver commit "add b" (a=SELECT 1, b exists)
    add_b = next(e for e in log if "add b" in e["subject"])
    assert "flow/b.yaml" in add_b["files"]

    # apply file only: restore a from before update (commit add b still has SELECT 1)
    # use parent of update = add b's tree has a with SELECT 1
    res = git.restore_file_from_commit(add_b["commit"], "flow/a.yaml")
    assert res["ok"] is True
    assert res["mode"] == "file"
    assert "SELECT 1" in a.read_text(encoding="utf-8")
    # b still SELECT 2
    assert "SELECT 2" in b.read_text(encoding="utf-8")

    # re-update a then snapshot to add b state
    a.write_text(
        "a:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  sql: SELECT 77\n  label: a\n",
        encoding="utf-8",
    )
    git.commit_all("a to 77")
    # also change b
    b.write_text(
        "b:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  sql: SELECT 88\n  label: b\n",
        encoding="utf-8",
    )
    git.commit_all("b to 88")

    snap = git.restore_snapshot_from_commit(add_b["commit"])
    assert snap["ok"] is True
    assert snap["mode"] == "all"
    assert "SELECT 1" in a.read_text(encoding="utf-8")
    assert "SELECT 2" in b.read_text(encoding="utf-8")
    # history advanced (new commits still exist in log)
    log2 = git.global_log(limit=30)
    assert len(log2) > len(log)
    assert log2[0]["commit"] != add_b["commit"]


def test_gui_global_changelog_api(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    db = tmp_path / "g.duckdb"
    proj = tmp_path / "g.renatus.yaml"
    client = TestClient(create_gui_app(db, pipe))
    with client:
        assert (
            client.post(
                "/gui/project/save",
                json={"path": str(proj), "name": "g"},
            ).status_code
            == 200
        )
        client.post(
            "/gui/steps",
            json={
                "name": "t1",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 1 AS n",
                    "label": "t1",
                },
            },
        )
        client.post(
            "/gui/steps",
            json={
                "name": "t2",
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 2 AS n",
                    "label": "t2",
                },
            },
        )
        client.put(
            "/gui/step/t1",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 50 AS n",
                    "label": "t1",
                }
            },
        )

        cl = client.get("/gui/changelog")
        assert cl.status_code == 200, cl.text
        body = cl.json()
        assert body["ok"] is True
        assert body["count"] >= 2
        entries = body["entries"]
        assert "files" in entries[0]

        # detail du commit le plus recent
        top = entries[0]["commit"]
        det = client.get(f"/gui/changelog/{top}")
        assert det.status_code == 200, det.text
        dj = det.json()
        assert "diff" in dj
        assert dj.get("files") is not None
        assert dj.get("path")

        # trouver un commit ou t1 a SELECT 1 (F0082: flow/default/t1.yaml)
        t1_path = "flow/default/t1.yaml"
        v1 = None
        for e in entries:
            d = client.get(
                f"/gui/changelog/{e['commit']}",
                params={"path": t1_path},
            ).json()
            content = d.get("content") or ""
            if "SELECT 1" in content:
                v1 = e["commit"]
                break
        assert v1 is not None

        # apply file only
        app = client.post(
            "/gui/changelog/apply",
            json={"commit": v1, "mode": "file", "path": t1_path},
        )
        assert app.status_code == 200, app.text
        aj = app.json()
        assert aj["ok"] is True
        assert aj["mode"] == "file"
        step = client.get("/gui/step/t1").json()
        assert "SELECT 1" in (step.get("config") or {}).get("script", "")
        # t2 still exists
        assert client.get("/gui/step/t2").status_code == 200

        # modify both then apply all from v1-ish: use commit after both created
        # find commit with both t1 and t2 where t1 has SELECT 1
        both = None
        for e in client.get("/gui/changelog").json()["entries"]:
            files = e.get("files") or []
            # use content at commit for t1 and t2
            c1 = client.get(
                f"/gui/changelog/{e['commit']}",
                params={"path": "flow/default/t1.yaml"},
            ).json().get("content") or ""
            c2 = client.get(
                f"/gui/changelog/{e['commit']}",
                params={"path": "flow/default/t2.yaml"},
            ).json().get("content") or ""
            if "SELECT 1" in c1 and "SELECT 2" in c2:
                both = e["commit"]
                break
        # if not found, use v1 and ensure t2 file exists at that commit via snapshot of later
        if both is None:
            both = v1

        client.put(
            "/gui/step/t1",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 9 AS n",
                    "label": "t1",
                }
            },
        )
        client.put(
            "/gui/step/t2",
            json={
                "config": {
                    "type": "table",
                    "mode": "create_or_replace",
                    "requires": [],
                    "sql": "SELECT 8 AS n",
                    "label": "t2",
                }
            },
        )

        # find snapshot where both are original-ish
        entries2 = client.get("/gui/changelog").json()["entries"]
        target = None
        for e in entries2:
            c1 = client.get(
                f"/gui/changelog/{e['commit']}",
                params={"path": "flow/default/t1.yaml"},
            ).json().get("content") or ""
            c2 = client.get(
                f"/gui/changelog/{e['commit']}",
                params={"path": "flow/default/t2.yaml"},
            ).json().get("content") or ""
            if "SELECT 1" in c1 and c2 and "SELECT 2" in c2:
                target = e["commit"]
                break
        assert target is not None

        app2 = client.post(
            "/gui/changelog/apply",
            json={"commit": target, "mode": "all"},
        )
        assert app2.status_code == 200, app2.text
        assert app2.json()["mode"] == "all"
        t1 = client.get("/gui/step/t1").json()["config"]["script"]
        t2 = client.get("/gui/step/t2").json()["config"]["script"]
        assert "SELECT 1" in t1
        assert "SELECT 2" in t2

        # forward only: count commits increased
        assert client.get("/gui/changelog").json()["count"] >= body["count"]


def test_changelog_requires_project(tmp_path: Path):
    """
    F0065: le workspace sans .renatus.yaml active le git automatiquement.
    (avant: 400/500 tant que projet non sauve — obsolete)
    """
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "n.duckdb", pipe))
    with client:
        r = client.get("/gui/changelog")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert "entries" in body
