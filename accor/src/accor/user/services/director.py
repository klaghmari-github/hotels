"""
Simulation « directeur » — résultats simples pour l'interface user.

Deux vues distinctes (même saisie utilisateur, sans étiqueter sim vs IA
dans le formulaire) :

* **simulateur** — CA règles métier + coûts + marge nette
* **ia** — CA prédit par le modèle + mêmes coûts + marge recalculée

Les réglages restent en session côté navigateur (pas d'écriture base).
"""

from __future__ import annotations

from typing import Any

from accor.hotel_solutions import SOLUTION_FLAG_COLS
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
from accor.user.rules.recommendation import RecommendationRules
from accor.user.rules.revenue import RevenueRules

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")
FLAG_BY = {
    "SIMPLY": "hotel_solution_simply",
    "LIBERTY": "hotel_solution_liberty",
    "CONNECTED": "hotel_solution_connected",
}


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


def _money_block(
    *,
    ca: float | None,
    cout: float,
    capex: float,
    marge_produit: float | None = None,
) -> dict[str, Any]:
    """Bloc CA / coûts / marge pour une solution (sim ou IA)."""
    ca_v = None if ca is None else round(float(ca), 2)
    cout_v = round(float(cout), 2)
    capex_v = round(float(capex), 2)
    if ca_v is None:
        return {
            "ca_mensuel": None,
            "marge_produit_mensuelle": None,
            "cout_mensuel": cout_v,
            "capex": capex_v,
            "marge_nette_mensuelle": None,
            "marge_nette_annuelle": None,
        }
    if marge_produit is None:
        # fallback grossier si pas de marge produit (ne devrait pas arriver côté sim)
        marge_prod = ca_v * 0.35
    else:
        marge_prod = float(marge_produit)
    marge_nette = marge_prod - cout_v
    return {
        "ca_mensuel": ca_v,
        "marge_produit_mensuelle": round(marge_prod, 2),
        "cout_mensuel": cout_v,
        "capex": capex_v,
        "marge_nette_mensuelle": round(marge_nette, 2),
        "marge_nette_annuelle": round(marge_nette * 12, 2),
    }


