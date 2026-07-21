"""Pipeline d'initialisation — extraction, targets, entraînement, évaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rod_ia.api.dependencies import build_container
from rod_ia.config.settings import get_settings
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.services.model_evaluation_service import ModelEvaluationService
from rod_ia.domain.services.model_trainer import ModelTrainer
from rod_ia.domain.services.pivot_store_enricher import PivotStoreEnricher
from rod_ia.domain.services.rod_excel_extractor import BrandProjectionsExtractor, RodExcelExtractor
from rod_ia.domain.services.sales_catalog_service import SalesCatalogService
from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline init ROD-IA")
    parser.add_argument(
        "--evaluation-year",
        "--validation-year",
        type=int,
        default=2026,
        dest="evaluation_year",
        help="Année holdout test/évaluation (exclue de l'entraînement, défaut 2026)",
    )
    parser.add_argument("--skip-train", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    registry = HotelIdentityRegistry(settings.identity_registry_path)

    sim_xlsx = next(settings.sources_raw_dir.glob("*Simulateurs*"), None)
    param_xlsx = next(settings.sources_raw_dir.glob("*Param*"), None)
    if sim_xlsx:
        RodExcelExtractor(sim_xlsx, settings.data_reference_dir / "rod_reference.json").extract()
        print(f"ROD références extraites → {settings.data_reference_dir / 'rod_reference.json'}")
    if param_xlsx:
        BrandProjectionsExtractor(param_xlsx, settings.data_reference_dir / "brand_projections.json").extract()
        print(f"Marques / nb hôtels → {settings.data_reference_dir / 'brand_projections.json'}")

    reference = ReferenceRepository(settings.rod_reference_path)
    if not reference.data:
        reference = ReferenceRepository(settings.data_reference_dir / "rod_reference.json")

    container = build_container(settings)
    catalog = SalesCatalogService(settings.sales_csv_path).save_reference(
        settings.data_reference_dir / "sales_catalog.json"
    )
    print(f"Catalogue ventes: {len(catalog.get('gammes', []))} gammes → sales_catalog.json")

    recap_path = settings.rod_recap_path
    if recap_path:
        print(f"Récap ROD détecté → {recap_path}")

    pipeline = SalesTargetsPipeline(
        sales_path=settings.sales_csv_path,
        identity_registry=registry,
        output_dir=settings.data_processed_dir,
        feature_store=container.feature_store,
        evaluation_year=args.evaluation_year,
        recap_path=recap_path,
        recap_output_dir=settings.rod_recap_reference_dir,
        reference_repository=reference,
    )
    dataset = pipeline.build_training_dataset()
    print(f"Dataset train: {len(dataset)} hôtels")

    enricher = PivotStoreEnricher(registry, reference, container.feature_store, pipeline)
    pivot_info = enricher.enrich_all_pivots()
    print(f"Feature store pivots: {pivot_info}")

    trainer = ModelTrainer(settings.data_processed_dir, settings.artifacts_dir)
    if not args.skip_train:
        meta = trainer.ensure_trained(force=True)
        print(f"Modèle entraîné: {meta}")
    elif not trainer.is_model_present():
        print("Attention: --skip-train actif et model.joblib absent.")

    evaluator = ModelEvaluationService(
        pipeline,
        container.simulation_orchestrator,
        registry,
        reference,
        feature_store=container.feature_store,
        output_path=settings.data_processed_dir / "performance_report.json",
        evaluation_year=args.evaluation_year,
    )
    report = evaluator.evaluate()
    print(f"Test/évaluation {args.evaluation_year}: {len(report.rows)} hôtels")
    (settings.data_processed_dir / "performance_report.json").write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()