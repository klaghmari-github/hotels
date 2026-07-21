from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer
from rod_ia.domain.models.store import StoreConfiguration


def create_hotel_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("hotel", __name__)

    @blueprint.get("/api/hotel/<hotel_id>")
    def get_hotel(hotel_id: str):
        record = container.identity_registry.get(hotel_id)
        if not record:
            return jsonify({"error": "hotel_id inconnu"}), 404
        return jsonify(
            {
                "record": record.to_dict(),
                "enriched": (
                    container.feature_store.load_enriched(hotel_id).to_dict()
                    if container.feature_store.load_enriched(hotel_id)
                    else None
                ),
                "director_inputs": container.feature_store.load_director_inputs(hotel_id),
                "store_config": (
                    container.feature_store.load_store_config(hotel_id).to_dict()
                    if container.feature_store.load_store_config(hotel_id)
                    else None
                ),
            }
        )

    @blueprint.post("/api/hotel/<hotel_id>/inputs")
    def save_inputs(hotel_id: str):
        payload = request.get_json(force=True) or {}
        container.feature_store.save_director_inputs(hotel_id, payload)
        if "store" in payload:
            container.feature_store.save_store_config(
                hotel_id, StoreConfiguration.from_dict(payload["store"])
            )
        return jsonify({"status": "saved", "hotel_id": hotel_id})

    @blueprint.get("/api/registry")
    def list_registry():
        return jsonify(
            {"hotels": [record.to_dict() for record in container.identity_registry.all_records()]}
        )

    return blueprint