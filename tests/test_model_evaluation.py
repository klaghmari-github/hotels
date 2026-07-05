"""Tests évaluation performance — best-fit concept et paramètres récap."""

from __future__ import annotations

import pytest

from rod_ia.api.dependencies import build_container
from rod_ia.config.settings import get_settings
from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.director_input_mapper import DirectorInputMapper
from rod_ia.domain.services.model_evaluation_service import ModelEvaluationService
from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline


@pytest.fixture
def container():
    return build_container()


@pytest.fixture
def evaluator(container):
    settings = get_settings()
    registry = HotelIdentityRegistry(settings.identity_registry_path)
    pipeline = SalesTargetsPipeline(
        settings.sales_csv_path,
        registry,
        settings.data_processed_dir,
        feature_store=container.feature_store,
        evaluation_year=2026,
        reference_repository=container.reference_repository,
    )
    return ModelEvaluationService(
        pipeline,
        container.simulation_orchestrator,
        registry,
        container.reference_repository,
        feature_store=container.feature_store,
        evaluation_year=2026,
    )


def test_operating_guests_not_overwritten_by_general_defaults():
    req = RodSimulationRequest.from_dict(
        {
            "operating": {"nb_chambres": 305, "taux_occupation": 0.75, "guests_per_chambre": 1.8},
        }
    )
    prepared = DirectorInputMapper.prepare_request(req)
    assert prepared.operating.guests_per_chambre == pytest.approx(1.8)


def test_evaluation_uses_recap_operating_params(evaluator):
    report = evaluator.evaluate()
    if not report.rows:
        pytest.skip("Pas de ventes 2026")
    nice = next((r for r in report.rows if r.hotel_id == "ibis-budget-nice"), None)
    if nice:
        assert nice.taux_occupation == pytest.approx(0.78, abs=0.02)
        assert nice.guests_per_chambre == pytest.approx(1.7, abs=0.1)


def test_evaluation_best_fit_prefers_simply_for_ibis_budget(evaluator):
    report = evaluator.evaluate()
    if not report.rows:
        pytest.skip("Pas de ventes 2026")
    nice = next((r for r in report.rows if r.hotel_id == "ibis-budget-nice"), None)
    stras = next((r for r in report.rows if r.hotel_id == "ibis-budget-strasbourg"), None)
    if nice:
        assert nice.concept == "SIMPLY"
    if stras:
        assert stras.concept == "SIMPLY"
        assert abs(stras.rod_error_pct) < 25.0


def test_period_label_jan_apr_2026():
    label = ModelEvaluationService._period_label([1, 2, 3, 4], 2026)
    assert label == "janvier–avril 2026 (4 mois)"


def test_to_from_recap_prefers_annuel_over_bas_mois():
    recap = {
        "d_recap_1_informations_generales_donnees_chiffrees_to_annuel_r25": 0.7,
        "d_recap_1_informations_generales_donnees_chiffrees_to_le_plus_bas_mois_r26": 0.78,
        "d_recap_1_informations_generales_donnees_chiffrees_to_le_plus_bas_taux_r27": 0.6,
    }
    assert ModelEvaluationService._to_from_recap(recap) == pytest.approx(0.7)