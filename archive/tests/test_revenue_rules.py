"""Tests règles revenus Excel 1→4."""

from __future__ import annotations

import pytest

from rod_ia.api.dependencies import build_container
from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.rules.revenue_rules import RodRevenueRules


@pytest.fixture
def container():
    return build_container()


@pytest.fixture
def revenue_rules(container) -> RodRevenueRules:
    return container.rod_simulator.revenue_rules


def test_rule1_pivot_simply_matches_excel(revenue_rules, container):
    """Pilote SIMPLY (129 ch) → CA mensuel 720 €."""
    req = RodSimulationRequest.from_dict(
        {
            "operating": {
                "nb_chambres": 129,
                "taux_occupation": 0.80,
                "guests_per_chambre": 1.7,
            },
        }
    )
    req = container.simulation_orchestrator.request_for_concept(req, "SIMPLY")
    result = revenue_rules.compute(req, "SIMPLY")
    assert result.ca_ht_mensuel_base == pytest.approx(720.0, abs=1.0)


def test_rule2_mix_adjustment_increases_fb_share(revenue_rules, container):
    """Écart mix +30 pts F&B augmente le CA F&B (Règle 2)."""
    base_req = RodSimulationRequest.from_dict(
        {
            "operating": {"nb_chambres": 129, "taux_occupation": 0.80, "guests_per_chambre": 1.7},
        }
    )
    ref_req = container.simulation_orchestrator.request_for_concept(base_req, "SIMPLY")
    ref = revenue_rules.compute(ref_req, "SIMPLY")

    custom = RodSimulationRequest.from_dict(
        {
            "operating": {"nb_chambres": 129, "taux_occupation": 0.80, "guests_per_chambre": 1.7},
            "store": {"m_lin": 6, "mix": {"fb_share": 0.7, "non_fb_share": 0.3}},
        }
    )
    custom_req = container.simulation_orchestrator.request_for_concept(custom, "SIMPLY")
    custom_result = revenue_rules.compute(custom_req, "SIMPLY")

    assert custom_result.breakdown["mix_steps_fb"] == pytest.approx(3.0, abs=0.1)
    assert custom_result.ca_ht_mensuel_base > ref.ca_ht_mensuel_base


def test_rule3_excluded_category_reduces_ca(revenue_rules, container):
    """Désactivation besoins clients réduit le CA (Règle 3 relative au pilote)."""
    full_req = RodSimulationRequest.from_dict(
        {
            "operating": {"nb_chambres": 129, "taux_occupation": 0.80, "guests_per_chambre": 1.7},
        }
    )
    full = container.simulation_orchestrator.request_for_concept(full_req, "SIMPLY")
    full_result = revenue_rules.compute(full, "SIMPLY")

    partial = RodSimulationRequest.from_dict(
        {
            "operating": {"nb_chambres": 129, "taux_occupation": 0.80, "guests_per_chambre": 1.7},
            "client_profile": {
                "client_needs": {
                    "fb_soft_drinks": False,
                    "fb_alcohol": False,
                    "fb_salty_snacks": False,
                    "fb_salty_meals": False,
                    "fb_sweet_snacks": False,
                    "fb_sweet_desserts": False,
                    "fb_gourmet": False,
                    "nfb_sos": False,
                    "nfb_hygiene": False,
                    "nfb_cosmetics": False,
                    "nfb_kids": False,
                    "nfb_apparel": False,
                    "nfb_accessories": False,
                    "nfb_souvenirs": False,
                }
            },
        }
    )
    partial_req = container.simulation_orchestrator.request_for_concept(partial, "SIMPLY")
    partial_result = revenue_rules.compute(partial_req, "SIMPLY")

    assert partial_result.ca_ht_mensuel_base < full_result.ca_ht_mensuel_base
    assert partial_result.breakdown["rule3_delta_fb"] < 0


def test_rule4_m_lin_adjustment(revenue_rules, container):
    """m_lin inférieur au pilote réduit le CA (Règle 4)."""
    base_req = RodSimulationRequest.from_dict(
        {
            "operating": {"nb_chambres": 129, "taux_occupation": 0.80, "guests_per_chambre": 1.7},
            "corner": {"m_lin": 6.0},
        }
    )
    pivot = container.simulation_orchestrator.request_for_concept(base_req, "SIMPLY")
    pivot_ca = revenue_rules.compute(pivot, "SIMPLY").ca_ht_mensuel_base

    small = RodSimulationRequest.from_dict(
        {
            "operating": {"nb_chambres": 129, "taux_occupation": 0.80, "guests_per_chambre": 1.7},
            "corner": {"m_lin": 3.0},
        }
    )
    small_req = container.simulation_orchestrator.request_for_concept(small, "SIMPLY")
    small_ca = revenue_rules.compute(small_req, "SIMPLY").ca_ht_mensuel_base

    assert small_ca < pivot_ca
    assert revenue_rules.compute(small_req, "SIMPLY").breakdown["m_lin_diff"] == pytest.approx(-3.0)