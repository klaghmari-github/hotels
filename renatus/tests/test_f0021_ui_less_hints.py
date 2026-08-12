"""
F0021 — UI GUI sans textes explicatifs redondants.
Titres de zone suffisent; pas de hints en petit partout.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

from tests.helpers.static_sources import read_all_js
INDEX = REPO / "src" / "renatus" / "gui" / "static" / "index.html"
APP_JS = REPO / "src" / "renatus" / "gui" / "static" / "app.js"
STYLE = REPO / "src" / "renatus" / "gui" / "static" / "style.css"


# Phrases explicatives qui ne doivent plus polluer l UI (F0021 + F0066)
FORBIDDEN_SNIPPETS = [
    "Cliquez pour ajouter",
    "from scratch",
    "pipeline · graphe",
    "Cochez pour lier",
    "Si vide, la table",
    "Synchronise avec le formulaire",
    "syntaxe coloree",
    "Selectionnez un dataset",
    "Selectionnez une step sur le graphe",
    "ajoutez un outil depuis la barre",
    "ajoutez un outil depuis la palette",
    "Recharger (limit 3)",
    "Build & afficher",
    "vue temporaire par tour",
    "step a rejouer a chaque scenario",
    # F0066: micro-textes config
    "Dependances = composants pipeline",
    "Dependances inverses calculees",
    "Aucun composant ne reference celui-ci",
    "Aucun composant disponible (ajoutez",
    "Utilise par",
    "Presence = copies disque",
    "Code execute dans le venv",
    "Dans le SQL, utilisez le",
    "Nom de la relation en base",
]


def test_feature_f0021_registered():
    features = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0021" in features


def test_html_no_redundant_hints():
    html = INDEX.read_text(encoding="utf-8")
    for snip in FORBIDDEN_SNIPPETS:
        assert snip not in html, f"texte redondant encore present: {snip!r}"


def test_html_zone_titles_present():
    html = INDEX.read_text(encoding="utf-8")
    # F0079: Composant / Flux (ex Outils / Graphe)
    assert "<h2>Composant</h2>" in html or "<h2>Outils</h2>" in html
    assert (
        "<h2>Flux</h2>" in html
        or "<h2>Graphe</h2>" in html
        or ">Flux<" in html
        or ">Graphe<" in html
    )
    assert "Config" in html
    # F0033/F0071: zone bas = onglets View / Track
    assert (
        "DataView" in html
        or "Data preview" in html
        or ">View<" in html
        or 'tab-data-preview' in html
    )
    assert ">YAML<" in html or "YAML" in html
    # F0026 / F0027: controles projet + onglets
    assert 'data-testid="pipeline-tabs"' in html
    assert 'data-testid="btn-project-save"' in html


def test_js_toolbox_without_desc_paragraph():
    js = read_all_js()
    # ne doit plus injecter t-desc dans le HTML des outils
    assert 't-desc">' not in js and "t-desc'>" not in js
    assert "t-title" in js


def test_js_yaml_status_errors_only():
    js = read_all_js()
    assert "YAML synchronise avec le formulaire" not in js
    assert "Formulaire synchronise avec le YAML" not in js
    assert 'kind === "err"' in js or "kind === 'err'" in js


def test_css_hides_tool_desc():
    css = STYLE.read_text(encoding="utf-8")
    assert ".tool .t-desc" in css
    assert "display: none" in css


def test_served_page_clean(tmp_path: Path):
    from fastapi.testclient import TestClient

    from renatus.gui.app import create_gui_app

    pipe = tmp_path / "flow"
    pipe.mkdir()
    client = TestClient(create_gui_app(tmp_path / "c.duckdb", pipe))
    with client:
        html = client.get("/").text
        for snip in FORBIDDEN_SNIPPETS:
            assert snip not in html, snip
        assert "Composant" in html or "Outils" in html
        assert (
            "DataView" in html
            or "Data preview" in html
            or ">View<" in html
            or "tab-data-preview" in html
        )
