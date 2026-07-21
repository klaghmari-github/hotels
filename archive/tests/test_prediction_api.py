"""Tests API REST de prédiction."""

from __future__ import annotations

import pytest

from rod_ia.api.api_factory import create_api_app
from rod_ia.api.dependencies import build_container
from rod_ia.domain.services.prediction_api_service import PredictionApiService


@pytest.fixture
def client():
    app = create_api_app(build_container())
    return app.test_client()


@pytest.fixture
def service():
    container = build_container()
    return PredictionApiService(
        enrich_service=container.enrich_service,
        feature_store=container.feature_store,
        identity_registry=container.identity_registry,
        reference=container.reference_repository,
        orchestrator=container.simulation_orchestrator,
    )


def _nice_payload() -> dict:
    return {
        "identity": {
            "hotel_name": "Ibis budget Nice",
            "city": "Nice",
            "brand": "IBIS_BUDGET",
        },
        "operating": {
            "nb_chambres": 129,
            "taux_occupation": 0.80,
            "guests_per_chambre": 1.7,
        },
        "corner": {"m_lin": 6},
    }


def test_predict_endpoint_returns_json(client):
    res = client.post("/api/v1/predict", json=_nice_payload())
    assert res.status_code == 200
    data = res.get_json()
    assert "input" in data
    assert "predictions" in data
    assert "recommendation" in data
    assert "context" in data


def test_predict_echoes_input_with_enrichment(client):
    res = client.post("/api/v1/predict", json=_nice_payload())
    data = res.get_json()
    assert data["input"]["identity"]["hotel_name"] == "Ibis budget Nice"
    assert data["input"]["identity"].get("hotel_id")
    assert "enriched" in data["input"]


def test_predict_three_concepts_with_monthly(service):
    response = service.predict(_nice_payload())
    assert set(response.predictions.keys()) == {"SIMPLY", "LIBERTY", "CONNECTED"}
    for concept, pred in response.predictions.items():
        assert pred.ca_annuel > 0
        assert pred.nbr_ventes_annuel > 0
        assert len(pred.monthly) == 12
        assert pred.monthly[0].month == 1
        assert pred.marge_annuelle != 0
        assert concept == pred.concept


def test_predict_context_has_proximity_and_rod_rules(service):
    response = service.predict(_nice_payload())
    ctx = response.context
    assert ctx["hotel_id"]
    assert "proximity" in ctx
    assert "beach_km" in ctx["proximity"]
    assert "commerce_fb" in ctx["proximity"]
    assert ctx["rod_rules"]["concepts"]["SIMPLY"]["pivot_nb_chambres"] == 129.0
    assert ctx["registry_hotels_count"] > 0


def test_predict_recommendation_present(service):
    response = service.predict(_nice_payload())
    assert response.recommendation["concept"] in {"SIMPLY", "LIBERTY", "CONNECTED"}
    assert response.recommendation["reason"]


def test_predict_rejects_empty_body(client):
    res = client.post("/api/v1/predict", json={})
    assert res.status_code == 400


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"