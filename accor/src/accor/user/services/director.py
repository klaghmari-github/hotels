"""
Simulation « directeur » — résultats simples pour l'interface user.

Pas de détail de formules : CA simulé, CA estimé par le modèle, coûts,
marge, solution recommandée. Les réglages (m linéaires, mix, vitrine,
sous-catégories) restent en session côté navigateur.
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


def director_simulate(body: dict[str, Any]) -> dict[str, Any]:
    """
    Calcule les 3 solutions pour un hôtel.

    Body attendu (champs optionnels sauf hotel_code) :
      hotel_code, hotel_name, hotel_brand,
      nb_chambres, taux_occupation, guests_per_chambre,
      m_lin, mix_fb, has_vitrine, client_needs
    """
    code = str(body.get("hotel_code") or "").strip()
    if not code:
        return {"ok": False, "error": "Indiquez un code hôtel."}

    # Contexte fiche (sans écrire en base)
    identity_name = str(body.get("hotel_name") or "").strip()
    identity_brand = str(body.get("hotel_brand") or "").strip()
    try:
        from accor.user.services.hotel_context import HotelContextBuilder

        ctx = HotelContextBuilder().build(code, fetch_if_missing=True)
        ident = ctx.identity or {}
        op0 = ctx.operating if isinstance(ctx.operating, dict) else {}
        if not identity_name:
            identity_name = str(ident.get("hotel_name") or "")
        if not identity_brand:
            identity_brand = str(ident.get("hotel_brand") or "")
        def_n = float(op0.get("nb_chambres") or getattr(ctx.operating, "nb_chambres", 100) or 100)
        def_to = float(op0.get("taux_occupation") or getattr(ctx.operating, "taux_occupation", 0.7) or 0.7)
        def_g = float(op0.get("guests_per_chambre") or getattr(ctx.operating, "guests_per_chambre", 1.7) or 1.7)
        services0 = getattr(ctx, "services", None) or {}
        if isinstance(services0, dict):
            def_vitrine = bool(
                services0.get("lobby_fridge")
                or services0.get("has_vitrine")
                or services0.get("vitrine_refrigeree")
            )
        else:
            def_vitrine = bool(getattr(services0, "lobby_fridge", False))
    except Exception:
        def_n, def_to, def_g, def_vitrine = 100.0, 0.7, 1.7, False

    n = _f(body.get("nb_chambres"), def_n) or def_n
    to = _f(body.get("taux_occupation"), def_to) or def_to
    if to > 1.0:
        to /= 100.0
    g = _f(body.get("guests_per_chambre"), def_g) or def_g
    m_lin = _f(body.get("m_lin"), 6.0) or 6.0
    mix_fb = _f(body.get("mix_fb"), 0.70) or 0.70
    if mix_fb > 1.0:
        mix_fb /= 100.0
    mix_fb = min(max(mix_fb, 0.0), 1.0)
    has_vitrine = body.get("has_vitrine")
    if has_vitrine is None:
        has_vitrine = def_vitrine
    else:
        has_vitrine = bool(has_vitrine)

    needs = body.get("client_needs") if isinstance(body.get("client_needs"), dict) else {}
    needs = {str(k): bool(v) for k, v in needs.items()}
    from accor.user.rules.coeffs import RULE3_FB_COEFFS, RULE3_NFB_COEFFS

    for k in list(RULE3_FB_COEFFS) + list(RULE3_NFB_COEFFS):
        needs.setdefault(k, True)

    ref = RodReference()
    rev = RevenueRules(ref)
    cost = CostRules(ref)
    reco_engine = RecommendationRules()

    by_solution: dict[str, Any] = {}
    req_for_reco: SimulationRequest | None = None

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
            services=HotelServices(lobby_fridge=bool(has_vitrine)),
            client_profile=ClientProfile(client_needs=dict(needs)),
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
        marge_nette = marge_prod - cout
        by_solution[concept] = {
            "ca_simule_mensuel": round(ca, 2),
            "ca_predit_mensuel": None,  # rempli plus bas si modèle dispo
            "marge_produit_mensuelle": round(marge_prod, 2),
            "cout_mensuel": round(cout, 2),
            "capex": round(capex, 2),
            "marge_nette_mensuelle": round(marge_nette, 2),
            "marge_nette_annuelle": round(marge_nette * 12, 2),
        }

    # Prédictions IA (3 scénarios solution) — optionnel
    ai_note = ""
    try:
        preds = _ai_predict_three(code, n, to, g)
        if preds:
            for c in CONCEPTS:
                if preds.get(c) is not None:
                    by_solution[c]["ca_predit_mensuel"] = preds[c]
            ai_note = "Estimation modèle sur la base des hôtels déjà équipés."
        else:
            ai_note = "Estimation modèle indisponible pour le moment — le simulateur reste la référence."
    except Exception:
        ai_note = "Estimation modèle indisponible pour le moment — le simulateur reste la référence."

    recommended, order, reasons = reco_engine.recommend_tree(
        req_for_reco or SimulationRequest(),
        m_lin=m_lin,
        to=to,
    )
    # Si la reco pointe une solution peu rentable, on le dit sans cacher les autres
    best_margin = max(
        CONCEPTS,
        key=lambda c: float(by_solution[c]["marge_nette_mensuelle"] or -1e18),
    )

    lifestyle_on = [
        CLIENT_NEED_LABELS.get(k, k)
        for k in LIBERTY_NFB_NEEDS
        if needs.get(k, False)
    ]

    return {
        "ok": True,
        "hotel": {
            "hotel_code": code,
            "hotel_name": identity_name,
            "hotel_brand": identity_brand,
            "nb_chambres": int(round(n)),
            "taux_occupation": round(to, 4),
            "guests_per_chambre": round(g, 3),
            "has_vitrine": bool(has_vitrine),
            "m_lin": round(m_lin, 2),
            "mix_fb": round(mix_fb, 4),
            "mix_nf": round(1.0 - mix_fb, 4),
        },
        "recommended_solution": recommended,
        "concept_order": order,
        "recommendation_reasons": reasons,
        "best_margin_solution": best_margin,
        "lifestyle_categories_on": lifestyle_on,
        "by_solution": by_solution,
        "ai_note": ai_note,
        "disclaimer": (
            "Les chiffres sont des estimations pour vous aider à choisir. "
            "Ils ne remplacent pas un budget d'investissement validé en interne."
        ),
    }


def _ai_predict_three(
    hotel_code: str,
    nb_chambres: float,
    to: float,
    guests: float,
) -> dict[str, float] | None:
    """
    Trois prédictions de CA mensuel (simply / liberty / connected = 1).

    Utilise le modèle final si possible, sinon l'intermédiaire.
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

    # Ligne type pour l'hôtel (moyenne des mois de modélisation si dispo)
    work = frame.copy()
    work["hotel_code"] = work["hotel_code"].astype(str).str.strip()
    sub = work.loc[work["hotel_code"] == hotel_code]
    if sub.empty:
        # hôtel hors historique : on part d'une ligne moyenne et on force l'exploitation
        row = work.mean(numeric_only=True).to_dict()
        base = work.iloc[[0]].copy()
        for k, v in row.items():
            if k in base.columns:
                base[k] = v
    else:
        # moyenne numérique des mois connus
        base = sub.mean(numeric_only=True).to_frame().T
        for col in sub.columns:
            if col not in base.columns:
                base[col] = sub[col].iloc[0]
        base = base.reset_index(drop=True)

    base["hotel_code"] = hotel_code
    base["hotel_nb_chambres"] = nb_chambres
    if "hotel_to_annuel" in base.columns:
        base["hotel_to_annuel"] = to
    for col in SOLUTION_FLAG_COLS:
        if col not in base.columns:
            base[col] = 0

    model = None
    feature_cols: list[str] = []
    # Final
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
                    # Reprendre une ligne pour notre hôtel après stacking
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
                except Exception:
                    # fallback intermédiaire seul
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

    for col in feature_cols:
        if col not in base.columns:
            base[col] = 0.0

    out: dict[str, float] = {}
    for sol in CONCEPTS:
        sc = base.copy()
        for c in CONCEPTS:
            col = FLAG_BY[c]
            if col in sc.columns or col in feature_cols:
                sc[col] = 1 if c == sol else 0
                if col not in sc.columns:
                    sc[col] = 1 if c == sol else 0
        try:
            import pandas as pd

            X = (
                sc[feature_cols]
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0.0)
                .to_numpy(dtype=float)
            )
            pred = model.predict(X)
            import numpy as np

            pred = np.asarray(pred, dtype=float)
            if pred.ndim > 1:
                pred = pred[:, 0]
            out[sol] = round(float(pred.mean()), 2)
        except Exception:
            continue
    return out or None
