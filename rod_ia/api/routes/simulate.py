from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer
from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.rules.financing_cost_rules import ConceptFinancing


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

    @blueprint.post("/api/simulate/detail")
    def simulate_detail():
        payload = request.get_json(force=True) or {}
        base = RodSimulationRequest.from_dict(payload.get("base") or payload)
        concept = str(payload.get("concept", "LIBERTY")).upper()
        financing = ConceptFinancing.from_dict(payload.get("financing"))
        return jsonify(
            container.concept_detail.simulate_detail(base, concept, financing)
        )

    return blueprint