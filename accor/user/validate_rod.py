#!/usr/bin/env python3
"""
Validation des regles ROD du simulateur user.

Usage:
    cd accor && python -m user.validate_rod

Verifie :
  * clients jour/mois
  * impact TO + R1 (API rule1 == RevenueRules)
  * R2–R4 neutres au mix/m_lin pilote + besoins complets
  * reco <50 ch, LIBERTY N-F&B, IBB
  * couts agencement proportionnels a m_lin
  * POST /api/simulate coherent
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from concept_pilote import rule1_ca_by_concept
    from user.models import DEFAULT_CLIENT_NEEDS, HotelOperating, SimulationRequest, StoreConfig
    from user.reference import RodReference
    from user.rules.coeffs import LIBERTY_NFB_NEEDS, RULE3_FB_COEFFS, RULE3_NFB_COEFFS
    from user.rules.costs import CostRules
    from user.rules.recommendation import RecommendationRules
    from user.rules.revenue import RevenueRules
    from user.services.orchestrator import SimulationOrchestrator

    errors: list[str] = []
    ref = RodReference()
    rev = RevenueRules(ref)
    costs = CostRules(ref)
    reco = RecommendationRules()

    # --- clients ---
    op = HotelOperating(100, 0.75, 1.7)
    expect_jour = 100 * 0.75 * 1.7
    expect_mois = expect_jour * 30.5
    if abs(op.clients_jour - expect_jour) > 1e-9 or abs(op.clients_mois - expect_mois) > 1e-9:
        errors.append(f"clients jour/mois incorrects: {op.clients_jour} / {op.clients_mois}")

    # --- R1 API vs engine ---
    n, to, g = 100, 0.75, 1.7
    r1 = rule1_ca_by_concept(nb_chambres=n, taux_occupation=to, guests_per_chambre=g)
    for concept in ("SIMPLY", "LIBERTY", "CONNECTED"):
        key = f"concepts.{concept}"
        pivot_m = float(ref.get(f"{key}.pivot_m_lin") or 6)
        mix_fb = float(ref.get(f"{key}.mix_fb") or 0.7)
        mix_nf = float(ref.get(f"{key}.mix_nf") or 0.3)
        all_true = {
            **{k: True for k in RULE3_FB_COEFFS},
            **{k: True for k in RULE3_NFB_COEFFS},
        }
        req = SimulationRequest.from_dict(
            {
                "identity": {"hotel_brand": "IBIS BUDGET"},
                "operating": {
                    "nb_chambres": n,
                    "taux_occupation": to,
                    "guests_per_chambre": g,
                },
                "client_profile": {"client_needs": all_true},
                "corner": {"m_lin": pivot_m, "mix_fb": mix_fb},
            }
        )
        req.store = StoreConfig(
            concept=concept, m_lin=pivot_m, mix_fb=mix_fb, mix_nf=mix_nf
        )
        full = rev.compute(req, concept)
        api_ca = float(r1["by_concept"][concept]["ca_ht_mensuel"])
        # R2=0 R3=0 R4=0 → full == R1
        if abs(full.ca_ht_mensuel - api_ca) > 0.5:
            errors.append(
                f"{concept}: CA full {full.ca_ht_mensuel:.2f} != R1 API {api_ca:.2f} "
                f"(attendu egal au mix/m_lin pilote + besoins complets)"
            )

    # --- reco ---
    small = SimulationRequest.from_dict(
        {
            "identity": {"hotel_brand": "NOVOTEL"},
            "operating": {"nb_chambres": 40, "taux_occupation": 0.8, "guests_per_chambre": 1.8},
            "client_profile": {
                "client_needs": {
                    **{k: True for k in RULE3_FB_COEFFS},
                    **{k: True for k in RULE3_NFB_COEFFS},
                }
            },
        }
    )
    allowed, _ = reco.allowed_concepts(small)
    if allowed != ["SIMPLY"]:
        errors.append(f"reco n<50 attendu [SIMPLY], got {allowed}")

    needs_no = {
        **{k: True for k in RULE3_FB_COEFFS},
        **{k: True for k in RULE3_NFB_COEFFS},
    }
    for k in LIBERTY_NFB_NEEDS:
        needs_no[k] = False
    mid = SimulationRequest.from_dict(
        {
            "identity": {"hotel_brand": "IBIS"},
            "operating": {"nb_chambres": 100, "taux_occupation": 0.7, "guests_per_chambre": 1.8},
            "client_profile": {"client_needs": needs_no},
        }
    )
    allowed2, _ = reco.allowed_concepts(mid)
    if "LIBERTY" in allowed2:
        errors.append(f"LIBERTY ne doit pas etre autorise sans N-F&B lifestyle: {allowed2}")
    if "CONNECTED" not in allowed2:
        errors.append(f"CONNECTED manquant: {allowed2}")

    ibb = SimulationRequest.from_dict(
        {
            "identity": {"hotel_brand": "IBIS BUDGET"},
            "operating": {"nb_chambres": 150, "taux_occupation": 0.75, "guests_per_chambre": 1.7},
            "client_profile": {
                "client_needs": {
                    **{k: True for k in RULE3_FB_COEFFS},
                    **{k: True for k in RULE3_NFB_COEFFS},
                }
            },
        }
    )
    allowed3, _ = reco.allowed_concepts(ibb)
    for c in ("SIMPLY", "LIBERTY", "CONNECTED"):
        if c not in allowed3:
            errors.append(f"IBB 150 doit autoriser {c}: {allowed3}")

    # --- costs m_lin ---
    req_c = SimulationRequest.from_dict(
        {
            "identity": {"hotel_brand": "IBIS"},
            "operating": {"nb_chambres": 100, "taux_occupation": 0.7, "guests_per_chambre": 1.7},
        }
    )
    req_c.store = StoreConfig(concept="SIMPLY", m_lin=6, mix_fb=0.4, mix_nf=0.6)
    c6 = costs.compute(req_c, "SIMPLY")
    req_c.store = StoreConfig(concept="SIMPLY", m_lin=12, mix_fb=0.4, mix_nf=0.6)
    c12 = costs.compute(req_c, "SIMPLY")
    per_m = float(ref.get("concepts.SIMPLY.agencement_per_m") or 1000)
    if abs((c12.capex - c6.capex) - 6 * per_m) > 1.0:
        errors.append(
            f"capex agencement non lineaire: d={c12.capex - c6.capex} attendu {6 * per_m}"
        )

    # --- pilot MN / costs vs rod_reference (reference metier) ---
    all_true = {
        **{k: True for k in RULE3_FB_COEFFS},
        **{k: True for k in RULE3_NFB_COEFFS},
    }
    for concept in ("SIMPLY", "LIBERTY", "CONNECTED"):
        key = f"concepts.{concept}"
        pivot_n = float(ref.get(f"{key}.pivot_nb_chambres"))
        pivot_to = float(ref.get(f"{key}.pivot_to"))
        pivot_g = float(ref.get(f"{key}.pivot_guests_per_chambre"))
        pivot_m = float(ref.get(f"{key}.pivot_m_lin"))
        mix_fb = float(ref.get(f"{key}.mix_fb"))
        mix_nf = float(ref.get(f"{key}.mix_nf"))
        ref_cost = float(ref.get(f"{key}.monthly_cost_total") or 0)
        ref_mn = float(ref.get(f"{key}.marge_nette_mensuelle_pilote") or 0)
        req_p = SimulationRequest.from_dict(
            {
                "identity": {"hotel_brand": "IBIS"},
                "operating": {
                    "nb_chambres": pivot_n,
                    "taux_occupation": pivot_to,
                    "guests_per_chambre": pivot_g,
                },
                "client_profile": {"client_needs": all_true},
                "corner": {"m_lin": pivot_m, "mix_fb": mix_fb},
            }
        )
        req_p.store = StoreConfig(
            concept=concept, m_lin=pivot_m, mix_fb=mix_fb, mix_nf=mix_nf
        )
        rev_p = rev.compute(req_p, concept)
        cost_p = costs.compute(req_p, concept)
        mn = rev_p.marge_produit_mensuelle - cost_p.monthly_cost
        if abs(cost_p.monthly_cost - ref_cost) > 0.5:
            errors.append(
                f"{concept} pilot cost {cost_p.monthly_cost:.2f} != ref {ref_cost:.2f}"
            )
        if abs(mn - ref_mn) > 0.5:
            errors.append(
                f"{concept} pilot MN {mn:.2f} != ref {ref_mn:.2f}"
            )

    # --- reco: recommend never picks blocked concept ---
    orch_r = SimulationOrchestrator(auto_enrich=False)
    req_block = SimulationRequest.from_dict(
        {
            "identity": {"hotel_brand": "NOVOTEL"},
            "operating": {
                "nb_chambres": 40,
                "taux_occupation": 0.8,
                "guests_per_chambre": 1.8,
            },
            "client_profile": {"client_needs": all_true},
            "corner": {},
        }
    )
    sim_b = orch_r.simulate_all(req_block, enrich=False, hydrate_from_admin=False)
    if sim_b.recommended_concept != "SIMPLY":
        errors.append(
            f"n=40 reco doit etre SIMPLY, got {sim_b.recommended_concept}"
        )
    if sim_b.allowed_concepts != ["SIMPLY"]:
        errors.append(f"n=40 allowed={sim_b.allowed_concepts}")

    # --- orchestrator + flask ---
    orch = SimulationOrchestrator(auto_enrich=False)
    req_o = SimulationRequest.from_dict(
        {
            "identity": {"hotel_brand": "IBIS BUDGET"},
            "operating": {"nb_chambres": n, "taux_occupation": to, "guests_per_chambre": g},
            "client_profile": {"client_needs": dict(DEFAULT_CLIENT_NEEDS)},
            "corner": {},
        }
    )
    sim = orch.simulate_all(req_o, enrich=False, hydrate_from_admin=False)
    if sim.recommended_concept not in sim.allowed_concepts:
        errors.append("recommended_concept hors allowed_concepts")
    if not sim.by_concept.get("SIMPLY") or sim.by_concept["SIMPLY"].ca_mensuel <= 0:
        errors.append("SIMPLY CA doit etre > 0 sur scenario standard")

    from user.app import app

    client = app.test_client()
    resp = client.post(
        "/api/simulate?light=1",
        json={
            "identity": {"hotel_brand": "IBIS BUDGET"},
            "operating": {
                "nb_chambres": n,
                "taux_occupation": to,
                "guests_per_chambre": g,
            },
            "client_profile": {"client_needs": dict(DEFAULT_CLIENT_NEEDS)},
            "corner": {},
            "light_enrich": True,
        },
    )
    data = resp.get_json() or {}
    if resp.status_code != 200 or not data.get("ok"):
        errors.append(f"API simulate echec: {resp.status_code} {data}")
    else:
        api_simply = (data.get("by_concept") or {}).get("SIMPLY") or {}
        eng = sim.by_concept["SIMPLY"].ca_mensuel
        if abs(float(api_simply.get("ca_mensuel") or 0) - eng) > 0.5:
            errors.append(
                f"API CA SIMPLY {api_simply.get('ca_mensuel')} != engine {eng}"
            )

    if errors:
        print("ROD VALIDATION FAILED")
        for e in errors:
            print(" -", e)
        return 1

    print("ROD VALIDATION OK")
    print(
        f"  R1 SIMPLY={r1['by_concept']['SIMPLY']['ca_ht_mensuel']} "
        f"clients_mois={r1['clients_mois']}"
    )
    print(
        f"  sim reco={sim.recommended_concept} "
        f"SIMPLY CA={sim.by_concept['SIMPLY'].ca_mensuel:.1f} "
        f"allowed={sim.allowed_concepts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
