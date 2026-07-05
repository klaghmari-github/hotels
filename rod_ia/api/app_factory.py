"""Factory Flask — point d'entrée HTTP."""

from __future__ import annotations

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


def create_app(container: AppContainer | None = None) -> Flask:
    container = container or build_container()
    app = Flask(__name__, static_folder=str(container.settings.web_dir), static_url_path="/static")
    app.config["CONTAINER"] = container

    app.register_blueprint(create_health_blueprint())
    app.register_blueprint(create_catalog_blueprint(container))
    app.register_blueprint(create_enrich_blueprint(container))
    app.register_blueprint(create_simulate_blueprint(container))
    app.register_blueprint(create_hotel_blueprint(container))
    app.register_blueprint(create_performance_blueprint(container))
    app.register_blueprint(create_interpretation_blueprint(container))
    app.register_blueprint(create_exploration_blueprint(container))
    app.register_blueprint(create_train_blueprint(container))

    @app.get("/")
    def index():
        return send_from_directory(container.settings.web_dir, "index.html")

    @app.get("/docs")
    def docs():
        docs_dir = container.settings.project_root / "rod_ia" / "web" / "docs"
        index = docs_dir / "index.html"
        if index.exists():
            return send_from_directory(docs_dir, "index.html")
        return "Documentation absente — exécuter: python scripts/generate_code_docs.py", 404

    @app.get("/interpretation")
    def interpretation():
        return send_from_directory(container.settings.web_dir, "interpretation.html")

    @app.get("/exploration")
    def exploration():
        return send_from_directory(container.settings.web_dir, "exploration.html")

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


def run() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)


if __name__ == "__main__":
    run()