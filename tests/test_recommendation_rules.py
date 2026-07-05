"""Tests règles recommandation concept — Excel REGLES POUR RECO."""

from __future__ import annotations

from rod_ia.api.dependencies import build_container
from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.rules.recommendation_rules import RodRecommendationRules


def test_small_hotel_only_simply():
    rules = RodRecommendationRules()
    req = RodSimulationRequest.from_dict(
        {"operating": {"nb_chambres": 40, "taux_occupation": 0.75, "guests_per_chambre": 1.7}}
    )
    allowed, _, _ = rules.allowed_concepts(req)
    assert allowed == ["SIMPLY"]


def test_large_hotel_liberty_and_connected():
    rules = RodRecommendationRules()
    req = RodSimulationRequest.from_dict(
        {"operating": {"nb_chambres": 305, "taux_occupation": 0.75, "guests_per_chambre": 1.8}}
    )
    allowed, _, _ = rules.allowed_concepts(req)
    assert "CONNECTED" in allowed
    assert "LIBERTY" in allowed
    assert "SIMPLY" not in allowed


def test_ibis_budget_mid_size_includes_simply():
    rules = RodRecommendationRules()
    req = RodSimulationRequest.from_dict(
        {
            "identity": {"brand": "IBIS BUDGET"},
            "operating": {"nb_chambres": 129, "taux_occupation": 0.78, "guests_per_chambre": 1.7},
        }
    )
    allowed, _, _ = rules.allowed_concepts(req)
    assert "SIMPLY" in allowed
    assert "CONNECTED" in allowed


def test_large_hotel_without_nfb_only_connected():
    rules = RodRecommendationRules()
    req = RodSimulationRequest.from_dict(
        {
            "operating": {"nb_chambres": 200, "taux_occupation": 0.75, "guests_per_chambre": 1.8},
            "client_profile": {
                "client_needs": {
                    "nfb_cosmetics": False,
                    "nfb_kids": False,
                    "nfb_apparel": False,
                    "nfb_accessories": False,
                    "nfb_souvenirs": False,
                }
            },
        }
    )
    allowed, _, warnings = rules.allowed_concepts(req)
    assert allowed == ["CONNECTED"]
    assert any("LIBERTY" in w for w in warnings)