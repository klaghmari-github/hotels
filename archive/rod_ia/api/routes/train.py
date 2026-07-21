"""Route de reentrainement manuel du modele IA."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from rod_ia.api.dependencies import AppContainer
from rod_ia.domain.services.model_trainer import ModelTrainer


def create_train_blueprint(container: AppContainer) -> Blueprint:
    blueprint = Blueprint("train", __name__)

    @blueprint.get("/api/model/status")
    def model_status():
        trainer = ModelTrainer(
            container.settings.data_processed_dir,
            container.settings.artifacts_dir,
        )
        return jsonify(
            {
                "dataset_ready": trainer.dataset_ready(),
                "model_present": trainer.is_model_present(),
                "artifacts_complete": trainer.artifacts_complete(),
                "model_path": str(trainer.model_path),
                "meta": trainer.load_meta(),
            }
        )

    @blueprint.post("/api/model/train")
    def model_train():
        force = bool((request.get_json(silent=True) or {}).get("force", False))
        trainer = ModelTrainer(
            container.settings.data_processed_dir,
            container.settings.artifacts_dir,
        )
        try:
            meta = trainer.ensure_trained(force=force)
            container.ai_predictor.model = None
            container.ai_predictor._load()
            return jsonify({"ok": True, "meta": meta})
        except FileNotFoundError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    return blueprint