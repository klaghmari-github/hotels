from flask import Blueprint, request, jsonify
from app.config.settings import REFERENCE_DIR, ARTIFACTS_DIR
from app.domain.models.simulation import RodSimulationRequest
from app.domain.repositories.reference_repository import ReferenceRepository
from app.domain.rules.revenue_rules import RodRevenueRules
from app.domain.rules.cost_rules import RodCostRules
from app.domain.rules.recommendation_rules import RodRecommendationRules
from app.domain.services.rod_simulator import RodSimulator
from app.domain.services.ai_predictor import AIRodRevenuePredictor
from app.domain.services.optimizer import RodOptimizer

simulate_bp = Blueprint('simulate', __name__)
reference = ReferenceRepository(REFERENCE_DIR / 'rod_reference_demo.json')
rod_simulator = RodSimulator(RodRevenueRules(reference), RodCostRules(reference), RodRecommendationRules())
ai_predictor = AIRodRevenuePredictor(ARTIFACTS_DIR)
optimizer = RodOptimizer(rod_simulator)

@simulate_bp.post('/api/simulate')
def simulate():
    payload = request.get_json(force=True) or {}
    req = RodSimulationRequest.from_dict(payload)
    rod_result = rod_simulator.simulate(req)
    ai_result = ai_predictor.predict(req)
    return jsonify({'rod': rod_result.to_dict(), 'ai': ai_result.to_dict()})

@simulate_bp.post('/api/optimize')
def optimize():
    payload = request.get_json(force=True) or {}
    req = RodSimulationRequest.from_dict(payload)
    return jsonify(optimizer.optimize(req))
