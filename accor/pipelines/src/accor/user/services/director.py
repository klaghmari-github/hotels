"""
Simulation « directeur » — résultats pour l'interface user.

Fidèle à ``simulateur_rules.html`` :
  arbre reco → 3× (R1→R2→R3→R4 → marge produits → coûts → marge nette / amort)

Deux vues (même saisie) :

* **simulateur** — CA règles métier + coûts + marge nette
* **ia** — prédiction modèle sur **montant_ventes** (CA) ; la marge produit
  suit la règle fixe ``ventes = 2,5 × achats`` (pas de modèle de marge)

Les réglages restent en session côté navigateur (pas d'écriture base).
"""

from __future__ import annotations

from typing import Any

from accor.model_data import (
    MAIN_TARGET,
    VENTES_SUR_ACHATS,
    marge_from_ventes,
    ventes_from_marge,
)
from accor.user.models import (
    ClientProfile,
    HotelIdentity,
    HotelOperating,
    HotelServices,
    SimulationRequest,
    StoreConfig,
)
from accor.user.reference import RodReference
from accor.user.rules.coeffs import CLIENT_NEED_LABELS, LIBERTY_NFB_NEEDS
from accor.user.rules.costs import CostRules
from accor.user.rules.pilot_table import get_pilot
from accor.user.rules.recommendation import RecommendationRules
from accor.user.rules.revenue import RevenueRules
from accor.user.services.simulator import RodSimulator

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")

# Minimum métier (spec §13)
MIN_M_LIN = 2.0


def _f(v: Any, default: float | None = None) -> float | None:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int | None = None) -> int | None:
    f = _f(v, None)
    if f is None:
        return default
    return int(round(f))


def _bool(v: Any, default: bool = False) -> bool:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "oui", "on"):
        return True
    if s in ("0", "false", "no", "non", "off"):
        return False
    return default


def _pnl_block(
    sim_result: Any,
    *,
    ca_override: float | None = None,
    marge_produit_override: float | None = None,
) -> dict[str, Any]:
    """
    Bloc P&L complet pour une solution (sim ou IA).

    Spec §11 :
      Marge_nette = Marge_produits − Coûts
      SI < 0 ou CA < 0 → status not_profitable
      SINON amort = cost_60 / marge_nette
    """
    cout = float(getattr(sim_result, "cout_mensuel", 0) or 0)
    capex = float(getattr(sim_result, "capex", 0) or 0)
    techno = float(getattr(sim_result, "techno_monthly", 0) or 0)
    annexes = float(getattr(sim_result, "annexes_monthly", 0) or 0)
    agencement = float(getattr(sim_result, "agencement_monthly", 0) or 0)
    cost_60 = float(getattr(sim_result, "cost_over_60m", 0) or 0)
    cost_lines = list(
        (getattr(sim_result, "costs", None) or {}).get("cost_lines")
        or getattr(sim_result, "cost_lines", None)
        or []
    )

    ca_fb = float(getattr(sim_result, "ca_fb_mensuel", 0) or 0)
    ca_nfb = float(getattr(sim_result, "ca_nfb_mensuel", 0) or 0)
    ca = float(getattr(sim_result, "ca_mensuel", 0) or 0)
    mp = float(getattr(sim_result, "marge_produit_mensuelle", 0) or 0)

    # Override IA : redimensionne CA F&B/NFB proportionnellement
    if ca_override is not None:
        if ca > 0 and ca_override is not None:
            ratio = float(ca_override) / ca if ca else 1.0
            ca_fb = ca_fb * ratio
            ca_nfb = ca_nfb * ratio
            ca = float(ca_override)
        else:
            ca = float(ca_override)
            ca_fb = ca * 0.7
            ca_nfb = ca * 0.3
        if marge_produit_override is not None:
            mp = float(marge_produit_override)
        elif ca > 0 and float(getattr(sim_result, "ca_mensuel", 0) or 0) > 0:
            mp = float(getattr(sim_result, "marge_produit_mensuelle", 0) or 0) * (
                ca / float(sim_result.ca_mensuel)
            )
        else:
            mp = ca * 0.35

    marge_nette = mp - cout
    not_profitable = marge_nette < 0 or ca < 0 or ca_fb < 0 or ca_nfb < 0
    status = "not_profitable" if not_profitable else "ok"

    amort_months: float | None = None
    amort_years: float | None = None
    taux_marge: float | None = None
    if not not_profitable and marge_nette > 0:
        amort_months = round(cost_60 / marge_nette, 2) if cost_60 > 0 else None
        amort_years = round(amort_months / 12.0, 2) if amort_months is not None else None
        taux_marge = round(marge_nette / ca, 4) if ca > 0 else None

    rev = getattr(sim_result, "revenue", None) or {}
    breakdown = rev.get("breakdown") if isinstance(rev, dict) else {}

    return {
        "ca_mensuel": round(ca, 2),
        "ca_fb_mensuel": round(ca_fb, 2),
        "ca_nfb_mensuel": round(ca_nfb, 2),
        "marge_produit_mensuelle": round(mp, 2),
        "cout_mensuel": round(cout, 2),
        "techno_monthly": round(techno, 2),
        "annexes_monthly": round(annexes, 2),
        "agencement_monthly": round(agencement, 2),
        "capex": round(capex, 2),
        "cost_over_60m": round(cost_60, 2),
        "cost_lines": cost_lines,
        "marge_nette_mensuelle": round(marge_nette, 2),
        "marge_nette_annuelle": round(marge_nette * 12.0, 2),
        "status": status,
        "not_profitable": not_profitable,
        "amort_months": amort_months,
        "amort_years": amort_years,
        "taux_marge": taux_marge,
        "ventes_mensuel": round(
            float(getattr(sim_result, "ventes_mensuel", 0) or 0), 2
        ),
        "breakdown": breakdown if isinstance(breakdown, dict) else {},
        "warnings": list(getattr(sim_result, "warnings", None) or []),
    }


