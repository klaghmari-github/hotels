"""
F0071 — onglets bas View / Track ; Apply seulement sur Track.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0071_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(
        encoding="utf-8"
    )
    assert "F0071" in text


def test_html_view_track_labels_and_actions():
    from tests.helpers.static_sources import read_css, read_index

    html = read_index()
    assert ">View<" in html
    assert ">Track<" in html
    # plus les anciens libelles comme titres d onglet bas
    assert ">Data preview<" not in html
    assert ">Changelogs<" not in html
    assert 'data-testid="dataview-actions"' in html
    assert 'data-testid="changelog-actions"' in html
    assert 'id="changelog-actions"' in html
    assert "btn-changelog-apply-file" in html
    assert "btn-changelog-apply-all" in html
    # Apply dans le bloc track (hidden par defaut)
    assert 'id="changelog-actions"' in html and "hidden" in html

    css = read_css()
    assert "#changelog-actions[hidden]" in css
    assert "display: none !important" in css


def test_js_switch_hides_apply_on_view():
    from tests.helpers.static_sources import read_all_js

    js = read_all_js()
    assert "switchBottomTab" in js
    assert "changelogActions" in js
    assert "dataviewActions" in js
    # exclusivite
    assert "dataviewActions.hidden" in js or "el.dataviewActions.hidden" in js
    assert "changelogActions.hidden" in js or "el.changelogActions.hidden" in js
    # aliases view/track
    assert "track" in js.lower()
