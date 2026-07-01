from flask import Blueprint, jsonify


def create_health_blueprint() -> Blueprint:
    blueprint = Blueprint("health", __name__)

    @blueprint.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "rod-ia"})

    return blueprint