from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer
from rod_ia.domain.models.simulation import RodSimulationRequest


def create_simulate_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("simulate", __name__)

    @blueprint.post("/api/simulate")
    def simulate():
        payload = request.get_json(force=True) or {}
        request_model = RodSimulationRequest.from_dict(payload)
        full = container.simulation_orchestrator.simulate_all(request_model)
        if request_model.identity.hotel_id:
            reco = full.recommended_concept
            if reco in full.rod_by_concept:
                container.feature_store.append_simulation(
                    request_model.identity.hotel_id,
                    full.rod_by_concept[reco],
                )
        return jsonify(full.to_dict())

    @blueprint.post("/api/optimize")
    def optimize():
        payload = request.get_json(force=True) or {}
        request_model = RodSimulationRequest.from_dict(payload)
        return jsonify(container.optimizer.optimize(request_model))

    return blueprint