def director_simulate(body: dict[str, Any]) -> dict[str, Any]:
    """
    Calcule les 3 solutions pour un hôtel.

    Body attendu (champs optionnels sauf hotel_code) :

      hotel_code, hotel_name, hotel_brand,
      hotel_params (dict colonnes hotel_data + guests_per_chambre),
      m_lin, mix_fb, client_needs
      (+ aliases plats legacy : nb_chambres, has_pool, …)
    """
    from accor.user.hotel_form import (
        params_to_feature_overrides,
        params_to_services,
        resolve_params,
    )
    from accor.user.models import DEFAULT_CLIENT_NEEDS
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

    # Saisie user (hotel_params) + aliases plats rétrocompat
    user_params: dict[str, Any] = {}
    if isinstance(body.get("hotel_params"), dict):
        user_params.update(body["hotel_params"])
    alias = {
        "hotel_nb_chambres": body.get("nb_chambres"),
        "hotel_to_annuel": body.get("taux_occupation"),
        "guests_per_chambre": body.get("guests_per_chambre"),
        "hotel_derniere_reno": body.get("derniere_reno"),
        "hotel_f_b_restaurant": body.get("nb_restaurants"),
        "hotel_f_b_bar": body.get("nb_bars") if body.get("nb_bars") is not None else body.get("has_bar"),
        "hotel_non_f_b_piscine": body.get("has_pool"),
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
    m_lin = _f(body.get("m_lin"), def_m_lin) or def_m_lin
    # m_lin corner dédié si fourni dans params et pas dans body
    if body.get("m_lin") in (None, "") and params.get("hotel_metres_lineaires_dedies_corner"):
        m_lin = float(params["hotel_metres_lineaires_dedies_corner"]) or m_lin
    mix_fb = _f(body.get("mix_fb"), def_mix) or def_mix
    if mix_fb > 1.0:
        mix_fb /= 100.0
    mix_fb = min(max(mix_fb, 0.0), 1.0)

    services_map = params_to_services(params)
    has_vitrine = bool(services_map.get("lobby_fridge") or services_map.get("has_vitrine"))
    has_pool = bool(services_map.get("pool") or services_map.get("has_pool"))
    nb_restaurants = int(services_map.get("nb_restaurants") or 0)
    nb_bars = int(services_map.get("nb_bars") or 0)
    derniere_reno = _i(params.get("hotel_derniere_reno"), None)

    needs = dict(DEFAULT_CLIENT_NEEDS)
    raw_needs = body.get("client_needs") if isinstance(body.get("client_needs"), dict) else {}
    for k, v in raw_needs.items():
        needs[str(k)] = bool(v)
    for k in list(RULE3_FB_COEFFS) + list(RULE3_NFB_COEFFS):
        needs.setdefault(k, False)

    # Clientèle % depuis hotel_params si fournis
    profile_kw: dict[str, Any] = {"client_needs": dict(needs)}
    if params.get("hotel_loisirs_pct") is not None:
        profile_kw["loisirs_pct"] = float(params["hotel_loisirs_pct"])
    if params.get("hotel_affaires_pct") is not None:
        profile_kw["affaires_pct"] = float(params["hotel_affaires_pct"])
    if params.get("hotel_national_pct") is not None:
        profile_kw["national_pct"] = float(params["hotel_national_pct"])
    if params.get("hotel_international_pct") is not None:
        profile_kw["international_pct"] = float(params["hotel_international_pct"])

    ref = RodReference()
    rev = RevenueRules(ref)
    cost = CostRules(ref)
    reco_engine = RecommendationRules()

    sim_by: dict[str, Any] = {}
    req_for_reco: SimulationRequest | None = None

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

    for concept in CONCEPTS:
        req = SimulationRequest(
            identity=HotelIdentity(
                hotel_code=code,
                hotel_name=identity_name,
                hotel_brand=identity_brand,
            ),
            operating=HotelOperating(
                nb_chambres=int(round(n)),
                taux_occupation=to,
                guests_per_chambre=g,
            ),
            services=services_obj,
            client_profile=ClientProfile(**profile_kw),
            store=StoreConfig(
                concept=concept,
                m_lin=m_lin,
                mix_fb=mix_fb,
                mix_nf=1.0 - mix_fb,
            ),
        )
        if concept == CONCEPTS[0]:
            req_for_reco = req

        rev_res = rev.compute(req, concept)
        cost_res = cost.compute(req, concept)
        ca = float(rev_res.ca_ht_mensuel or 0)
        marge_prod = float(rev_res.marge_produit_mensuelle or 0)
        cout = float(cost_res.monthly_cost or 0)
        capex = float(cost_res.capex or 0)
        sim_by[concept] = _money_block(
            ca=ca, cout=cout, capex=capex, marge_produit=marge_prod
        )

    # Prédictions IA (3 scénarios solution) — mêmes coûts, CA modèle
    ai_note = ""
    ai_available = False
    ai_by: dict[str, Any] = {}
    feature_overrides = params_to_feature_overrides(params)
    feature_overrides["hotel_nb_chambres"] = n
    feature_overrides["hotel_to_annuel"] = to
    if derniere_reno is not None:
        feature_overrides["hotel_derniere_reno"] = derniere_reno
    try:
        preds = _ai_predict_three(code, feature_overrides)
        if preds:
            ai_available = True
            ai_note = "Estimation modèle sur la base des hôtels déjà équipés."
            for c in CONCEPTS:
                ca_ai = preds.get(c)
                # Marge produit proportionnelle au ratio marge/CA du simulateur
                sim = sim_by[c]
                ca_sim = sim.get("ca_mensuel") or 0
                mp_sim = sim.get("marge_produit_mensuelle") or 0
                if ca_ai is not None and ca_sim and ca_sim > 0:
                    mp_ai = float(mp_sim) * (float(ca_ai) / float(ca_sim))
                elif ca_ai is not None:
                    mp_ai = float(ca_ai) * 0.35
                else:
                    mp_ai = None
                ai_by[c] = _money_block(
                    ca=ca_ai,
                    cout=float(sim.get("cout_mensuel") or 0),
                    capex=float(sim.get("capex") or 0),
                    marge_produit=mp_ai,
                )
        else:
            ai_note = (
                "Estimation modèle indisponible pour le moment — "
                "consultez l'onglet Simulateur."
            )
            for c in CONCEPTS:
                sim = sim_by[c]
                ai_by[c] = _money_block(
                    ca=None,
                    cout=float(sim.get("cout_mensuel") or 0),
                    capex=float(sim.get("capex") or 0),
                )
    except Exception:
        ai_note = (
            "Estimation modèle indisponible pour le moment — "
            "consultez l'onglet Simulateur."
        )
        for c in CONCEPTS:
            sim = sim_by[c]
            ai_by[c] = _money_block(
                ca=None,
                cout=float(sim.get("cout_mensuel") or 0),
                capex=float(sim.get("capex") or 0),
            )

    recommended, order, reasons = reco_engine.recommend_tree(
        req_for_reco or SimulationRequest(),
        m_lin=m_lin,
        to=to,
    )
    best_margin = max(
        CONCEPTS,
        key=lambda c: float(sim_by[c].get("marge_nette_mensuelle") or -1e18),
    )
    best_margin_ai = None
    if ai_available:
        best_margin_ai = max(
            CONCEPTS,
            key=lambda c: float(
                (ai_by.get(c) or {}).get("marge_nette_mensuelle") or -1e18
            ),
        )

    lifestyle_on = [
        CLIENT_NEED_LABELS.get(k, k)
        for k in LIBERTY_NFB_NEEDS
        if needs.get(k, False)
    ]

    # Compat legacy (anciens clients API) : ca_simule + ca_predit côte à côte
    by_solution_legacy: dict[str, Any] = {}
    for c in CONCEPTS:
        s, a = sim_by[c], ai_by.get(c) or {}
        by_solution_legacy[c] = {
            "ca_simule_mensuel": s.get("ca_mensuel"),
            "ca_predit_mensuel": a.get("ca_mensuel"),
            "marge_produit_mensuelle": s.get("marge_produit_mensuelle"),
            "cout_mensuel": s.get("cout_mensuel"),
            "capex": s.get("capex"),
            "marge_nette_mensuelle": s.get("marge_nette_mensuelle"),
            "marge_nette_annuelle": s.get("marge_nette_annuelle"),
        }

    return {
        "ok": True,
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
            "m_lin": round(m_lin, 2),
            "mix_fb": round(mix_fb, 4),
            "mix_nf": round(1.0 - mix_fb, 4),
            "hotel_params": params,
        },
        "recommended_solution": recommended,
        "concept_order": order,
        "recommendation_reasons": reasons,
        "best_margin_solution": best_margin,
        "best_margin_solution_ai": best_margin_ai,
        "lifestyle_categories_on": lifestyle_on,
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
        # legacy
        "by_solution": by_solution_legacy,
        "ai_note": ai_note,
    }


