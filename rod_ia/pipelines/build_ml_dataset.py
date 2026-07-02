"""CLI — délègue à ``SalesTargetsPipeline`` (train < validation_year)."""

from __future__ import annotations

import argparse

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Construire le dataset ML ROD-IA")
    parser.add_argument("--validation-year", type=int, default=2026)
    args = parser.parse_args()

    settings = get_settings()
    registry = HotelIdentityRegistry(settings.identity_registry_path)
    feature_store = FeatureStoreRepository(settings.feature_store_dir)
    pipeline = SalesTargetsPipeline(
        sales_path=settings.sales_csv_path,
        identity_registry=registry,
        output_dir=settings.data_processed_dir,
        feature_store=feature_store,
        validation_year=args.validation_year,
        recap_path=settings.rod_recap_path,
        recap_output_dir=settings.rod_recap_reference_dir,
    )
    dataset = pipeline.build_training_dataset()
    pipeline.persist_hotel_targets()
    print(f"Dataset construit: {len(dataset)} hôtels → {settings.data_processed_dir}")


if __name__ == "__main__":
    main()