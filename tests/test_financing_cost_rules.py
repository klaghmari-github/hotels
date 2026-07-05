"""Tests coûts lease vs buy — panneau détail solution."""

from __future__ import annotations

from rod_ia.api.dependencies import build_container
from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.rules.financing_cost_rules import (
    BUY_AMORT_MONTHS,
    ConceptFinancing,
    FinancingCostRules,
)


def _liberty_financing(mode: str) -> ConceptFinancing:
    return ConceptFinancing(
        mode=mode,
        agencement_type="classique",
        equipment_qty={"caisse": 1, "vitrine": 1},
    )


def test_lease_more_expensive_than_buy_monthly():
    """Location mensuelle > achat amorti (même équipement)."""
    rules = FinancingCostRules(build_container().reference_repository)
    base = dict(
        marge_produit_mensuelle=500.0,
        ca_ht_mensuel=400.0,
        ca_fb_ht_mensuel=300.0,
        ca_nf_ht_mensuel=100.0,
    )
    lease = rules.compute("LIBERTY", 8.0, _liberty_financing("lease"), **base)
    buy = rules.compute("LIBERTY", 8.0, _liberty_financing("buy"), **base)
    assert lease.monthly_cost > buy.monthly_cost
    assert lease.equipment_monthly == 263.0  # 250 + 13
    assert buy.amort_months == BUY_AMORT_MONTHS
    assert lease.amort_months == 48


def test_agencement_lease_uses_eur_m2_month():
    rules = FinancingCostRules(build_container().reference_repository)
    lease = rules.compute(
        "LIBERTY",
        10.0,
        _liberty_financing("lease"),
        marge_produit_mensuelle=0.0,
        ca_ht_mensuel=0.0,
        ca_fb_ht_mensuel=0.0,
        ca_nf_ht_mensuel=0.0,
    )
    assert lease.agencement_monthly == 120.0  # 10 m × 12 €/m²/mois


def test_detail_api_lease_buy_diverge():
    c = build_container()
    base = RodSimulationRequest.from_dict({
        "identity": {"hotel_name": "IBIS ALES", "city": "Alès"},
        "operating": {"nb_chambres": 78, "taux_occupation": 0.65, "guests_per_chambre": 1.7},
        "store": {"m_lin": 8},
    })
    lease = c.concept_detail.simulate_detail(
        base, "LIBERTY", _liberty_financing("lease")
    )
    buy = c.concept_detail.simulate_detail(
        base, "LIBERTY", _liberty_financing("buy")
    )
    assert lease["costs"]["monthly_cost"] > buy["costs"]["monthly_cost"]
    assert lease["costs"]["marge_nette_mensuelle"] < buy["costs"]["marge_nette_mensuelle"]