def _ai_predict_three(
    hotel_code: str,
    feature_overrides: dict[str, Any] | None = None,
) -> dict[str, float] | None:
    """
    Trois prédictions de CA mensuel (simply / liberty / connected = 1).

    ``feature_overrides`` applique les valeurs saisies par le directeur
    (chambres, TO, rénovation, restos/bars, piscine, vitrine…) sur la ligne
    model_data avant prédiction.
    """
    try:
        from accor.model_train import _load_model_frame, load_design_model, get_top_model
        from accor.model_final import get_final_top_model, load_final_model, build_stacked_features
    except Exception:
        return None

    try:
        frame, meta = _load_model_frame()
    except Exception:
        return None
    if frame is None or frame.empty:
        return None

    overrides = {k: v for k, v in (feature_overrides or {}).items() if v is not None}

    work = frame.copy()
    work["hotel_code"] = work["hotel_code"].astype(str).str.strip()
    sub = work.loc[work["hotel_code"] == hotel_code]
    if sub.empty:
        row = work.mean(numeric_only=True).to_dict()
        base = work.iloc[[0]].copy()
        for k, v in row.items():
            if k in base.columns:
                base[k] = v
    else:
        base = sub.mean(numeric_only=True).to_frame().T
        for col in sub.columns:
            if col not in base.columns:
                base[col] = sub[col].iloc[0]
        base = base.reset_index(drop=True)

    base["hotel_code"] = hotel_code
    for col, val in overrides.items():
        if col in base.columns or True:
            base[col] = val
    for col in SOLUTION_FLAG_COLS:
        if col not in base.columns:
            base[col] = 0

    model = None
    feature_cols: list[str] = []
    try:
        top = get_final_top_model()
        if top:
            mid = top.get("id") or top.get("name")
            loaded = load_final_model(str(mid))
            bundle = loaded.get("bundle") or {}
            conf = loaded.get("meta") or {}
            model = bundle.get("model")
            feature_cols = list(bundle.get("feature_cols") or conf.get("feature_cols") or [])
            imid = conf.get("intermediate_model_id") or bundle.get("intermediate_model_id")
            if imid and model is not None:
                try:
                    inter = load_design_model(str(imid))["bundle"]
                    expanded, feature_cols, _, _ = build_stacked_features(
                        work, meta or {}, inter
                    )
                    exp = expanded.loc[
                        expanded["hotel_code"].astype(str).str.strip() == hotel_code
                    ]
                    if not exp.empty:
                        base = exp.mean(numeric_only=True).to_frame().T
                        for col in exp.columns:
                            if col not in base.columns:
                                base[col] = exp[col].iloc[0]
                        base = base.reset_index(drop=True)
                        base["hotel_code"] = hotel_code
                        for col, val in overrides.items():
                            base[col] = val
                except Exception:
                    inter_loaded = load_design_model(str(imid))
                    model = (inter_loaded.get("bundle") or {}).get("model")
                    feature_cols = list(
                        (inter_loaded.get("bundle") or {}).get("feature_cols")
                        or (inter_loaded.get("meta") or {}).get("feature_cols")
                        or []
                    )
    except Exception:
        model = None

    if model is None:
        try:
            top = get_top_model()
            if not top:
                return None
            mid = top.get("id") or top.get("name")
            loaded = load_design_model(str(mid))
            model = (loaded.get("bundle") or {}).get("model")
            feature_cols = list(
                (loaded.get("bundle") or {}).get("feature_cols")
                or (loaded.get("meta") or {}).get("feature_cols")
                or []
            )
        except Exception:
            return None

    if model is None or not feature_cols:
        return None

    # Ré-appliquer overrides après stacking / fallback
    for col, val in overrides.items():
        base[col] = val

    for col in feature_cols:
        if col not in base.columns:
            base[col] = 0.0

    out: dict[str, float] = {}
    for sol in CONCEPTS:
        sc = base.copy()
        for c in CONCEPTS:
            col = FLAG_BY[c]
            sc[col] = 1 if c == sol else 0
        try:
            import numpy as np
            import pandas as pd

            X = (
                sc[feature_cols]
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0.0)
                .to_numpy(dtype=float)
            )
            pred = model.predict(X)
            pred = np.asarray(pred, dtype=float)
            if pred.ndim > 1:
                pred = pred[:, 0]
            out[sol] = round(float(pred.mean()), 2)
        except Exception:
            continue
    return out or None