def _empty_pnl(*, cout: float = 0, capex: float = 0) -> dict[str, Any]:
    return {
        "ca_mensuel": None,
        "ca_fb_mensuel": None,
        "ca_nfb_mensuel": None,
        "marge_produit_mensuelle": None,
        "cout_mensuel": round(cout, 2),
        "techno_monthly": None,
        "annexes_monthly": None,
        "agencement_monthly": None,
        "capex": round(capex, 2),
        "cost_over_60m": None,
        "cost_lines": [],
        "marge_nette_mensuelle": None,
        "marge_nette_annuelle": None,
        "status": "unavailable",
        "not_profitable": None,
        "amort_months": None,
        "amort_years": None,
        "taux_marge": None,
        "ventes_mensuel": None,
        "breakdown": {},
        "warnings": [],
    }


def director_simulate(body: dict[str, Any]) -> dict[str, Any]:
    """
    Calcule les 3 solutions pour un hôtel (iso simulateur_rules).

    Body :
      hotel_code, hotel_name, hotel_brand,
      hotel_params, m_lin, mix_fb, client_needs,
      contract (BUY|LEASE), agencement (CLASSIC|PREMIUM|BESPOKE),
      nb_frigos_froid, nb_frigos_ambiant, nb_scanners, nb_caisses, nb_vitrines
    """
    from accor.user.hotel_form import (
        params_to_feature_overrides,
        params_to_services,
        resolve_params,
    )
    from accor.user.models import DEFAULT_CLIENT_NEEDS
    from accor.user.rules.assortment import (
        FB_KEYS,
        NFB_KEYS,
        needs_from_shares,
        optimize_repartition,
        parse_shares_payload,
        shares_for_api,
    )
    from accor.user.rules.coeffs import RULE3_FB_COEFFS, RULE3_NFB_COEFFS

    code = str(body.get("hotel_code") or "").strip()
    if not code:
        return {"ok": False, "error": "Indiquez un code hôtel."}

    identity_name = str(body.get("hotel_name") or "").strip()
    identity_brand = str(body.get("hotel_brand") or "").strip()
    hotel_values: dict[str, Any] = {}
    def_m_lin = 6.0
    def_mix = 0.70
    def_g = 1.7
    try:
        from accor.user.services.hotel_context import HotelContextBuilder

        ctx = HotelContextBuilder().build(code, fetch_if_missing=True)
        ident = ctx.identity or {}
        ind0 = ctx.indicators if isinstance(ctx.indicators, dict) else {}
        if not identity_name:
            identity_name = str(ident.get("hotel_name") or "")
        if not identity_brand:
            identity_brand = str(ident.get("hotel_brand") or "")
        hotel_values = dict(ctx.hotel_params or {})
        op0 = ctx.operating if isinstance(ctx.operating, dict) else {}
        def_g = float(op0.get("guests_per_chambre") or def_g) or def_g
        if ind0.get("m_lin") is not None:
            def_m_lin = float(ind0["m_lin"]) or 6.0
        elif (ctx.corner or {}).get("m_lin") is not None:
            def_m_lin = float(ctx.corner["m_lin"]) or 6.0
        if ind0.get("mix_fb") is not None:
            def_mix = float(ind0["mix_fb"])
    except Exception:
        pass

    user_params: dict[str, Any] = {}
    if isinstance(body.get("hotel_params"), dict):
        user_params.update(body["hotel_params"])
    alias = {
        "hotel_nb_chambres": body.get("nb_chambres"),
        "hotel_to_annuel": body.get("taux_occupation"),
        "guests_per_chambre": body.get("guests_per_chambre"),
        "hotel_derniere_reno": body.get("derniere_reno"),
        "hotel_f_b_restaurant": body.get("nb_restaurants"),
        "hotel_f_b_bar": body.get("nb_bars")
        if body.get("nb_bars") is not None
        else body.get("has_bar"),
        "hotel_non_f_b_piscine": body.get("has_pool"),
        "hotel_dispo_dans_lobby_vitrine_refrigerree": body.get("has_vitrine"),
        "hotel_dispo_dans_lobby_vitrine_refrigeree": body.get("has_vitrine"),
    }
    for k, v in alias.items():
        if v is not None and v != "" and k not in user_params:
            user_params[k] = v

    params = resolve_params(hotel_values, user_params, guests_fallback=def_g)
    n = float(params.get("hotel_nb_chambres") or 100) or 100.0
    to = float(params.get("hotel_to_annuel") or 0.7) or 0.7
    if to > 1.0:
        to /= 100.0
    g = float(params.get("guests_per_chambre") or def_g) or def_g

    # --- ML min 2 (spec §13) ---
    m_lin_raw = _f(body.get("m_lin"), def_m_lin)
    if m_lin_raw is None:
        m_lin_raw = def_m_lin
    if body.get("m_lin") in (None, "") and params.get(
        "hotel_metres_lineaires_dedies_corner"
    ):
        m_lin_raw = (
            float(params["hotel_metres_lineaires_dedies_corner"]) or m_lin_raw
        )
    m_lin = float(max(MIN_M_LIN, int(round(float(m_lin_raw)))))
    m_lin_forced = float(m_lin_raw) < MIN_M_LIN

    mix_fb = _f(body.get("mix_fb"), def_mix) or def_mix
    if mix_fb > 1.0:
        mix_fb /= 100.0
    mix_fb = min(max(mix_fb, 0.0), 1.0)

    # Équipements / contrat (spec §2)
    contract = str(body.get("contract") or "BUY").upper().strip()
    if contract not in ("BUY", "LEASE"):
        contract = "BUY"
    agencement = str(body.get("agencement") or "CLASSIC").upper().strip()
    if agencement not in ("CLASSIC", "PREMIUM", "BESPOKE"):
        agencement = "CLASSIC"
    nb_scanners = max(_i(body.get("nb_scanners"), 1) or 1, 0)
    nb_caisses = max(_i(body.get("nb_caisses"), 1) or 1, 0)
    nb_vitrines = max(_i(body.get("nb_vitrines"), 1) or 1, 0)
    nb_frigos_froid = max(_i(body.get("nb_frigos_froid"), 3) or 0, 0)
    nb_frigos_ambiant = max(_i(body.get("nb_frigos_ambiant"), 0) or 0, 0)

    services_map = params_to_services(params)
    has_vitrine = bool(
        services_map.get("lobby_fridge")
        or services_map.get("has_vitrine")
        or body.get("has_vitrine")
    )
    has_pool = bool(services_map.get("pool") or services_map.get("has_pool"))
    nb_restaurants = int(services_map.get("nb_restaurants") or 0)
    nb_bars = int(services_map.get("nb_bars") or 0)
    derniere_reno = _i(params.get("hotel_derniere_reno"), None)

    shares_fb, shares_nfb, needs, _ = parse_shares_payload(
        body, default_needs=dict(DEFAULT_CLIENT_NEEDS)
    )
    for k in list(RULE3_FB_COEFFS) + list(RULE3_NFB_COEFFS):
        needs.setdefault(k, False)

    # Garde-fou : toutes catégories OFF
    any_cat = any(bool(v) for v in needs.values())
    if not any_cat:
        return {
            "ok": False,
            "error": "Activez au moins une catégorie produit (F&B ou Non F&B).",
        }

    # mode: "simulate" = choix user (+ suggestion) ; "optimize" = applique le meilleur
    mode = str(body.get("mode") or "").strip().lower()
    optimize = bool(
        body.get("optimize_repartition")
        or body.get("optimize")
        or body.get("optimize_shares")
        or mode in ("optimize", "optimise", "opt")
    )
    # Toujours chercher une meilleure répartition pour signaler « optimisation possible »
    suggest_opt = bool(body.get("suggest_optimization", True))

    profile_base: dict[str, Any] = {}
    if params.get("hotel_loisirs_pct") is not None:
        profile_base["loisirs_pct"] = float(params["hotel_loisirs_pct"])
    if params.get("hotel_affaires_pct") is not None:
        profile_base["affaires_pct"] = float(params["hotel_affaires_pct"])
    if params.get("hotel_national_pct") is not None:
        profile_base["national_pct"] = float(params["hotel_national_pct"])
    if params.get("hotel_international_pct") is not None:
        profile_base["international_pct"] = float(params["hotel_international_pct"])

    ref = RodReference()
    rev = RevenueRules(ref)
    cost_rules = CostRules(ref)
    sim_engine = RodSimulator(rev, cost_rules)
    reco_engine = RecommendationRules()

    services_obj = HotelServices(
        bar=bool(services_map.get("bar")),
        restaurant=bool(services_map.get("restaurant")),
        room_service=bool(services_map.get("room_service")),
        minibar=bool(services_map.get("minibar")),
        meeting_rooms=bool(services_map.get("meeting_rooms")),
        gym=bool(services_map.get("gym")),
        spa=bool(services_map.get("spa")),
        pool=bool(has_pool),
        parking=bool(services_map.get("parking")),
        wifi=bool(services_map.get("wifi")),
        clim=bool(services_map.get("clim")),
        breakfast=bool(services_map.get("breakfast")),
        accessible=bool(services_map.get("accessible")),
        pets=bool(services_map.get("pets")),
        non_smoking=bool(services_map.get("non_smoking")),
        shuttle=bool(services_map.get("shuttle")),
        lobby_fridge=bool(has_vitrine),
        lobby_microwave=bool(services_map.get("lobby_microwave")),
        lobby_water=bool(services_map.get("lobby_water")),
        lobby_coffee=bool(services_map.get("lobby_coffee")),
        lobby_kettle=bool(services_map.get("lobby_kettle")),
        lobby_seating=bool(services_map.get("lobby_seating")),
        corner_fb_caisse=bool(services_map.get("corner_fb_caisse")),
        corner_fb_distributeur=bool(services_map.get("corner_fb_distributeur")),
        corner_fb_frigo=bool(services_map.get("corner_fb_frigo")),
        corner_fb_reception=bool(services_map.get("corner_fb_reception")),
        corner_fb_snacking=bool(services_map.get("corner_fb_snacking")),
        corner_nfb_armoire=bool(services_map.get("corner_nfb_armoire")),
        corner_nfb_caisse=bool(services_map.get("corner_nfb_caisse")),
        corner_nfb_distributeur=bool(services_map.get("corner_nfb_distributeur")),
        corner_nfb_reception=bool(services_map.get("corner_nfb_reception")),
    )

    identity = HotelIdentity(
        hotel_code=code,
        hotel_name=identity_name,
        hotel_brand=identity_brand,
    )
    operating = HotelOperating(
        nb_chambres=int(round(n)),
        taux_occupation=to,
        guests_per_chambre=g,
    )

    def _store_for(concept: str, mix: float) -> StoreConfig:
        return StoreConfig(
            concept=concept,
            m_lin=m_lin,
            mix_fb=mix,
            mix_nf=1.0 - mix,
            nb_frigos_froid=nb_frigos_froid,
            nb_frigos_ambiant=nb_frigos_ambiant,
            nb_scanners=nb_scanners,
            nb_caisses=nb_caisses,
            nb_vitrines=nb_vitrines,
            contract=contract,
            agencement=agencement,
        )

    def _needs_from(sh_fb: dict, sh_nfb: dict) -> dict[str, bool]:
        nd = needs_from_shares(sh_fb or {}, sh_nfb or {})
        for k in list(RULE3_FB_COEFFS) + list(RULE3_NFB_COEFFS):
            if k in needs and k not in (sh_fb or {}) and k not in (sh_nfb or {}):
                nd[k] = bool(needs[k])
            nd.setdefault(k, False)
        return nd

    def _run_concepts(
        mix: float,
        sh_fb: dict[str, float],
        sh_nfb: dict[str, float],
        *,
        concepts: tuple[str, ...] | None = None,
        fixed_rec: str | None = None,
    ) -> tuple[dict[str, Any], SimulationRequest | None, dict[str, Any], dict[str, Any]]:
        """P&L pour un ou plusieurs concepts (iso rules)."""
        nd = _needs_from(sh_fb, sh_nfb)
        profile = ClientProfile(
            client_needs=nd,
            shares_fb=dict(sh_fb),
            shares_nfb=dict(sh_nfb),
            **profile_base,
        )
        target = concepts or CONCEPTS
        by: dict[str, Any] = {}
        raw: dict[str, Any] = {}
        req0: SimulationRequest | None = None
        ca_by: dict[str, float] = {}
        for concept in target:
            req = SimulationRequest(
                identity=identity,
                operating=operating,
                services=services_obj,
                client_profile=profile,
                store=_store_for(concept, mix),
            )
            if req0 is None:
                req0 = req
            cs = sim_engine.simulate(req, concept)
            raw[concept] = cs
            ca_by[concept] = float(cs.ca_mensuel or 0)
            by[concept] = _pnl_block(cs)
        if fixed_rec and fixed_rec in by:
            rec = fixed_rec
        else:
            rec, _, _ = reco_engine.recommend_tree(
                req0 or SimulationRequest(store=_store_for("SIMPLY", mix)),
                m_lin=m_lin,
                to=to,
            )
        ca_ht = ca_by.get(rec) if rec in ca_by else max(ca_by.values(), default=0.0)
        marge_n = 0.0
        if rec in by:
            marge_n = float(by[rec].get("marge_nette_mensuelle") or 0)
        elif by:
            marge_n = max(
                float(v.get("marge_nette_mensuelle") or 0) for v in by.values()
            )
        return (
            by,
            req0,
            {
                "ca_ht": float(ca_ht or 0),
                "marge_nette": float(marge_n),
                "ca_by": ca_by,
                "recommended": rec,
            },
            raw,
        )

    def _run_three(
        mix: float, sh_fb: dict[str, float], sh_nfb: dict[str, float]
    ) -> tuple[dict[str, Any], SimulationRequest | None, dict[str, Any], dict[str, Any]]:
        return _run_concepts(mix, sh_fb, sh_nfb, concepts=CONCEPTS)

    # --- Baseline user (parts normalisées à 100 %) ---
    user_mix = float(mix_fb)
    user_shares_fb = dict(shares_fb)
    user_shares_nfb = dict(shares_nfb)
    # Parts déjà normalisées côté parse_shares_payload (somme forcée à 1)
    sum_fb = sum(float(v or 0) for v in user_shares_fb.values())
    sum_nfb = sum(float(v or 0) for v in user_shares_nfb.values())
    shares_ok = abs(sum_fb - 1.0) < 0.02 and abs(sum_nfb - 1.0) < 0.02

    sim_user, req_user, meta_user, raw_user = _run_three(
        user_mix, user_shares_fb, user_shares_nfb
    )
    user_ca = float(meta_user.get("ca_ht") or 0)
    user_marge = float(meta_user.get("marge_nette") or 0)
    # Reco stable pour la grille d'opti (dépend des toggles lifestyle / ML / TO, pas du mix)
    fixed_rec = str(meta_user.get("recommended") or "LIBERTY")

    # --- Optimisation mix F&B × sous-catégories (toujours évaluée) ---
    en_fb = {k: bool(needs.get(k, False)) for k in FB_KEYS}
    en_nfb = {k: bool(needs.get(k, False)) for k in NFB_KEYS}
    # Respect des toggles user ; si un canal vide, tout activer pour ce canal
    if not any(en_fb.values()):
        en_fb = {k: True for k in FB_KEYS}
    if not any(en_nfb.values()):
        en_nfb = {k: True for k in NFB_KEYS}

    def _sim_opt(mix: float, sh_fb: dict, sh_nfb: dict) -> dict:
        # Pendant la recherche : 1 concept (reco) seulement → ~3× plus rapide
        _, _, meta, _ = _run_concepts(
            mix, sh_fb, sh_nfb, concepts=(fixed_rec,), fixed_rec=fixed_rec
        )
        return meta

    opt: dict[str, Any] = {"ok": False}
    if optimize or suggest_opt:
        opt = optimize_repartition(
            simulate_fn=_sim_opt,
            enabled_fb=en_fb,
            enabled_nfb=en_nfb,
            m_lin=m_lin,
            user_mix_fb=user_mix,
        )

    opt_ca = float(opt.get("ca_ht") or 0) if opt.get("ok") else user_ca
    opt_marge = (
        float(opt.get("marge_nette") or opt_ca) if opt.get("ok") else user_marge
    )
    # Amélioration significative (marge puis CA)
    eps_m, eps_ca = 0.5, 1.0  # € / mois
    improvement = bool(opt.get("ok")) and (
        opt_marge > user_marge + eps_m
        or (abs(opt_marge - user_marge) <= eps_m and opt_ca > user_ca + eps_ca)
    )

    applied = False
    if optimize and opt.get("ok"):
        mix_fb = float(opt["mix_fb"])
        shares_fb = dict(opt["shares_fb"])
        shares_nfb = dict(opt["shares_nfb"])
        needs = needs_from_shares(shares_fb, shares_nfb)
        sim_by, req_for_reco, _meta_run, raw_by = _run_three(
            mix_fb, shares_fb, shares_nfb
        )
        applied = True
    else:
        mix_fb = user_mix
        shares_fb = user_shares_fb
        shares_nfb = user_shares_nfb
        sim_by, req_for_reco, _meta_run, raw_by = (
            sim_user,
            req_user,
            meta_user,
            raw_user,
        )

    category_shares_out = shares_for_api(shares_fb, shares_nfb)

    suggestion: dict[str, Any] | None = None
    if opt.get("ok") and not applied:
        suggestion = {
            "available": improvement,
            "mix_fb": opt.get("mix_fb"),
            "mix_nf": opt.get("mix_nf"),
            "shares_fb": opt.get("shares_fb"),
            "shares_nfb": opt.get("shares_nfb"),
            "category_shares": opt.get("category_shares"),
            "strategy": opt.get("strategy"),
            "trials": opt.get("trials"),
            "ca_ht": opt_ca,
            "marge_nette": opt_marge,
            "user_ca_ht": user_ca,
            "user_marge_nette": user_marge,
            "delta_ca": round(opt_ca - user_ca, 2),
            "delta_marge": round(opt_marge - user_marge, 2),
            "recommended": opt.get("recommended"),
        }

    opt_meta: dict[str, Any] = {
        "optimized": applied,
        "normalized": True,
        "shares_ok": shares_ok,
        "mode": "optimize" if applied else "simulate",
        "strategy": opt.get("strategy") if applied else None,
        "trials": opt.get("trials") if opt.get("ok") else 0,
        "ca_ht_best": opt_ca if opt.get("ok") else None,
        "marge_nette_best": opt_marge if opt.get("ok") else None,
        "user_ca_ht": user_ca,
        "user_marge_nette": user_marge,
        "improvement_possible": improvement and not applied,
        "suggestion": suggestion,
    }

    # Prédictions IA
    ai_note = ""
    ai_available = False
    ai_by: dict[str, Any] = {}
    feature_overrides = params_to_feature_overrides(params)
    feature_overrides["hotel_nb_chambres"] = n
    feature_overrides["hotel_to_annuel"] = to
    if derniere_reno is not None:
        feature_overrides["hotel_derniere_reno"] = derniere_reno
    try:
        preds_payload = _ai_predict_three(code, feature_overrides)
        preds = (preds_payload or {}).get("by_solution") if preds_payload else None
        pred_kind = (preds_payload or {}).get("main_target") or MAIN_TARGET
        if preds:
            ai_available = True
            k_markup = float(VENTES_SUR_ACHATS)
            ai_note = (
                f"IA : prédiction du **montant des ventes** (CA mensuel). "
                f"Règle marge : ventes = {k_markup:g} × achats "
                f"(marge produit = ventes − ventes/{k_markup:g} = "
                f"{(1 - 1 / k_markup) * 100:.0f} % du CA). "
                "Marge nette = marge produit − coûts ; "
                "amort = CAPEX60 / marge nette mensuelle ; annuel = mensuel × 12."
            )
            for c in CONCEPTS:
                pred_val = preds.get(c)
                cs = raw_by[c]
                if pred_val is not None:
                    # Cible IA = montant_ventes ; legacy montant_marge → convertie
                    if pred_kind == "montant_marge":
                        mp_ai = float(pred_val)
                        ca_ai = ventes_from_marge(mp_ai, k_markup)
                    else:
                        ca_ai = float(pred_val)
                        mp_ai = marge_from_ventes(ca_ai, k_markup)
                    block = _pnl_block(
                        cs,
                        ca_override=float(ca_ai),
                        marge_produit_override=float(mp_ai),
                    )
                    block["main_target"] = "montant_ventes"
                    block["pred_raw"] = round(float(pred_val), 2)
                    block["pred_kind_model"] = pred_kind
                    block["ventes_sur_achats"] = k_markup
                    block["montant_achats_ia"] = round(
                        float(ca_ai) / k_markup if k_markup else 0.0, 2
                    )
                    ai_by[c] = block
                else:
                    ai_by[c] = _empty_pnl(
                        cout=float(cs.cout_mensuel or 0),
                        capex=float(cs.capex or 0),
                    )
        else:
            ai_note = (
                "Estimation modèle indisponible pour le moment — "
                "consultez l'onglet Simulateur."
            )
            for c in CONCEPTS:
                cs = raw_by[c]
                ai_by[c] = _empty_pnl(
                    cout=float(cs.cout_mensuel or 0),
                    capex=float(cs.capex or 0),
                )
    except Exception:
        ai_note = (
            "Estimation modèle indisponible pour le moment — "
            "consultez l'onglet Simulateur."
        )
        for c in CONCEPTS:
            cs = raw_by.get(c)
            if cs is not None:
                ai_by[c] = _empty_pnl(
                    cout=float(cs.cout_mensuel or 0),
                    capex=float(cs.capex or 0),
                )
            else:
                ai_by[c] = _empty_pnl()

    recommended, order, reasons = reco_engine.recommend_tree(
        req_for_reco
        or SimulationRequest(
            identity=identity,
            operating=operating,
            services=services_obj,
            store=_store_for("SIMPLY", mix_fb),
        ),
        m_lin=m_lin,
        to=to,
    )
    if m_lin_forced:
        reasons = list(reasons) + [
            f"Mètres linéaires forcés à {int(MIN_M_LIN)} (minimum métier)."
        ]

    def _best_margin(by: dict[str, Any]) -> str:
        return max(
            CONCEPTS,
            key=lambda c: (
                -1e18
                if (by.get(c) or {}).get("not_profitable")
                else float((by.get(c) or {}).get("marge_nette_mensuelle") or -1e18)
            ),
        )

    best_margin = _best_margin(sim_by)
    best_margin_ai = _best_margin(ai_by) if ai_available else None

    lifestyle_on = [
        CLIENT_NEED_LABELS.get(k, k)
        for k in LIBERTY_NFB_NEEDS
        if needs.get(k, False)
    ]

    # Legacy flatten
    by_solution_legacy: dict[str, Any] = {}
    for c in CONCEPTS:
        s, a = sim_by[c], ai_by.get(c) or {}
        by_solution_legacy[c] = {
            "ca_simule_mensuel": s.get("ca_mensuel"),
            "ca_predit_mensuel": a.get("ca_mensuel"),
            "ca_fb_mensuel": s.get("ca_fb_mensuel"),
            "ca_nfb_mensuel": s.get("ca_nfb_mensuel"),
            "marge_produit_mensuelle": s.get("marge_produit_mensuelle"),
            "cout_mensuel": s.get("cout_mensuel"),
            "capex": s.get("capex"),
            "marge_nette_mensuelle": s.get("marge_nette_mensuelle"),
            "marge_nette_annuelle": s.get("marge_nette_annuelle"),
            "status": s.get("status"),
            "amort_months": s.get("amort_months"),
            "amort_years": s.get("amort_years"),
        }

    # Pilotes exposés pour UI info (zone gauche)
    pilots = {c: get_pilot(c) for c in CONCEPTS}

    return {
        "ok": True,
        "schema": "simulateur_rules_v1",
        "hotel": {
            "hotel_code": code,
            "hotel_name": identity_name,
            "hotel_brand": identity_brand,
            "nb_chambres": int(round(n)),
            "taux_occupation": round(to, 4),
            "guests_per_chambre": round(g, 3),
            "derniere_reno": derniere_reno,
            "nb_restaurants": int(nb_restaurants),
            "nb_bars": int(nb_bars),
            "has_pool": bool(has_pool),
            "has_vitrine": bool(has_vitrine),
            "m_lin": int(round(m_lin)),
            "m_lin_forced_min": m_lin_forced,
            "mix_fb": round(mix_fb, 4),
            "mix_nf": round(1.0 - mix_fb, 4),
            "contract": contract,
            "agencement": agencement,
            "nb_scanners": nb_scanners,
            "nb_caisses": nb_caisses,
            "nb_vitrines": nb_vitrines,
            "nb_frigos_froid": nb_frigos_froid,
            "nb_frigos_ambiant": nb_frigos_ambiant,
            "hotel_params": params,
            "client_needs": needs,
            "shares_fb": shares_fb,
            "shares_nfb": shares_nfb,
        },
        "category_shares": category_shares_out,
        "assortment": opt_meta,
        "recommended_solution": recommended,
        "concept_order": order,
        "recommendation_reasons": reasons,
        "best_margin_solution": best_margin,
        "best_margin_solution_ai": best_margin_ai,
        "lifestyle_categories_on": lifestyle_on,
        "pilots": {
            c: {
                "ventes": p["ventes"],
                "ca_fb": p["ca_fb"],
                "ca_nfb": p["ca_nfb"],
                "mix_fb": p["mix_fb"],
                "ml_ref": p.get("ml_ref"),
                "frigo_ref": p.get("frigo_ref"),
                "coeff_fb": p["coeff_fb"],
                "coeff_nfb": p["coeff_nfb"],
            }
            for c, p in pilots.items()
        },
        "simulator": {
            "label": "Simulateur",
            "by_solution": sim_by,
            "best_margin_solution": best_margin,
        },
        "ai": {
            "label": "Estimation IA",
            "available": ai_available,
            "note": ai_note,
            "by_solution": ai_by,
            "best_margin_solution": best_margin_ai,
        },
        "by_solution": by_solution_legacy,
        "ai_note": ai_note,
    }


