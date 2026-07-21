"""Factory Flask — serveur API REST autonome."""

from __future__ import annotations

from flask import Flask

from rod_ia.api.dependencies import AppContainer, build_container
from rod_ia.api.routes.health import create_health_blueprint
from rod_ia.api.routes.prediction import create_prediction_blueprint


def create_api_app(container: AppContainer | None = None) -> Flask:
    container = container or build_container()
    app = Flask(__name__)
    app.config["CONTAINER"] = container

    app.register_blueprint(create_health_blueprint())
    app.register_blueprint(create_prediction_blueprint(container))

    return app


def run_api(host: str = "127.0.0.1", port: int = 5002) -> None:
    app = create_api_app()
    print(f"[api] ROD-IA Prediction API → http://{host}:{port}/api/v1")
    print(f"[api] POST predict → http://{host}:{port}/api/v1/predict")
    app.run(host=host, port=port, debug=False, use_reloader=False)