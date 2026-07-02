"""Orchestration SIMPLY / LIBERTY / CONNECTED — store config en sortie."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

from rod_ia.domain.models.simulation import (
    FullSimulationResponse,
    RodSimulationRequest,
    SimulationResult,
)
from rod_ia.domain.models.store import CategoryMix, StoreConfiguration
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.recommendation_rules import RodRecommendationRules
from rod_ia.domain.services.ai_pnl_service import AIPnlService
from rod_ia.domain.services.rod_simulator import RodSimulator


class SimulationOrchestrator:
    """Compare les 3 concepts ROD + IA et recommande la meilleure marge nette."""

    CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")

    def __init__(
        self,
        reference: ReferenceRepository,
        rod_simulator: RodSimulator,
        ai_pnl: AIPnlService,
        recommendation_rules: RodRecommendationRules,
    ) -> None:
        self._reference = reference
        self._rod = rod_simulator
        self._ai = ai_pnl
        self._reco = recommendation_rules

    def build_store_for_concept(
        self, request: RodSimulationRequest, concept: str
    ) -> StoreConfiguration:
        """Construit la configuration store proposée pour un concept (sortie)."""
        key = f"concepts.{concept}"
        mix_fb = float(self._reference.get(f"{key}.mix_fb", 0.7) or 0.7)
        mix_nf = float(self._reference.get(f"{key}.mix_nf", 0.3) or 0.3)
        m_lin = float(self._reference.get(f"{key}.pivot_m_lin", 2.0) or 2.0)

        excluded = list(request.constraints.get("excluded_categories") or [])
        if request.store and request.store.excluded_categories:
            excluded = list(request.store.excluded_categories)
        locked = list(request.constraints.get("locked_fields") or [])
        if request.store and request.store.locked_fields:
            locked = list(request.store.locked_fields)

        return StoreConfiguration(
            concept=concept,
            m_lin=m_lin,
            mix=CategoryMix(fb_share=mix_fb, non_fb_share=mix_nf).normalize(),
            excluded_categories=excluded,
            locked_fields=locked,
        )

    def request_for_concept(
        self, request: RodSimulationRequest, concept: str
    ) -> RodSimulationRequest:
        candidate = deepcopy(request)
        candidate.store = self.build_store_for_concept(request, concept)
        return candidate

    def simulate_all(self, request: RodSimulationRequest) -> FullSimulationResponse:
        warnings: list[str] = []
        rod_by_concept: dict[str, SimulationResult] = {}
        ai_by_concept: dict[str, SimulationResult] = {}

        allowed, _, reco_warnings = self._reco.allowed_concepts(request, self._reference)
        warnings.extend(reco_warnings)

        for concept in self.CONCEPTS:
            req = self.request_for_concept(request, concept)
            rod_by_concept[concept] = self._rod.simulate(req, concept)
            ai_by_concept[concept] = self._ai.predict_pnl(req, concept)

        recommended, best_margin, reason = self._reco.recommend(rod_by_concept, allowed)
        return FullSimulationResponse(
            rod_by_concept=rod_by_concept,
            ai_by_concept=ai_by_concept,
            recommended_concept=recommended,
            best_margin_concept=best_margin,
            recommendation_reason=reason,
            warnings=warnings,
        )

    def simulate_concept(
        self,
        request: RodSimulationRequest,
        concept: str,
        *,
        m_lin: float | None = None,
        fb_share: float | None = None,
    ) -> tuple[RodSimulationRequest, SimulationResult]:
        """Simulation unitaire (optimiseur)."""
        req = self.request_for_concept(request, concept)
        if m_lin is not None:
            req.store.m_lin = float(m_lin)
        if fb_share is not None:
            req.store.mix.fb_share = float(fb_share)
            req.store.mix.non_fb_share = float(1.0 - fb_share)
        return req, self._rod.simulate(req, concept)