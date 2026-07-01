"""Optimiseur de configuration corner sous contraintes figées."""

from __future__ import annotations

from copy import deepcopy
from itertools import product

from rod_ia.domain.models.simulation import RodSimulationRequest


class RodOptimizer:
    """Recherche la meilleure configuration en respectant ``locked_fields``."""

    def __init__(self, simulator) -> None:
        self.simulator = simulator

    def optimize(
        self,
        request: RodSimulationRequest,
        concepts: tuple[str, ...] = ("SIMPLY", "LIBERTY", "CONNECTED"),
        m_lins: tuple[float, ...] = (1, 2, 3, 4, 5, 6, 7, 8),
        fb_shares: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9),
    ) -> dict:
        locked = set(request.store.locked_fields)
        best_result = None
        best_request = None

        for concept, m_lin, fb_share in product(concepts, m_lins, fb_shares):
            candidate = deepcopy(request)
            if "concept" not in locked:
                candidate.store.concept = concept
            if "m_lin" not in locked:
                candidate.store.m_lin = float(m_lin)
            if "fb_share" not in locked:
                candidate.store.mix.fb_share = float(fb_share)
                candidate.store.mix.non_fb_share = float(1.0 - fb_share)

            result = self.simulator.simulate(candidate)
            if best_result is None or result.marge_annuelle > best_result.marge_annuelle:
                best_result = result
                best_request = candidate

        return {
            "request": best_request.store.to_dict() if best_request else None,
            "result": best_result.to_dict() if best_result else None,
        }