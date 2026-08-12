"""F0108 — documentation README + HTML UML backend/frontend."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_feature_f0108_registered():
    text = (REPO / "gestion_projet" / "features.csv").read_text(encoding="utf-8")
    assert "F0108" in text


def test_readme_points_to_uml_html():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "documentation.html" in readme
    assert "uml" in readme.lower() or "UML" in readme


def test_html_has_backend_and_frontend_uml():
    html = (REPO / "doc" / "documentation.html").read_text(encoding="utf-8")
    assert 'id="uml-backend"' in html
    assert 'id="uml-frontend"' in html
    assert "classDiagram" in html
    assert "mermaid" in html.lower()
    # classes metiers backend
    for name in (
        "Step",
        "ZoneStep",
        "ConnectionPipeline",
        "GuiService",
        "YamlStepStore",
        "GraphOps",
        "RenatusService",
    ):
        assert f"class {name}" in html or f"class {name} " in html
    # frontend
    for name in ("GuiApp", "GuiState", "UiController", "GraphCanvas", "StepType"):
        assert name in html


def test_html_class_attributes_present():
    html = (REPO / "doc" / "documentation.html").read_text(encoding="utf-8")
    # attributs cles documentes
    assert "ALLOWED_CONFIG_KEYS" in html or "+str id" in html
    assert "objects" in html
    assert "_active_tab" in html or "active_tab" in html
    assert "selected" in html


def test_architecture_has_uml_section():
    arch = (REPO / "doc" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "UML" in arch
    assert "documentation.html" in arch
