"""Tests simulation 3 concepts — valeurs non nulles et store en sortie."""

from __future__ import annotations

import pytest

from rod_ia.api.dependencies import build_container
from rod_ia.domain.models.simulation import RodSimulationRequest


@pytest.fixture
def container():
    return build_container()


def _nice_request() -> RodSimulationRequest:
    return RodSimulationRequest.from_dict(
        {
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
        }
    )


def test_rod_simulation_non_zero_for_nice(container):
    full = container.simulation_orchestrator.simulate_all(_nice_request())
    simply = full.rod_by_concept["SIMPLY"]

    assert simply.ca_annuel > 0
    assert simply.nbr_ventes_annuel > 0
    assert simply.cout_annuel > 0
    assert simply.marge_annuelle != 0
    assert simply.store_config["concept"] == "SIMPLY"
    assert simply.store_config["m_lin"] == 6
    assert simply.breakdown["techno_monthly"] > 0
    assert simply.breakdown["display_mode"] == "monthly_average"


def test_rod_monthly_average_flat_line(container):
    """Excel SIMULATEUR * affiche un mois moyen — même valeur sur les 12 mois."""
    full = container.simulation_orchestrator.simulate_all(_nice_request())
    simply = full.rod_by_concept["SIMPLY"]
    cas = [m.ca for m in simply.monthly]
    ventes = [m.nbr_ventes for m in simply.monthly]
    assert len(set(round(c, 2) for c in cas)) == 1
    assert len(set(round(v, 2) for v in ventes)) == 1
    assert simply.ca_mensuel_moyen == pytest.approx(cas[0], rel=1e-6)
    assert simply.ca_annuel == pytest.approx(simply.ca_mensuel_moyen * 12, rel=1e-6)


def test_rod_marge_produit_matches_excel_formula(container):
    """E132/E133 au pilote SIMPLY Nice : marge produit mensuelle ≈ 386 €."""
    full = container.simulation_orchestrator.simulate_all(_nice_request())
    simply = full.rod_by_concept["SIMPLY"]
    assert simply.breakdown["marge_produit_mensuelle"] == pytest.approx(386.03, abs=2.0)


def test_three_concepts_returned(container):
    full = container.simulation_orchestrator.simulate_all(_nice_request())
    assert set(full.rod_by_concept.keys()) == {"SIMPLY", "LIBERTY", "CONNECTED"}
    assert set(full.ai_by_concept.keys()) == {"SIMPLY", "LIBERTY", "CONNECTED"}
    assert full.recommended_concept in full.rod_by_concept


def test_ai_pipeline_has_steps(container):
    full = container.simulation_orchestrator.simulate_all(_nice_request())
    reco = full.recommended_concept
    ai = full.ai_by_concept[reco]
    steps = [s["step"] for s in ai.pipeline]
    assert "predict_ventes" in steps
    assert "ventes_to_pct" in steps
    assert "pct_to_ca" in steps
    assert "ca_to_marge_produit" in steps
    assert "apply_couts" in steps
    assert "marge_nette" in steps
    assert ai.cout_annuel > 0


def test_connected_higher_ca_than_simply(container):
    full = container.simulation_orchestrator.simulate_all(_nice_request())
    assert full.rod_by_concept["CONNECTED"].ca_annuel > full.rod_by_concept["SIMPLY"].ca_annuel


def test_rod_ca_differs_by_hotel_size(container):
    """Chaque hôtel doit avoir un CA ROD distinct (nb chambres / clients hébergés)."""
    nice = container.simulation_orchestrator.simulate_all(_nice_request())
    strasbourg = container.simulation_orchestrator.simulate_all(
        RodSimulationRequest.from_dict(
            {
                "identity": {"hotel_name": "Ibis budget Strasbourg", "city": "Strasbourg"},
                "operating": {"nb_chambres": 97, "taux_occupation": 0.75, "guests_per_chambre": 1.7},
            }
        )
    )
    nice_ca = nice.rod_by_concept["SIMPLY"].ca_mensuel_moyen
    stras_ca = strasbourg.rod_by_concept["SIMPLY"].ca_mensuel_moyen
    assert nice_ca != pytest.approx(stras_ca, rel=0.01)
    assert nice_ca > stras_ca


def test_validation_rule_of_three(container):
    from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline
    from rod_ia.config.settings import get_settings
    from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry

    settings = get_settings()
    sp = SalesTargetsPipeline(
        settings.sales_csv_path,
        HotelIdentityRegistry(settings.identity_registry_path),
        settings.data_processed_dir,
        validation_year=2026,
    )
    cov = sp.validation_coverage_by_hotel()
    if cov.empty:
        pytest.skip("Pas de ventes 2026")
    row = cov.iloc[0]
    assert row["n_months_present"] < 12
    assert row["actual_ca_annualized"] == pytest.approx(
        row["actual_ca_period"] * 12 / row["n_months_present"], rel=1e-6
    )