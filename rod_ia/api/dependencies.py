"""Injection de dépendances — composition racine de l'application."""

from __future__ import annotations

from dataclasses import dataclass

from rod_ia.config.settings import Settings, get_settings
from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.cost_rules import RodCostRules
from rod_ia.domain.rules.recommendation_rules import RodRecommendationRules
from rod_ia.domain.rules.revenue_rules import RodRevenueRules
from rod_ia.domain.services.ai_predictor import AIRodRevenuePredictor
from rod_ia.domain.services.enrich_hotel import EnrichHotelService
from rod_ia.domain.services.optimizer import RodOptimizer
from rod_ia.domain.services.rod_simulator import RodSimulator


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
    optimizer: RodOptimizer


def build_container(settings: Settings | None = None) -> AppContainer:
    settings = settings or get_settings()
    identity_registry = HotelIdentityRegistry(settings.identity_registry_path)
    feature_store = FeatureStoreRepository(settings.feature_store_dir)
    reference_repository = ReferenceRepository(settings.rod_reference_path)

    revenue_rules = RodRevenueRules(reference_repository)
    cost_rules = RodCostRules(reference_repository)
    recommendation_rules = RodRecommendationRules()
    rod_simulator = RodSimulator(revenue_rules, cost_rules, recommendation_rules)

    return AppContainer(
        settings=settings,
        identity_registry=identity_registry,
        feature_store=feature_store,
        reference_repository=reference_repository,
        enrich_service=EnrichHotelService(feature_store, identity_registry, settings),
        rod_simulator=rod_simulator,
        ai_predictor=AIRodRevenuePredictor(settings.artifacts_dir),
        optimizer=RodOptimizer(rod_simulator),
    )