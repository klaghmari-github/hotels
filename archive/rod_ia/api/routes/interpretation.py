from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer
from rod_ia.domain.models.simulation import RodSimulationRequest


def create_interpretation_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("interpretation", __name__)

    @blueprint.post("/api/model-interpretation")
    def model_interpretation():
        payload = request.get_json(force=True) or {}
        request_model = RodSimulationRequest.from_dict(payload)
        concept = payload.get("concept")
        report = container.model_interpretation.interpret(request_model, concept=concept)
        return jsonify(report)

    return blueprint