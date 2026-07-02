from flask import Blueprint, jsonify

from rod_ia.api.dependencies import AppContainer


def create_performance_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("performance", __name__)

    @blueprint.get("/api/performance")
    def performance():
        path = container.settings.performance_report_path
        if not path.exists():
            return jsonify(
                {
                    "error": "Rapport absent — exécuter ./init.sh",
                    "validation_year": 2026,
                    "rows": [],
                    "summary": {},
                }
            ), 404
        import json

        return jsonify(json.loads(path.read_text(encoding="utf-8")))

    @blueprint.get("/api/brands")
    def brands():
        path = container.settings.brand_projections_path
        if not path.exists():
            return jsonify({"brands": {}, "warning": "Exécuter ./init.sh pour extraire l'Excel"})
        import json

        return jsonify(json.loads(path.read_text(encoding="utf-8")))

    return blueprint