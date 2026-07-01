from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer
from rod_ia.domain.models.simulation import RodSimulationRequest


def create_simulate_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("simulate", __name__)

    @blueprint.post("/api/simulate")
    def simulate():
        payload = request.get_json(force=True) or {}
        request_model = RodSimulationRequest.from_dict(payload)
        rod_result = container.rod_simulator.simulate(request_model)
        ai_result = container.ai_predictor.predict(request_model)
        if request_model.identity.hotel_id:
            container.feature_store.append_simulation(request_model.identity.hotel_id, rod_result)
        return jsonify({"rod": rod_result.to_dict(), "ai": ai_result.to_dict()})

    @blueprint.post("/api/optimize")
    def optimize():
        payload = request.get_json(force=True) or {}
        request_model = RodSimulationRequest.from_dict(payload)
        return jsonify(container.optimizer.optimize(request_model))

    return blueprint