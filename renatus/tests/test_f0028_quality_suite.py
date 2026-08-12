"""
F0028 — qualite : suite de tests alignee sur l etat actuel du projet.

Verifie que le full check unitaires passe les gardes minimales
(features recentes presentes, pas d assertions UI obsoletes connues).
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
ARCHIVE = TESTS / "archive"
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"


def test_feature_f0028_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0028" in features


def test_archive_policy_documented():
    readme = ARCHIVE / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert "obsoletes" in text.lower() or "archive" in text.lower()
    assert "F0028" in text


def test_no_known_obsolete_ui_strings_in_active_tests():
    """
    Assertions figant d anciens libelles UI ne doivent plus trainer
    dans les tests actifs (ils cassent apres F0021/F0027).

    On detecte les formes assert "..." in html / assert '...' in html
    (pas les commentaires d historique ni les listes FORBIDDEN).
    """
    import re

    obsolete = [
        "Sources prerequis",
        "Graphe pipeline",
        "Build & afficher",
        "Cliquez pour ajouter une step",
    ]
    # assert "X" in ...  ou assert 'X' in ...  (presence positive)
    pat = re.compile(
        r"""assert\s+["']([^"']+)["']\s+in\s+"""
    )
    for path in TESTS.glob("test_*.py"):
        if path.name == "test_f0028_quality_suite.py":
            continue
        text = path.read_text(encoding="utf-8")
        for m in pat.finditer(text):
            snip = m.group(1)
            if snip in obsolete:
                # autorise assert "X" not in
                start = m.start()
                window = text[max(0, start - 12) : m.end() + 24]
                if " not in " in window:
                    continue
                raise AssertionError(
                    f"{path.name} fige encore le libelle obsolete: {snip!r}"
                )


def test_current_ui_contract_smoke():
    """Smoke: index.html reflete le design actuel (projet + onglets + requires)."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-testid="pipeline-tabs"' in html
    assert 'data-testid="btn-project-save"' in html
    assert 'data-testid="cfg-requires-picker"' in html
    assert "<h2>Flux</h2>" in html or "<h2>Graphe</h2>" in html
    assert "<h2>Composant</h2>" in html or "<h2>Outils</h2>" in html
    assert (
        "DataView" in html
        or "Data preview" in html
        or ">View<" in html
        or "tab-data-preview" in html
    )
    assert "Requires" in html
    # F0035 changelogs globaux
    assert 'data-testid="tab-changelogs"' in html
    assert 'data-testid="btn-global-changelogs"' in html
    assert 'data-testid="btn-changelog-apply-file"' in html
    assert 'data-testid="btn-changelog-apply-all"' in html


def test_recent_feature_tests_present():
    """Les modules de test des features recentes restent actifs."""
    expected = [
        "test_f0023_graph_dependencies_xlsx.py",
        "test_f0024_iteration_component.py",
        "test_f0025_documentation.py",
        "test_f0026_project_save.py",
        "test_f0027_pipeline_tabs.py",
        "test_f0028_quality_suite.py",
    ]
    for name in expected:
        assert (TESTS / name).is_file(), name


def test_archived_modules_not_collected_as_tests():
    """Les fichiers archives ne s appellent pas test_*.py sous archive/."""
    if not ARCHIVE.is_dir():
        return
    for path in ARCHIVE.rglob("test_*.py"):
        raise AssertionError(
            f"Module archive encore nomme test_*.py (pytest le collecterait): {path}"
        )
