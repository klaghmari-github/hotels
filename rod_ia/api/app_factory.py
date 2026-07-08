"""Factory Flask — point d'entrée HTTP."""

from __future__ import annotations

import threading
import time
import webbrowser
from typing import Literal

from flask import Flask, send_from_directory

from rod_ia.api.dependencies import AppContainer, build_container
from rod_ia.api.routes.catalog import create_catalog_blueprint
from rod_ia.api.routes.enrich import create_enrich_blueprint
from rod_ia.api.routes.health import create_health_blueprint
from rod_ia.api.routes.hotel import create_hotel_blueprint
from rod_ia.api.routes.exploration import create_exploration_blueprint
from rod_ia.api.routes.interpretation import create_interpretation_blueprint
from rod_ia.api.routes.performance import create_performance_blueprint
from rod_ia.api.routes.simulate import create_simulate_blueprint
from rod_ia.api.routes.train import create_train_blueprint

AppMode = Literal["user", "admin"]


def create_app(container: AppContainer | None = None, *, mode: AppMode = "admin") -> Flask:
    container = container or build_container()
    app = Flask(__name__, static_folder=str(container.settings.web_dir), static_url_path="/static")
    app.config["CONTAINER"] = container
    app.config["APP_MODE"] = mode

    app.register_blueprint(create_health_blueprint())
    app.register_blueprint(create_catalog_blueprint(container))
    app.register_blueprint(create_enrich_blueprint(container))
    app.register_blueprint(create_simulate_blueprint(container))
    app.register_blueprint(create_hotel_blueprint(container))

    if mode == "admin":
        app.register_blueprint(create_performance_blueprint(container))
        app.register_blueprint(create_interpretation_blueprint(container))
        app.register_blueprint(create_exploration_blueprint(container))
        app.register_blueprint(create_train_blueprint(container))

    web_dir = container.settings.web_dir

    if mode == "user":

        @app.get("/")
        def index():
            return send_from_directory(web_dir, "index.html")

    else:

        @app.get("/")
        def admin_home():
            return send_from_directory(web_dir, "admin.html")

        @app.get("/simulator")
        def admin_simulator():
            return send_from_directory(web_dir, "admin-simulator.html")

        @app.get("/docs")
        def docs():
            docs_dir = container.settings.project_root / "rod_ia" / "web" / "docs"
            index = docs_dir / "index.html"
            if index.exists():
                return send_from_directory(docs_dir, "index.html")
            return "Documentation absente — exécuter: python scripts/generate_code_docs.py", 404

        @app.get("/interpretation")
        def interpretation():
            return send_from_directory(web_dir, "interpretation.html")

        @app.get("/exploration")
        def exploration():
            return send_from_directory(web_dir, "exploration.html")

        @app.get("/exploration/guide")
        def exploration_guide():
            guide = container.settings.project_root / "docs" / "exploration_interface.md"
            if guide.exists():
                return send_from_directory(guide.parent, "exploration_interface.md")
            return "Guide absent", 404

        @app.get("/journal")
        def journal():
            consignes_path = container.settings.project_root / "docs" / "consignes.md"
            if consignes_path.exists():
                return send_from_directory(consignes_path.parent, "consignes.md")
            return "Consignes absentes — voir docs/consignes.md", 404

    return app


def _open_browser_later(url: str, delay_s: float = 1.2) -> None:
    def _open() -> None:
        time.sleep(delay_s)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()


def run(*, mode: AppMode = "user", host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True) -> None:
    app = create_app(mode=mode)
    url = f"http://{host}:{port}/"
    label = "Simulateur ROD" if mode == "user" else "Administration ROD"
    print(f"[{mode}] {label} → {url}")
    if open_browser:
        _open_browser_later(url)
    app.run(host=host, port=port, debug=True, use_reloader=False)


if __name__ == "__main__":
    run()