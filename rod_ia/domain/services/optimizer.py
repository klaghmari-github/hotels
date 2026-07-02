"""Optimiseur de configuration corner sous contraintes figées."""

from __future__ import annotations

from copy import deepcopy
from itertools import product

from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.services.simulation_orchestrator import SimulationOrchestrator


class RodOptimizer:
    """Recherche la meilleure configuration en respectant ``locked_fields``."""

    def __init__(self, orchestrator: SimulationOrchestrator) -> None:
        self._orchestrator = orchestrator

    def optimize(
        self,
        request: RodSimulationRequest,
        concepts: tuple[str, ...] = ("SIMPLY", "LIBERTY", "CONNECTED"),
        m_lins: tuple[float, ...] = (2, 4, 6, 8, 10),
        fb_shares: tuple[float, ...] = (0.4, 0.5, 0.6, 0.7, 0.8),
    ) -> dict:
        base = deepcopy(request)
        locked = set()
        if base.store:
            locked = set(base.store.locked_fields)
        locked.update(base.constraints.get("locked_fields") or [])

        best_result = None
        best_request = None

        for concept, m_lin, fb_share in product(concepts, m_lins, fb_shares):
            if "concept" in locked and base.store and base.store.concept != concept:
                continue

            req, result = self._orchestrator.simulate_concept(
                base,
                concept,
                m_lin=None if "m_lin" in locked else float(m_lin),
                fb_share=None if "fb_share" in locked else float(fb_share),
            )
            if best_result is None or result.marge_annuelle > best_result.marge_annuelle:
                best_result = result
                best_request = req

        return {
            "request": best_request.store.to_dict() if best_request and best_request.store else None,
            "result": best_result.to_dict() if best_result else None,
            "recommended_concept": best_result.concept if best_result else None,
        }