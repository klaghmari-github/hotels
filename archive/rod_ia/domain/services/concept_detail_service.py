"""Panneau détail solution — revenus ROD + coûts lease/buy."""

from __future__ import annotations

from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.rules.financing_cost_rules import (
    AGENCEMENT_BUY_EUR_M2,
    AGENCEMENT_LEASE_EUR_M2_MONTH,
    CONCEPT_EQUIPMENT,
    ConceptFinancing,
    FinancingCostRules,
)
from rod_ia.domain.services.director_input_mapper import DirectorInputMapper
from rod_ia.domain.services.simulation_orchestrator import SimulationOrchestrator


class ConceptDetailService:
    """Simule le détail d'un concept avec financement lease ou buy."""

    def __init__(
        self,
        orchestrator: SimulationOrchestrator,
        financing_rules: FinancingCostRules,
    ) -> None:
        self._orchestrator = orchestrator
        self._financing = financing_rules

    def simulate_detail(
        self,
        base_request: RodSimulationRequest,
        concept: str,
        financing: ConceptFinancing,
    ) -> dict:
        prepared = DirectorInputMapper.prepare_request(base_request)
        _, rod = self._orchestrator.simulate_concept(prepared, concept)

        bd = rod.breakdown or {}
        breakdown = self._financing.compute(
            concept,
            rod.m_lin,
            financing,
            marge_produit_mensuelle=float(bd.get("marge_produit_mensuelle", 0.0)),
            ca_ht_mensuel=float(rod.ca_mensuel_moyen or 0.0),
            ca_fb_ht_mensuel=float(bd.get("ca_fb_ht_mensuel", 0.0)),
            ca_nf_ht_mensuel=float(bd.get("ca_nf_ht_mensuel", 0.0)),
        )

        return {
            "concept": concept,
            "m_lin": rod.m_lin,
            "rod_summary": {
                "ca_mensuel_moyen": rod.ca_mensuel_moyen,
                "marge_annuelle_rod": rod.marge_annuelle,
            },
            "financing": financing.to_dict(),
            "costs": breakdown.to_dict(),
            "catalog": {
                "agencement_lease_eur_m2_month": AGENCEMENT_LEASE_EUR_M2_MONTH,
                "agencement_buy_eur_m2": AGENCEMENT_BUY_EUR_M2,
                "equipment": CONCEPT_EQUIPMENT.get(concept, {}),
            },
        }