from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer
from rod_ia.domain.services.prediction_api_service import PredictionApiService


def create_prediction_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("prediction", __name__)
    service = PredictionApiService(
        enrich_service=container.enrich_service,
        feature_store=container.feature_store,
        identity_registry=container.identity_registry,
        reference=container.reference_repository,
        orchestrator=container.simulation_orchestrator,
    )

    @blueprint.post("/api/v1/predict")
    def predict():
        payload = request.get_json(force=True, silent=True)
        if not payload:
            return jsonify({"error": "Corps JSON requis"}), 400
        if not (payload.get("identity") or payload.get("hotel_name")):
            return jsonify({"error": "Champ identity (ou hotel_name) requis"}), 400
        if payload.get("hotel_name") and not payload.get("identity"):
            payload = {
                **payload,
                "identity": {
                    "hotel_name": payload["hotel_name"],
                    "city": payload.get("city", ""),
                    "address": payload.get("address", ""),
                    "brand": payload.get("brand", ""),
                    "hotel_id": payload.get("hotel_id"),
                },
            }
        try:
            response = service.predict(payload)
            return jsonify(response.to_dict())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @blueprint.get("/api/v1")
    def api_info():
        return jsonify({
            "service": "rod-ia-prediction-api",
            "version": "1",
            "endpoints": {
                "predict": "POST /api/v1/predict",
                "health": "GET /health",
            },
        })

    return blueprint