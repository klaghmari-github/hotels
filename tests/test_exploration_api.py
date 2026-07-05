"""Tests API exploration donnees et modele."""

from __future__ import annotations

import pytest

from rod_ia.api.app_factory import create_app
from rod_ia.api.dependencies import build_container


@pytest.fixture
def client():
    app = create_app(build_container())
    return app.test_client()


def test_data_exploration_returns_stages(client):
    res = client.get("/api/data-exploration")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data.get("stages", [])) == 7
    assert data["stages"][0]["id"] == "source"


def test_model_exploration_meta(client):
    res = client.get("/api/model-exploration/meta")
    assert res.status_code == 200
    data = res.get_json()
    assert "n_outputs" in data
    assert "targets" in data


def test_model_tree_and_predict(client):
    meta = client.get("/api/model-exploration/meta").get_json()
    if not meta.get("model_available"):
        pytest.skip("Modele absent")
    tree = client.get("/api/model-exploration/tree?target_index=0&tree_number=1")
    assert tree.status_code == 200
    assert "tree" in tree.get_json()
    pred = client.post(
        "/api/model-exploration/predict",
        json={"hotel_id": "ibis-budget-nice", "feature_overrides": {}},
    )
    assert pred.status_code == 200
    body = pred.get_json()
    assert body["annual_totals"]["ca_annuel"] >= 0
    assert len(body["monthly_global"]) == 12