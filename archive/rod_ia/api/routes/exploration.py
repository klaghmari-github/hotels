"""Routes exploration donnees et modele."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer


def create_exploration_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("exploration", __name__)

    @blueprint.get("/api/data-exploration")
    def data_exploration():
        hotel_id = request.args.get("hotel_id") or None
        try:
            payload = container.data_exploration.explore(hotel_id)
            return jsonify(payload)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @blueprint.get("/api/model-exploration/meta")
    def model_meta():
        try:
            return jsonify(container.model_exploration.meta())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @blueprint.get("/api/model-exploration/tree")
    def model_tree():
        try:
            target_index = int(request.args.get("target_index", 0))
            tree_number = int(request.args.get("tree_number", 1))
            return jsonify(container.model_exploration.tree(target_index, tree_number))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @blueprint.post("/api/model-exploration/predict")
    def model_predict():
        payload = request.get_json(force=True) or {}
        try:
            result = container.model_exploration.predict(
                hotel_id=payload.get("hotel_id"),
                feature_overrides=payload.get("feature_overrides") or {},
            )
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return blueprint