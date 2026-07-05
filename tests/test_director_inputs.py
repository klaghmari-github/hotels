"""Tests saisies directeur — mapping besoins clients → store."""

from __future__ import annotations

from rod_ia.domain.models.director_inputs import (
    ClientProfile,
    excluded_gammes_from_needs,
    mix_from_client_needs,
)
from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.services.director_input_mapper import DirectorInputMapper


def test_excluded_gammes_when_need_disabled():
    needs = {"fb_alcohol": False, "nfb_sos": True}
    excluded = excluded_gammes_from_needs(needs)
    assert "ALCOOL" in excluded
    assert "SOS" not in excluded


def test_mix_from_client_needs():
    needs = {f"fb_{i}": True for i in range(3)}
    needs.update({f"nfb_{i}": True for i in range(1)})
    fb, nf = mix_from_client_needs(needs)
    assert fb == 0.75
    assert nf == 0.25


def test_store_overrides_use_corner_m_lin():
    request = RodSimulationRequest.from_dict({
        "identity": {"hotel_name": "Test"},
        "operating": {"nb_chambres": 80, "taux_occupation": 0.65},
        "corner": {"m_lin": 9.0},
        "client_profile": {
            "client_needs": {"fb_alcohol": False, "nfb_sos": True},
        },
    })
    store = DirectorInputMapper.apply_store_overrides(
        request, default_fb=0.7, default_nf=0.3, default_m_lin=6.0, concept="LIBERTY"
    )
    assert store.m_lin == 9.0
    assert "ALCOOL" in store.excluded_categories


def test_m_lin_changes_rod_simulation():
    """4 m lin vs 6 m lin doit modifier le CA ROD."""
    from rod_ia.api.dependencies import build_container

    c = build_container()
    base = {
        "identity": {"hotel_name": "Ibis budget Nice", "city": "Nice", "brand": "IBIS_BUDGET"},
        "operating": {"nb_chambres": 129, "taux_occupation": 0.80, "guests_per_chambre": 1.7},
    }
    req4 = RodSimulationRequest.from_dict({**base, "store": {"m_lin": 4}})
    req6 = RodSimulationRequest.from_dict({**base, "store": {"m_lin": 6}})
    r4 = c.simulation_orchestrator.simulate_all(req4).rod_by_concept["SIMPLY"]
    r6 = c.simulation_orchestrator.simulate_all(req6).rod_by_concept["SIMPLY"]
    assert r4.ca_annuel != r6.ca_annuel
    assert r4.m_lin == 4
    assert r6.m_lin == 6