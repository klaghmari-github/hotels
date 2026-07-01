from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer


def create_enrich_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("enrich", __name__)

    @blueprint.post("/api/enrich")
    def enrich():
        payload = request.get_json(force=True) or {}
        identity = payload.get("identity", payload)
        hotel_id, features, warnings = container.enrich_service.enrich(
            hotel_name=identity.get("hotel_name", ""),
            address=identity.get("address", ""),
            city=identity.get("city", ""),
            force_refresh=bool(payload.get("force_refresh", False)),
            hotel_id=identity.get("hotel_id"),
        )
        return jsonify(
            {
                "hotel_id": hotel_id,
                "features": features.to_dict(),
                "warnings": warnings,
            }
        )

    return blueprint