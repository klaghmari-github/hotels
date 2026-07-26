"""
Simulateur ROD côté admin — traçage détaillé sur hôtels pilotes (année incomplete).

Trois usages UI (sidebar admin → Simulateur ROD)
------------------------------------------------
1. Prédiction ventes : impact TO → R1 → R2 → R3 → R4 → marge produit
2. Marge : coûts techno / annexes / agencement par concept + marge nette
3. Évaluation : CA mensuel simulé vs CA réel (somme mois dispo / 12)

API : GET /api/rod/pilots , /api/rod/hotel/<code>/trace , /api/rod/eval
UI  : static/js/admin/rod-sim-panel.js
Doc : docs/ROD_ADMIN.md , docs/ROD_RULES.md

Réutilise les mêmes moteurs que le parcours user
(RevenueRules, CostRules, SimulationOrchestrator).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from accor.data_io import DATA_DIR, read_excel
from accor.user.models import (
    ClientProfile,
    HotelIdentity,
    HotelOperating,
    SimulationRequest,
    StoreConfig,
)
from accor.user.reference import RodReference
from accor.user.rules.coeffs import RULE3_BASELINE_FB, RULE3_BASELINE_NF
from accor.user.rules.costs import CostRules
from accor.user.rules.revenue import RevenueRules
from accor.user.services.hotel_context import HotelContextBuilder
from accor.user.services.orchestrator import SimulationOrchestrator

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")
DEFAULT_YEAR = 2026
DIVISOR_MONTHS = 12.0


def _round(x: Any, nd: int = 2) -> float | None:
    try:
        v = float(x)
        if v != v:  # NaN
            return None
        return round(v, nd)
    except (TypeError, ValueError):
        return None


def list_pilot_hotels(year: int = DEFAULT_YEAR) -> dict[str, Any]:
    """
    Hôtels présents dans hotel_sales_data pour ``year`` (pilotes avec vérité terrain).
    """
    path = DATA_DIR / "hotel_sales_data.xlsx"
    sales = read_excel(path, sheet="hotel_sales")
    if sales.empty:
        sales = read_excel(path, sheet=0)
    if sales.empty or "hotel_code" not in sales.columns:
        return {
            "ok": False,
            "error": "hotel_sales_data indisponible",
            "year": year,
            "hotels": [],
        }

    years = pd.to_numeric(sales.get("annee"), errors="coerce")
    sub = sales.loc[years == int(year)].copy()
    if sub.empty:
        return {
            "ok": True,
            "year": year,
            "hotels": [],
            "n": 0,
            "message": f"Aucune vente pour l'année {year}.",
        }

    sub["montant_ventes"] = pd.to_numeric(sub.get("montant_ventes"), errors="coerce")
    sub["mois"] = pd.to_numeric(sub.get("mois"), errors="coerce")

    hotels: list[dict[str, Any]] = []
    for code, g in sub.groupby(sub["hotel_code"].astype(str).str.strip()):
        months = sorted(
            int(m) for m in g["mois"].dropna().unique().tolist() if 1 <= int(m) <= 12
        )
        sum_true = float(g["montant_ventes"].fillna(0).sum())
        name = ""
        if "nom_hotel" in g.columns:
            name = str(g["nom_hotel"].iloc[0] or "")
        elif "hotel_name" in g.columns:
            name = str(g["hotel_name"].iloc[0] or "")
        hotels.append(
            {
                "hotel_code": str(code),
                "hotel_name": name,
                "n_months": len(months),
                "months": months,
                "sum_montant_ventes": _round(sum_true, 2),
                "avg_monthly_true": _round(sum_true / DIVISOR_MONTHS, 2),
            }
        )
    hotels.sort(key=lambda h: h["hotel_code"])

    # Enrichir nom/marque depuis hotel_data si dispo
    try:
        hd = read_excel(DATA_DIR / "hotel_data.xlsx", sheet=0)
        if not hd.empty and "hotel_code" in hd.columns:
            by_code = {
                str(r["hotel_code"]).strip(): r
                for _, r in hd.iterrows()
            }
            for h in hotels:
                row = by_code.get(h["hotel_code"])
                if row is None:
                    continue
                if not h["hotel_name"]:
                    h["hotel_name"] = str(row.get("hotel_name") or "")
                h["hotel_brand"] = str(row.get("hotel_brand") or "")
    except Exception:
        pass

    return {
        "ok": True,
        "year": int(year),
        "divisor_months": int(DIVISOR_MONTHS),
        "n": len(hotels),
        "hotels": hotels,
        "method": (
            f"Pilotes = hôtels avec ventes en {year}. "
            f"avg_monthly_true = somme(montant_ventes mois dispo) / {int(DIVISOR_MONTHS)}."
        ),
    }


def _request_from_context(code: str) -> tuple[SimulationRequest, dict[str, Any]]:
    builder = HotelContextBuilder()
    ctx = builder.build(code, fetch_if_missing=False)
    payload = ctx.to_simulation_payload()
    req = SimulationRequest.from_dict(payload)
    meta = {
        "identity": ctx.identity,
        "operating": ctx.operating,
        "corner": ctx.corner,
        "client_profile": ctx.client_profile,
        "indicators": ctx.indicators,
        "sources": ctx.sources,
        "warnings": list(ctx.warnings or []),
    }
    return req, meta


def _sales_steps(
    rev: RevenueRules,
    request: SimulationRequest,
    concept: str,
) -> dict[str, Any]:
    """
    Rejoue la chaîne revenus en enregistrant chaque étape (chiffres + formule).
    """
    concept = concept.upper()
    if request.store is None:
        raise ValueError("store requis")

    ref = rev._ref
    key = f"concepts.{concept}"
    pivot_nb = float(ref.get(f"{key}.pivot_nb_chambres", 129) or 129)
    pivot_guests = float(ref.get(f"{key}.pivot_guests_per_chambre", 1.7) or 1.7)
    pivot_m_lin = float(ref.get(f"{key}.pivot_m_lin", 6) or 6)
    pivot_to = float(ref.get(f"{key}.pivot_to", 0.75) or 0.75)
    ca_fb_ref = float(ref.get(f"{key}.base_monthly_ca_fb", 0) or 0)
    ca_nf_ref = float(ref.get(f"{key}.base_monthly_ca_nf", 0) or 0)
    ventes_ref = float(ref.get(f"{key}.base_monthly_sales", 0) or 0)
    margin_fb = float(ref.get(f"{key}.margin_fb_pct", 2.6) or 2.6)
    margin_nf = float(ref.get(f"{key}.margin_nf_pct", 1.45) or 1.45)
    ref_mix_fb = float(ref.get(f"{key}.mix_fb", 0.7) or 0.7)
    ref_mix_nf = float(ref.get(f"{key}.mix_nf", 0.3) or 0.3)
    impact_to = float(ref.get("impact_to.ht_per_0_01_to", 9.233974) or 9.233974)

    store = request.store
    user_mix_fb = float(store.mix_fb)
    user_mix_nf = float(store.mix_nf)
    total_mix = user_mix_fb + user_mix_nf
    if total_mix > 0:
        user_mix_fb /= total_mix
        user_mix_nf /= total_mix
    mix_customized = (
        abs(user_mix_fb - ref_mix_fb) > 0.02 or abs(user_mix_nf - ref_mix_nf) > 0.02
    )
    effective_fb = user_mix_fb if mix_customized else ref_mix_fb
    effective_nf = user_mix_nf if mix_customized else ref_mix_nf

    op = request.operating
    clients_pilote = pivot_nb * pivot_to * pivot_guests * op.JOURS_MOIS
    clients_hotel = op.clients_mois
    to_delta = op.taux_occupation - pivot_to

    steps: list[dict[str, Any]] = []

    steps.append(
        {
            "id": "inputs",
            "title": "Entrées hôtel",
            "rule": "Saisie / hotel_data + model_data",
            "formula": "clients_jour = n × TO × guests ; clients_mois = clients_jour × 30,5",
            "values": {
                "nb_chambres": op.nb_chambres,
                "taux_occupation": _round(op.taux_occupation, 4),
                "guests_per_chambre": _round(op.guests_per_chambre, 3),
                "clients_jour": _round(op.clients_jour, 2),
                "clients_mois": _round(clients_hotel, 2),
                "m_lin": _round(store.m_lin, 2),
                "mix_fb_user": _round(user_mix_fb, 4),
                "mix_nf_user": _round(user_mix_nf, 4),
            },
            "ca_fb": ca_fb_ref,
            "ca_nf": ca_nf_ref,
            "ca_ht": ca_fb_ref + ca_nf_ref,
        }
    )

    steps.append(
        {
            "id": "pilot",
            "title": f"Référence pilote {concept}",
            "rule": "rod_reference.json → concepts." + concept,
            "formula": "CA et pivots Excel du concept",
            "values": {
                "pivot_nb_chambres": pivot_nb,
                "pivot_to": pivot_to,
                "pivot_guests": pivot_guests,
                "pivot_m_lin": pivot_m_lin,
                "ca_fb_ref": _round(ca_fb_ref, 2),
                "ca_nf_ref": _round(ca_nf_ref, 2),
                "ca_ht_ref": _round(ca_fb_ref + ca_nf_ref, 2),
                "ventes_ref": _round(ventes_ref, 2),
                "mix_fb_ref": ref_mix_fb,
                "mix_nf_ref": ref_mix_nf,
                "clients_pilote": _round(clients_pilote, 2),
            },
            "ca_fb": ca_fb_ref,
            "ca_nf": ca_nf_ref,
            "ca_ht": ca_fb_ref + ca_nf_ref,
        }
    )

    ca_fb, ca_nf = RevenueRules.apply_to_impact(
        ca_fb_ref, ca_nf_ref, to_delta, impact_to
    )
    to_impact = (to_delta / 0.01) * impact_to
    steps.append(
        {
            "id": "impact_to",
            "title": "Impact taux d’occupation",
            "rule": "Écart TO × impact_to (~9,23 € HT par point de TO)",
            "formula": "ΔTO = TO_hôtel − TO_pilote ; impact = (ΔTO / 0,01) × 9,233974 € réparti F&B/N-F&B",
            "values": {
                "to_hotel": _round(op.taux_occupation, 4),
                "to_pilote": pivot_to,
                "to_delta": _round(to_delta, 4),
                "impact_ht": _round(to_impact, 2),
                "ca_fb_apres": _round(ca_fb, 2),
                "ca_nf_apres": _round(ca_nf, 2),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_fb, ca_nf, client_factor = RevenueRules.rule1_clients(
        ca_fb, ca_nf, clients_hotel, clients_pilote
    )
    steps.append(
        {
            "id": "r1_clients",
            "title": "Règle 1 — scaling clients",
            "rule": "CA × (clients_hôtel / clients_pilote)",
            "formula": "facteur = clients_mois_hôtel / clients_mois_pilote",
            "values": {
                "clients_hotel": _round(clients_hotel, 2),
                "clients_pilote": _round(clients_pilote, 2),
                "client_factor": _round(client_factor, 4),
                "ca_fb_apres": _round(ca_fb, 2),
                "ca_nf_apres": _round(ca_nf, 2),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_fb_r1, ca_nf_r1 = ca_fb, ca_nf
    ca_fb, ca_nf, steps_fb, steps_nf = RevenueRules.rule2_mix(
        ca_fb,
        ca_nf,
        user_mix_fb=effective_fb,
        user_mix_nf=effective_nf,
        ref_mix_fb=ref_mix_fb,
        ref_mix_nf=ref_mix_nf,
        ca_fb_ref=ca_fb_ref,
        ca_nf_ref=ca_nf_ref,
    )
    ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)
    steps.append(
        {
            "id": "r2_mix",
            "title": "Règle 2 — mix F&B / N-F&B",
            "rule": "Ajustement par pas de 10 % de mix vs pilote",
            "formula": "steps = (mix_user − mix_ref) × 10 ; CA += unit × steps",
            "values": {
                "mix_fb_effectif": _round(effective_fb, 4),
                "mix_nf_effectif": _round(effective_nf, 4),
                "mix_fb_ref": ref_mix_fb,
                "mix_nf_ref": ref_mix_nf,
                "mix_customized": mix_customized,
                "steps_fb": _round(steps_fb, 3),
                "steps_nf": _round(steps_nf, 3),
                "ca_avant_ht": _round(ca_fb_r1 + ca_nf_r1, 2),
                "ca_fb_apres": _round(ca_fb, 2),
                "ca_nf_apres": _round(ca_nf, 2),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_fb_r2, ca_nf_r2 = ca_fb, ca_nf
    cumul_fb, cumul_nf = RevenueRules.cumul_rule3(request.client_profile.client_needs)
    ca_fb, ca_nf, delta_fb, delta_nf = RevenueRules.rule3_categories(
        ca_fb, ca_nf, cumul_fb, cumul_nf
    )
    ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)
    steps.append(
        {
            "id": "r3_categories",
            "title": "Règle 3 — catégories besoins clients",
            "rule": "Δ cumul coefs besoins vs baseline Excel",
            "formula": "CA_canal × (1 + (cumul_besoins − baseline))",
            "values": {
                "cumul_fb": _round(cumul_fb, 4),
                "cumul_nf": _round(cumul_nf, 4),
                "baseline_fb": RULE3_BASELINE_FB,
                "baseline_nf": RULE3_BASELINE_NF,
                "delta_fb": _round(delta_fb, 4),
                "delta_nf": _round(delta_nf, 4),
                "ca_avant_ht": _round(ca_fb_r2 + ca_nf_r2, 2),
                "ca_fb_apres": _round(ca_fb, 2),
                "ca_nf_apres": _round(ca_nf, 2),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_fb_r3, ca_nf_r3 = ca_fb, ca_nf
    ca_fb, ca_nf, m_lin_diff = RevenueRules.rule4_m_lin(
        ca_fb,
        ca_nf,
        m_lin=store.m_lin,
        pivot_m_lin=pivot_m_lin,
        ca_fb_ref=ca_fb_ref,
        ca_nf_ref=ca_nf_ref,
    )
    ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)
    steps.append(
        {
            "id": "r4_mlin",
            "title": "Règle 4 — mètres linéaires",
            "rule": "Écart m_lin vs pivot concept",
            "formula": "Δm = m_lin − pivot_m_lin ; CA ± (CA_ref / pivot_m) × |Δm|",
            "values": {
                "m_lin": _round(store.m_lin, 2),
                "pivot_m_lin": pivot_m_lin,
                "m_lin_diff": _round(m_lin_diff, 2),
                "ca_avant_ht": _round(ca_fb_r3 + ca_nf_r3, 2),
                "ca_fb_apres": _round(ca_fb, 2),
                "ca_nf_apres": _round(ca_nf, 2),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_ht = ca_fb + ca_nf
    taux_acheteur = ventes_ref / clients_pilote if clients_pilote else 0.0
    nbr_ventes = taux_acheteur * clients_hotel
    marge = RevenueRules.marge_produit(ca_fb, ca_nf, margin_fb, margin_nf)
    steps.append(
        {
            "id": "marge_produit",
            "title": "Marge produit",
            "rule": "Excel : marge = CA − CA/coef (F&B et N-F&B)",
            "formula": f"marge_fb = CA_fb − CA_fb/{margin_fb} ; idem N-F&B coef {margin_nf}",
            "values": {
                "ca_ht_mensuel": _round(ca_ht, 2),
                "ca_fb": _round(ca_fb, 2),
                "ca_nf": _round(ca_nf, 2),
                "nbr_ventes_mensuel": _round(nbr_ventes, 2),
                "taux_acheteur": _round(taux_acheteur, 4),
                "marge_produit_mensuelle": _round(marge, 2),
                "coef_fb": margin_fb,
                "coef_nf": margin_nf,
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_ht,
        }
    )

    # arrondir ca des steps pour l'UI
    for s in steps:
        s["ca_fb"] = _round(s.get("ca_fb"), 2)
        s["ca_nf"] = _round(s.get("ca_nf"), 2)
        s["ca_ht"] = _round(s.get("ca_ht"), 2)

    return {
        "concept": concept,
        "ca_ht_mensuel": _round(ca_ht, 2),
        "ca_fb_mensuel": _round(ca_fb, 2),
        "ca_nf_mensuel": _round(ca_nf, 2),
        "nbr_ventes_mensuel": _round(nbr_ventes, 2),
        "marge_produit_mensuelle": _round(marge, 2),
        "steps": steps,
    }


def simulate_hotel_trace(
    hotel_code: str,
    *,
    year: int = DEFAULT_YEAR,
    concept: str | None = None,
) -> dict[str, Any]:
    """
    Trace complète ventes + coûts + marge pour un hôtel pilote.

    Si ``concept`` est None : les 3 concepts.
    """
    code = str(hotel_code or "").strip()
    if not code:
        return {"ok": False, "error": "hotel_code requis"}

    try:
        req, ctx_meta = _request_from_context(code)
    except Exception as exc:
        return {"ok": False, "error": f"Contexte hôtel : {exc}", "hotel_code": code}

    orch = SimulationOrchestrator(auto_enrich=False)
    req, prep = orch.prepare_request(req, hydrate_from_admin=True)

    rev = RevenueRules(orch.reference)
    costs = CostRules(orch.reference)

    concepts = (concept.upper(),) if concept else CONCEPTS
    by_concept: dict[str, Any] = {}

    for c in concepts:
        req_c = orch.request_for_concept(req, c)
        try:
            sales = _sales_steps(rev, req_c, c)
            cost = costs.compute(req_c, c)
            marge_prod = float(sales["marge_produit_mensuelle"] or 0)
            cout_m = float(cost.monthly_cost or 0)
            marge_nette = marge_prod - cout_m
            by_concept[c] = {
                "sales": sales,
                "costs": {
                    "monthly_cost": _round(cout_m, 2),
                    "annual_cost": _round(cost.annual_cost, 2),
                    "capex": _round(cost.capex, 2),
                    "techno_monthly": _round(cost.techno_monthly, 2),
                    "annexes_monthly": _round(cost.annexes_monthly, 2),
                    "agencement_monthly": _round(cost.agencement_monthly, 2),
                    "cost_lines": cost.cost_lines,
                    "warnings": cost.warnings,
                },
                "margin": {
                    "marge_produit_mensuelle": _round(marge_prod, 2),
                    "marge_produit_annuelle": _round(marge_prod * 12, 2),
                    "cout_mensuel": _round(cout_m, 2),
                    "cout_annuel": _round(cout_m * 12, 2),
                    "marge_nette_mensuelle": _round(marge_nette, 2),
                    "marge_nette_annuelle": _round(marge_nette * 12, 2),
                    "formula": "marge_nette = marge_produit − coûts_mensuels",
                },
                "store": req_c.store.to_dict() if req_c.store else {},
            }
        except Exception as exc:
            by_concept[c] = {"ok": False, "error": str(exc)}

    # Vérité terrain année
    pilots = list_pilot_hotels(year)
    real = next(
        (h for h in pilots.get("hotels") or [] if h["hotel_code"] == code),
        None,
    )

    return {
        "ok": True,
        "hotel_code": code,
        "year": int(year),
        "divisor_months": int(DIVISOR_MONTHS),
        "context": ctx_meta,
        "prep_warnings": prep.get("warnings") or [],
        "operating": req.operating.to_dict(),
        "identity": req.identity.to_dict(),
        "client_needs": dict(req.client_profile.client_needs or {}),
        "by_concept": by_concept,
        "real_sales": real,
        "concepts": list(concepts),
    }


def evaluate_pilots_year(year: int = DEFAULT_YEAR) -> dict[str, Any]:
    """
    Pour chaque pilote de ``year`` : CA simulé (3 concepts) vs réel Σ/12.
    """
    pilots = list_pilot_hotels(year)
    if not pilots.get("ok"):
        return pilots

    rows: list[dict[str, Any]] = []
    orch = SimulationOrchestrator(auto_enrich=False)

    for h in pilots.get("hotels") or []:
        code = h["hotel_code"]
        avg_true = float(h.get("avg_monthly_true") or 0)
        try:
            req, _ = _request_from_context(code)
            req, _ = orch.prepare_request(req, hydrate_from_admin=True)
            full = orch.simulate_all(req, light_enrich=True, hydrate_from_admin=False)
            by_c: dict[str, Any] = {}
            for c, sim in full.by_concept.items():
                ca = float(sim.ca_mensuel or 0)
                gap = ca - avg_true
                pct = (100.0 * gap / avg_true) if abs(avg_true) > 1e-9 else None
                by_c[c] = {
                    "ca_sim_mensuel": _round(ca, 2),
                    "avg_monthly_true": _round(avg_true, 2),
                    "gap": _round(gap, 2),
                    "gap_pct": _round(pct, 1) if pct is not None else None,
                    "marge_nette_mensuelle": _round(sim.marge_nette_mensuelle, 2),
                }
            # écart sur concept recommandé
            reco = full.recommended_concept or "SIMPLY"
            rows.append(
                {
                    "hotel_code": code,
                    "hotel_name": h.get("hotel_name") or "",
                    "hotel_brand": h.get("hotel_brand") or "",
                    "n_months": h.get("n_months"),
                    "months": h.get("months"),
                    "sum_true": h.get("sum_montant_ventes"),
                    "avg_monthly_true": _round(avg_true, 2),
                    "recommended_concept": reco,
                    "by_concept": by_c,
                    "gap_reco": (by_c.get(reco) or {}).get("gap"),
                    "gap_pct_reco": (by_c.get(reco) or {}).get("gap_pct"),
                    "ca_sim_reco": (by_c.get(reco) or {}).get("ca_sim_mensuel"),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "hotel_code": code,
                    "hotel_name": h.get("hotel_name") or "",
                    "error": str(exc),
                    "avg_monthly_true": _round(avg_true, 2),
                }
            )

    # métriques globales sur reco
    gaps = [r["gap_reco"] for r in rows if r.get("gap_reco") is not None]
    import numpy as np

    metrics: dict[str, Any] = {"n": len(gaps)}
    if gaps:
        g = np.array(gaps, dtype=float)
        yt = np.array(
            [float(r["avg_monthly_true"] or 0) for r in rows if r.get("gap_reco") is not None],
            dtype=float,
        )
        yp = yt + g
        metrics["mae"] = _round(float(np.mean(np.abs(g))), 2)
        metrics["bias"] = _round(float(np.mean(g)), 2)
        metrics["rmse"] = _round(float(np.sqrt(np.mean(g ** 2))), 2)
        nz = np.abs(yt) > 1e-9
        if nz.any():
            metrics["mape"] = _round(
                float(np.mean(np.abs(g[nz] / yt[nz])) * 100.0), 1
            )
        metrics["mean_true"] = _round(float(np.mean(yt)), 2)
        metrics["mean_sim"] = _round(float(np.mean(yp)), 2)

    return {
        "ok": True,
        "year": int(year),
        "divisor_months": int(DIVISOR_MONTHS),
        "n_hotels": len(rows),
        "method": (
            f"CA simulé mensuel (règles ROD) vs avg_monthly_true = "
            f"somme(montant_ventes {year}) / {int(DIVISOR_MONTHS)}. "
            "Écart = simulé − réel (sur concept recommandé)."
        ),
        "metrics": metrics,
        "hotels": rows,
    }
