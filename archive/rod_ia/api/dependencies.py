"""Injection de dépendances — composition racine de l'application."""

from __future__ import annotations

from dataclasses import dataclass

from rod_ia.config.settings import Settings, get_settings
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.cost_rules import RodCostRules
from rod_ia.domain.rules.financing_cost_rules import FinancingCostRules
from rod_ia.domain.rules.recommendation_rules import RodRecommendationRules
from rod_ia.domain.rules.revenue_rules import RodRevenueRules
from rod_ia.domain.services.ai_pnl_service import AIPnlService
from rod_ia.domain.services.concept_detail_service import ConceptDetailService
from rod_ia.domain.services.ai_predictor import AIRodRevenuePredictor
from rod_ia.domain.services.hotel_feature_loader import HotelFeatureLoader
from rod_ia.domain.services.enrich_hotel import EnrichHotelService
from rod_ia.domain.services.data_exploration_service import DataExplorationService
from rod_ia.domain.services.model_exploration_service import ModelExplorationService
from rod_ia.domain.services.model_interpretation_service import ModelInterpretationService
from rod_ia.domain.services.model_trainer import ModelTrainer
from rod_ia.domain.services.optimizer import RodOptimizer
from rod_ia.domain.services.rod_simulator import RodSimulator
from rod_ia.domain.services.simulation_orchestrator import SimulationOrchestrator


@dataclass
class AppContainer:
    """Regroupe les services partagés par les routes Flask."""

    settings: Settings
    identity_registry: HotelIdentityRegistry
    feature_store: FeatureStoreRepository
    reference_repository: ReferenceRepository
    enrich_service: EnrichHotelService
    rod_simulator: RodSimulator
    ai_predictor: AIRodRevenuePredictor
    ai_pnl: AIPnlService
    simulation_orchestrator: SimulationOrchestrator
    optimizer: RodOptimizer
    model_interpretation: ModelInterpretationService
    data_exploration: DataExplorationService
    model_exploration: ModelExplorationService
    concept_detail: ConceptDetailService


def build_container(settings: Settings | None = None) -> AppContainer:
    settings = settings or get_settings()
    identity_registry = HotelIdentityRegistry(settings.identity_registry_path)
    feature_store = FeatureStoreRepository(settings.feature_store_dir)
    reference_repository = ReferenceRepository(settings.rod_reference_path)

    revenue_rules = RodRevenueRules(reference_repository)
    cost_rules = RodCostRules(reference_repository)
    recommendation_rules = RodRecommendationRules()
    rod_simulator = RodSimulator(revenue_rules, cost_rules, recommendation_rules)
    hotel_features = HotelFeatureLoader(settings.data_processed_dir)
    trainer = ModelTrainer(settings.data_processed_dir, settings.artifacts_dir)
    if trainer.dataset_ready() and not trainer.is_model_present():
        trainer.ensure_trained()
    ai_predictor = AIRodRevenuePredictor(settings.artifacts_dir, hotel_features)
    ai_pnl = AIPnlService(ai_predictor, revenue_rules, cost_rules)
    simulation_orchestrator = SimulationOrchestrator(
        reference_repository,
        rod_simulator,
        ai_pnl,
        recommendation_rules,
    )
    model_interpretation = ModelInterpretationService(
        ai_predictor,
        ai_pnl,
        simulation_orchestrator,
        recommendation_rules,
        settings.data_processed_dir,
        settings.artifacts_dir,
    )
    financing_rules = FinancingCostRules(reference_repository)
    concept_detail = ConceptDetailService(simulation_orchestrator, financing_rules)
    data_exploration = DataExplorationService(
        settings, identity_registry, feature_store
    )
    model_exploration = ModelExplorationService(ai_predictor, settings.data_processed_dir)

    return AppContainer(
        settings=settings,
        identity_registry=identity_registry,
        feature_store=feature_store,
        reference_repository=reference_repository,
        enrich_service=EnrichHotelService(feature_store, identity_registry, settings),
        rod_simulator=rod_simulator,
        ai_predictor=ai_predictor,
        ai_pnl=ai_pnl,
        simulation_orchestrator=simulation_orchestrator,
        optimizer=RodOptimizer(simulation_orchestrator),
        model_interpretation=model_interpretation,
        data_exploration=data_exploration,
        model_exploration=model_exploration,
        concept_detail=concept_detail,
    )