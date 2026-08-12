"""
Package renatus.gui — GUI web Renatus GUI.

Factory: create_gui_app(db_path, pipeline_path)
Service: GuiService
CLI: renatus-gui / python -m renatus.gui
"""

from __future__ import annotations

from .app import GuiApp, create_gui_app
from .service import GuiService
from .yaml_store import YamlStepStore

try:
    from .server import main
except ImportError:

    def main(argv=None):  # type: ignore[misc]
        raise SystemExit(
            'uvicorn/fastapi requis: pip install "renatus[api]"'
        )


__all__ = [
    "create_gui_app",
    "GuiApp",
    "GuiService",
    "YamlStepStore",
    "main",
]
