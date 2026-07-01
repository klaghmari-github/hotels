"""CLI — construit le dataset ML avec colonnes ``d_`` et ``t_``."""

from __future__ import annotations

import argparse

from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.ml_dataset_builder import MLDatasetBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Construire le dataset ML ROD-IA")
    parser.add_argument("--exclude-year", type=int, default=2026)
    args = parser.parse_args()

    settings = get_settings()
    registry = HotelIdentityRegistry(settings.identity_registry_path)
    builder = MLDatasetBuilder(
        sales_path=settings.sales_csv_path,
        identity_registry=registry,
        output_dir=settings.data_processed_dir,
    )
    dataset = builder.build(exclude_year=args.exclude_year)
    print(f"Dataset construit: {len(dataset)} hôtels → {settings.data_processed_dir}")


if __name__ == "__main__":
    main()