def _ai_predict_three(
    hotel_code: str,
    feature_overrides: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Trois prédictions (un modèle final par solution).

    Retourne ``{"main_target": str, "by_solution": {SOL: float}}``.
    Cible attendue : **montant_ventes** (MAIN_TARGET). Les anciens bundles
    encore tagués ``montant_marge`` sont signalés pour conversion côté P&L.
    """
    import numpy as np
    import pandas as pd

    try:
        from accor.hotel_solutions import SOLUTIONS
        from accor.model_data import MAIN_TARGET
        from accor.model_final import (
            build_stacked_features,
            get_final_top_model,
            load_final_model,
        )
        from accor.model_train import (
            _load_model_frame,
            get_top_model,
            load_design_model,
        )
    except Exception:
        return None

    try:
        frame, meta = _load_model_frame()
    except Exception:
        return None
    if frame is None or frame.empty:
        return None

    # Priorité : constante code (montant_ventes), puis meta, puis bundle
    meta_main = MAIN_TARGET or (meta or {}).get("main_target") or "montant_ventes"
    main_target = (
        str(meta_main).strip() if meta_main else "montant_ventes"
    ) or "montant_ventes"

    overrides = {k: v for k, v in (feature_overrides or {}).items() if v is not None}
    work = frame.copy()
    work["hotel_code"] = work["hotel_code"].astype(str).str.strip()
    code = str(hotel_code).strip()
    sub = work.loc[work["hotel_code"] == code]
    base_src = sub.copy() if not sub.empty else work.iloc[[0]].copy()

    out: dict[str, float] = {}
    for sol in SOLUTIONS:
        try:
            top = get_final_top_model(solution=sol) or get_top_model(solution=sol)
            if not top:
                continue
            mid = str(top.get("id") or top.get("name") or "")
            is_final = top.get("tier") == "final" or top.get("kind") == "stacked_final"
            loaded = (
                load_final_model(mid, solution=sol)
                if is_final
                else load_design_model(mid, solution=sol)
            )
            bundle = loaded.get("bundle") or {}
            conf = loaded.get("meta") or {}
            model = bundle.get("model")
            feature_cols = list(
                bundle.get("feature_cols") or conf.get("feature_cols") or []
            )
            if model is None or not feature_cols:
                continue
            # Cible du bundle final (mono-cible) prime si connue
            bundle_target = (
                conf.get("main_target")
                or bundle.get("main_target")
                or conf.get("target")
                or bundle.get("target")
            )
            sol_target = main_target
            if isinstance(bundle_target, str) and bundle_target.strip() in (
                "montant_marge",
                "montant_ventes",
            ):
                sol_target = bundle_target.strip()
            row = base_src.copy()
            imid = conf.get("intermediate_model_id") or bundle.get(
                "intermediate_model_id"
            )
            if imid:
                try:
                    inter = load_design_model(str(imid), solution=sol)["bundle"]
                    expanded, feature_cols, _, _ = build_stacked_features(
                        work, meta or {}, inter
                    )
                    exp = expanded.loc[
                        expanded["hotel_code"].astype(str).str.strip() == code
                    ]
                    row = exp if not exp.empty else expanded.iloc[[0]].copy()
                except Exception:
                    pass
            for col, val in overrides.items():
                row[col] = val
            for c in feature_cols:
                if c not in row.columns:
                    row[c] = 0.0
            X = (
                row[feature_cols]
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0.0)
                .to_numpy(dtype=float)
            )
            if X.ndim == 1:
                X = X.reshape(1, -1)
            pred = np.asarray(model.predict(X), dtype=float)
            # Multi-output intermédiaire : prendre la colonne de la main_target
            if pred.ndim == 2 and pred.shape[1] > 1:
                tcols = list(
                    bundle.get("target_cols")
                    or conf.get("target_cols")
                    or (meta or {}).get("target_columns")
                    or []
                )
                if sol_target in tcols:
                    idx = tcols.index(sol_target)
                    out[sol] = round(float(np.nanmean(pred[:, idx])), 2)
                else:
                    out[sol] = round(float(np.nanmean(pred[:, 0])), 2)
            else:
                out[sol] = round(float(np.nanmean(pred)), 2)
            # Mémoriser la cible effective (premier modèle chargé)
            main_target = sol_target
        except Exception:
            continue
    if not out:
        return None
    return {"main_target": main_target, "by_solution": out}
