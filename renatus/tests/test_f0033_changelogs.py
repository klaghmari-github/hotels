"""
F0033 — historique (supplantee en partie par F0035).

Les tests per-step changelog sont retires: l API est globale (F0035).
On conserve un smoke minimal de compatibilite ProjectGit file_*.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0033_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0033" in features


def test_project_git_file_helpers_still_work(tmp_path: Path):
    from renatus.pipeline.project_git import ProjectGit

    root = tmp_path / "proj"
    root.mkdir()
    git = ProjectGit(root)
    git.init_repository()
    pipelines = root / "flow"
    pipelines.mkdir()
    f = pipelines / "t_a.yaml"
    f.write_text(
        "t_a:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  sql: SELECT 1 AS n\n  label: t_a\n",
        encoding="utf-8",
    )
    assert git.commit_all("add t_a") is True
    f.write_text(
        "t_a:\n  type: table\n  mode: create_or_replace\n"
        "  requires: []\n  sql: SELECT 2 AS n\n  label: t_a\n",
        encoding="utf-8",
    )
    assert git.commit_all("update sql to 2") is True

    rel = "flow/t_a.yaml"
    log = git.file_log(rel, limit=10)
    assert len(log) >= 2
    latest = log[0]["commit"]
    older = log[1]["commit"]
    diff_latest = git.file_diff_at(latest, rel)
    assert diff_latest["ok"] is True
    content_old = git.file_content_at(older, rel)
    assert content_old is not None
    assert "SELECT 1" in content_old

    res = git.restore_file_from_commit(older, rel)
    assert res["ok"] is True
    assert "SELECT 1" in f.read_text(encoding="utf-8")
