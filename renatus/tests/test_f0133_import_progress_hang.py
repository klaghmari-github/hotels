"""F0133 — import ne reste pas bloque a ~90 % (post-traitement leger)."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.static_sources import read_all_js, read_index

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0133_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0133" in text


def test_js_import_avoids_switchtab_under_progress():
    """Post-import: pas de switchTab/ensureSelection sous la pop (hang 90%)."""
    js = (REPO / "src/renatus/gui/static/app/import-flow.js").read_text(
        encoding="utf-8"
    )
    assert "skipSelection" in js
    assert "refreshGraph({ skipSelection: true })" in js or (
        "refreshGraph(" in js and "skipSelection" in js
    )
    # selection differee apres pop
    assert "setTimeout" in js
    assert "ensureSelection" in js
    # timeout de securite
    assert "withTimeout" in js
    # ne plus appeler switchTab dans runImportFlow (chemin lourd)
    run_fn = js.split("export async function runImportFlow")[1].split(
        "export function wireImportFlow"
    )[0]
    # ignorer mentions dans commentaires
    code_only = "\n".join(
        ln for ln in run_fn.splitlines() if not ln.strip().startswith("//")
    )
    assert "switchTab(" not in code_only
    assert "skipSelection" in run_fn


def test_js_refresh_graph_skip_selection_option():
    js = (REPO / "src/renatus/gui/static/app/graph.js").read_text(encoding="utf-8")
    assert "skipSelection" in js
    assert "opts.skipSelection" in js or "options.skipSelection" in js


def test_js_select_step_anti_recursion():
    js = (
        REPO / "src/renatus/gui/static/app/config/step-crud.js"
    ).read_text(encoding="utf-8")
    assert "_ensureSelectionDepth" in js
    assert "skipEnsureFallback" in js
    assert "skipDataView" in js


def test_cache_bust_f0133():
    html = read_index()
    # cache-bust avance avec les features suivantes (ex. F0144)
    assert "main.js?v=F" in html


def test_all_js_mentions_f0133_path():
    js = read_all_js()
    assert "skipSelection" in js
    assert "withTimeout" in js
