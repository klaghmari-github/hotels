"""Entrainement du modele IA — pipeline autonome ou relance si artifact absent."""

from __future__ import annotations

import argparse
import json

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.services.model_trainer import ModelTrainer
from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline


def build_dataset(settings, evaluation_year: int) -> int:
    registry = HotelIdentityRegistry(settings.identity_registry_path)
    reference = ReferenceRepository(settings.rod_reference_path)
    feature_store = FeatureStoreRepository(settings.feature_store_dir)
    pipeline = SalesTargetsPipeline(
        sales_path=settings.sales_csv_path,
        identity_registry=registry,
        output_dir=settings.data_processed_dir,
        feature_store=feature_store,
        evaluation_year=evaluation_year,
        recap_path=settings.rod_recap_path,
        recap_output_dir=settings.rod_recap_reference_dir,
        reference_repository=reference,
    )
    dataset = pipeline.build_training_dataset()
    pipeline.persist_hotel_targets()
    return len(dataset)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Entraine model.joblib a partir du dataset processed (holdout exclu du fit)."
    )
    parser.add_argument(
        "--evaluation-year",
        "--validation-year",
        type=int,
        default=2026,
        dest="evaluation_year",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reentrainer meme si model.joblib existe deja",
    )
    parser.add_argument(
        "--rebuild-dataset",
        action="store_true",
        help="Regenerer X_descriptive.csv et y_targets.csv avant l entrainement",
    )
    args = parser.parse_args()

    settings = get_settings()
    trainer = ModelTrainer(settings.data_processed_dir, settings.artifacts_dir)

    if args.rebuild_dataset or not trainer.dataset_ready():
        print("Construction du dataset d entrainement...")
        n = build_dataset(settings, args.evaluation_year)
        print(f"Dataset: {n} hotels → {settings.data_processed_dir}")

    meta = trainer.ensure_trained(force=args.force)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"Modele → {trainer.model_path}")


if __name__ == "__main__":
    main()