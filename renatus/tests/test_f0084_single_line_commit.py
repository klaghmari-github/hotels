"""F0084 — Enter / blur sur champ monoligne → commit + save immediate."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0084_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0084" in text


def test_js_commit_single_line_enter_blur():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "commitEditField" in js
    assert "isSingleLineControl" in js
    assert "flushAutoSave" in js
    # Enter
    assert 'key !== "Enter"' in js or 'key === "Enter"' in js
    # blur / focusout
    assert "focusout" in js
    # mousedown preventDefault sur crayon (cancel sans commit blur)
    assert "_suppressBlurCommit" in js or "suppressBlurCommit" in js
    # SELECT = monoligne; TEXTAREA = multi (F0085)
    assert "SELECT" in js
    assert "isSingleLineControl" in js


def test_js_commit_keeps_values_not_restore():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    # commitEditField ne doit pas appeler restoreFieldControls
    idx = js.find("function commitEditField")
    assert idx > 0
    block = js[idx : idx + 900]
    assert "restoreFieldControls" not in block
    assert "flushAutoSave" in block
    assert "is-editing" in block
    # cancel garde restore
    cidx = js.find("function cancelEditField")
    cblock = js[cidx : cidx + 600]
    assert "restoreFieldControls" in cblock
