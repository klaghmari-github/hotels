"""
server.py - Backend Flask pour l'application web ROD-IA
- Charge le modèle ML + scaler + features
- Construit un vecteur de features pour un nouvel hôtel (sans utiliser de moyenne globale des pivots)
- Expose /predict et /simulate
- Sert les fichiers web/ (index.html, style, js)
"""

import os
import json
import joblib
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, send_from_directory

try:
    from rod_simulator import RODSimulator, RODParameters
    ROD_SIM = RODSimulator()
    HAS_ROD_SIM = True
except Exception as e:
    HAS_ROD_SIM = False
    print("[server] rod_simulator not available:", e)

try:
    import business_logic as biz
    HAS_BIZ = True
except Exception as e:
    HAS_BIZ = False
    print("[server] business_logic not available:", e)

try:
    from enrich_hotel import geocode_hotel, fetch_poi, fetch_weather, compute_poi_features, aggregate_weather
    HAS_ENRICH = True
except Exception as e:
    HAS_ENRICH = False
    print("[server] enrich_hotel not fully available, will use mock:", e)

app = Flask(__name__, static_folder="web", static_url_path="/static")

# ---------------- Load artifacts ----------------
print("[server] Loading artifacts...")
MODEL = joblib.load("artifacts/model.joblib")
SCALER = joblib.load("artifacts/scaler.joblib")
FEATURE_COLS = json.load(open("artifacts/feature_cols.json"))
TARGET_COLS = json.load(open("artifacts/target_cols.json"))
META = json.load(open("artifacts/meta.json"))
BASE_ROWS = json.load(open("artifacts/base_rows.json"))

NB_CH_COL = META["nb_ch_col"]

# Simple location profiles (used to override POI in the base vector)
LOCATION_PROFILES = {
    "centre_ville_dense": {"fb_mult": 2.8, "notfb_mult": 2.2},
    "aeroport":          {"fb_mult": 1.6, "notfb_mult": 1.1},
    "montagne":          {"fb_mult": 0.7, "notfb_mult": 0.9},
    "centre_commercial": {"fb_mult": 3.5, "notfb_mult": 2.8},
    "banlieue":          {"fb_mult": 1.1, "notfb_mult": 1.3},
}

def get_base_row(location: str = "centre_ville_dense"):
    """Return a base feature row (from one of the saved base pivots)."""
    # Use first saved base row as starting point
    row = pd.Series(BASE_ROWS[0])
    # Apply location scaling on POI columns
    prof = LOCATION_PROFILES.get(location, LOCATION_PROFILES["centre_ville_dense"])
    for col in FEATURE_COLS:
        if col.startswith("fb_0_"):
            row[col] = row.get(col, 0) * prof["fb_mult"]
        elif col.startswith("not_fb_0_"):
            row[col] = row.get(col, 0) * prof["notfb_mult"]
    return row

def build_feature_vector(nb_chambres: int = None, location: str = "centre_ville_dense", overrides: dict = None) -> pd.DataFrame:
    """
    Build the input vector for the model.
    Starts from a real pivot template.
    Applies high-level changes + any user-provided overrides for individual features.
    This allows full control over the descriptive input values.
    """
    base = get_base_row(location)
    if nb_chambres is not None and NB_CH_COL in base.index:
        base[NB_CH_COL] = nb_chambres

    # Apply user overrides (the core of "saisie des valeurs d'entrée")
    if overrides:
        for col, val in overrides.items():
            if col in base.index:
                base[col] = val

    vec = base.reindex(FEATURE_COLS).fillna(0).to_frame().T
    return vec

def aggregate_prediction(pred_array):
    """Turn the 286 predictions into nice aggregates + breakdowns by GAMME for what-if."""
    df = pd.DataFrame([pred_array], columns=TARGET_COLS)
    mont_cols = [c for c in TARGET_COLS if "__montant" in c]
    vent_cols = [c for c in TARGET_COLS if "__nbr_ventes" in c]

    total_ca = float(df[mont_cols].sum(axis=1).values[0])
    total_ventes = float(df[vent_cols].sum(axis=1).values[0])

    # F&B share
    fb_mont = [c for c in mont_cols if "__FB__" in c]
    fb_share = float(df[fb_mont].sum(axis=1).values[0] / total_ca) if total_ca > 0 else 0.5

    # Monthly totals
    monthly = {}
    for m in range(1, 13):
        mkey = f"m{m:02d}"
        m_cols = [c for c in mont_cols if c.startswith(mkey + "__")]
        monthly[mkey] = round(float(df[m_cols].sum(axis=1).values[0]), 0)

    # Breakdown by GAMME (sum of montants across all months and types)
    by_gamme = {}
    gammes = set()
    for c in mont_cols:
        parts = c.split("__")
        if len(parts) >= 3:
            gammes.add(parts[2])

    for g in sorted(gammes):
        g_cols = [c for c in mont_cols if f"__{g}__montant" in c]
        by_gamme[g] = round(float(df[g_cols].sum(axis=1).values[0]), 2)

    # Breakdown by TYPE
    fb_total = round(float(df[fb_mont].sum(axis=1).values[0]), 2)
    non_fb_mont = [c for c in mont_cols if "__NON_FB__" in c]
    non_fb_total = round(float(df[non_fb_mont].sum(axis=1).values[0]), 2)

    # Sample targets
    sample = {}
    for example in ["m01__FB__ALCOOL__montant", "m01__FB__FOOD_SALEE__montant", "m01__NON_FB__ACCESSOIRES__montant"]:
        matching = [c for c in TARGET_COLS if example in c]
        if matching:
            sample[example] = round(float(df[matching[0]].values[0]), 2)

    # Full targets for advanced use / export
    full_targets = {col: round(float(val), 2) for col, val in zip(TARGET_COLS, pred_array)}

    # Mix profile (percentage of total CA per GAMME) - this is what we reallocate
    gamme_mix = {g: round(val / total_ca, 4) if total_ca > 0 else 0 for g, val in by_gamme.items()}

    return {
        "total_ca": round(total_ca, 0),
        "total_ventes": round(total_ventes, 0),
        "fb_share": round(fb_share, 3),
        "monthly_ca": monthly,
        "by_gamme": by_gamme,
        "by_type": {"FB": fb_total, "NON_FB": non_fb_total},
        "gamme_mix": gamme_mix,
        "sample_targets": sample,
        "full_targets": full_targets
    }

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("web", path)

@app.route("/api/feature_info", methods=["GET"])
def api_feature_info():
    """Returns info to build the input form: feature list + a sample base vector + the nb_ch column."""
    base = get_base_row("centre_ville_dense")
    sample = {col: float(base[col]) for col in FEATURE_COLS[:50]}  # limit for UI sanity

    # Human friendly short names
    def short_name(col):
        parts = col.split("__")
        return parts[-1] if len(parts) > 1 else col

    feature_meta = []
    for col in FEATURE_COLS[:80]:  # top 80 for the advanced editor
        feature_meta.append({
            "name": col,
            "short": short_name(col),
            "value": float(base[col])
        })

    return jsonify({
        "nb_ch_col": NB_CH_COL,
        "total_features": len(FEATURE_COLS),
        "sample_base": sample,
        "editable_features": feature_meta,
        "important_cols": [NB_CH_COL] + [c for c in FEATURE_COLS if "restaurant" in c or "reunion" in c or c.startswith("fb_") or c.startswith("not_fb_") or "LON" in c or "LAT" in c][:15]
    })

@app.route("/api/predict", methods=["POST"])
def api_predict():
    data = request.get_json(force=True)

    # Support both old high-level and new ROD-style inputs from screens
    nb = data.get("nb_ch") or data.get("nb_chambres")
    if nb is not None:
        nb = int(nb)

    loc = data.get("location", "centre_ville_dense")

    overrides = data.get("overrides", {}) or {}

    # Map ROD screen fields to feature overrides
    if "nb_ch" in data or "nb_chambres" in data:
        overrides[NB_CH_COL] = nb

    vec = build_feature_vector(nb_chambres=nb, location=loc, overrides=overrides)
    scaled = SCALER.transform(vec)
    pred = MODEL.predict(scaled)[0]

    result = aggregate_prediction(pred)
    if nb is not None:
        result["nb_ch"] = nb
    result["location"] = loc
    result["used_overrides_count"] = len(overrides)

    # For full CSV export of the 286 cibles
    result["full_targets"] = {col: round(float(p), 2) for col, p in zip(TARGET_COLS, pred)}

    # Business context
    if HAS_BIZ:
        funnel = biz.compute_funnel(nb or 180, 0.78)
        result["funnel"] = funnel

    return jsonify(result)


@app.route("/api/enrich", methods=["POST"])
def api_enrich():
    """Auto compute POI + Meteo from hotel name/city. Director does NOT enter these."""
    data = request.get_json(force=True)
    hotel_name = data.get("hotel_name", "")
    city = data.get("city", "")

    if not HAS_ENRICH or not hotel_name:
        # Mock for demo: return plausible values for a city center
        mock = {
            "fb_0_1km": 15, "fb_0_2km": 45, "fb_0_3km": 80, "fb_0_4km": 120, "fb_0_5km": 180,
            "not_fb_0_1km": 8, "not_fb_0_2km": 25, "not_fb_0_3km": 50, "not_fb_0_4km": 70, "not_fb_0_5km": 95,
            "m01_dwpt_mean": 4.5, "m01_prcp_mean": 0.08  # simplified weather
        }
        return jsonify({"enriched_features": mock, "note": "Mock (no real enrich)"})

    try:
        geo = geocode_hotel(hotel_name, city)
        if not geo:
            return jsonify({"error": "Could not geocode"}), 400

        poi = fetch_poi(geo["lat"], geo["lon"])
        poi_feats = compute_poi_features(poi)

        weather = fetch_weather(geo["lat"], geo["lon"])
        weather_feats = aggregate_weather(weather)

        features = {**poi_feats, **weather_feats}
        return jsonify({"enriched_features": features, "geo": geo})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    """
    Simple simulation using the predicted CA + m_lin + concept.
    In a fuller version we would call rod_full_simulator.estimate_revenue / estimate_costs
    """
    data = request.get_json(force=True)
    nb = int(data.get("nb_chambres", 180))
    m_lin = float(data.get("m_lin", 5.0))
    concept = data.get("concept", "SIMPLY")
    loc = data.get("location", "centre_ville_dense")

    # Get ML prediction
    vec = build_feature_vector(nb, loc)
    scaled = SCALER.transform(vec)
    pred = MODEL.predict(scaled)[0]
    ml_agg = aggregate_prediction(pred)

    base_ca = ml_agg["total_ca"]

    # Very simple ROD-like scaling (inspired by the real simulator)
    m_lin_ref = 5.0
    m_lin_factor = m_lin / m_lin_ref

    # Concept margin hints (from Excel knowledge in the project)
    concept_margin = {
        "SIMPLY": 0.32,
        "LIBERTY": 0.27,
        "CONNECTED": 0.24,
    }.get(concept, 0.28)

    # Revenue estimate (ML base scaled)
    revenue = base_ca * m_lin_factor

    # Very rough cost model (amort + opex proportional to m_lin)
    # (in real app we would use the full COST tables + rod_full_simulator)
    cost_per_m = {"SIMPLY": 1850, "LIBERTY": 2100, "CONNECTED": 2400}.get(concept, 2000)
    annual_cost = m_lin * cost_per_m * 0.75   # amort + opex simplified

    margin = revenue * concept_margin - annual_cost
    margin_pct = (margin / revenue * 100) if revenue > 0 else 0

    return jsonify({
        "revenue": round(revenue, 0),
        "annual_cost": round(annual_cost, 0),
        "margin": round(margin, 0),
        "margin_pct": round(margin_pct, 1),
        "ml_base_ca": ml_agg["total_ca"],
        "m_lin_factor": round(m_lin_factor, 2),
        "concept": concept,
    })


@app.route("/api/rod_simulate", methods=["POST"])
def api_rod_simulate():
    """Use the official ROD simulator logic from rod_simulator.py"""
    data = request.get_json(force=True)

    if not HAS_ROD_SIM:
        return jsonify({"error": "ROD simulator not available"}), 500

    p = RODParameters(
        nb_ch=int(data.get("nb_ch", 180)),
        guests_per_ch=float(data.get("guests_per_ch", 1.7)),
        to=float(data.get("to", 0.78)),
        m_lin=float(data.get("m_lin", 5.0)),
        f_b_share=float(data.get("f_b_share", 0.5)),
        concept=data.get("concept", "SIMPLY"),
    )

    res = ROD_SIM.simulate(p)
    return jsonify(res)

def reallocate_mix(base_by_gamme, desired_mix):
    """
    Reallocate percentages when user changes desired mix.
    desired_mix: dict like {"ALCOOL": 0.0, "FOOD_SALEE": 0.15, ...} or partial.
    Rules:
    - If a category is set to 0 or a specific value, remove its share.
    - Renormalize the remaining categories proportionally to their original mix (within the affected group if possible, else global).
    - Return new_by_gamme with same total_ca.
    """
    if not base_by_gamme:
        return {}

    total = sum(base_by_gamme.values())
    if total == 0:
        return base_by_gamme

    # Normalize desired to sum 1 (user can set partial, we respect explicit 0s and renormalize rest)
    explicit = {g: v for g, v in desired_mix.items() if g in base_by_gamme}
    remaining_gammes = [g for g in base_by_gamme if g not in explicit or explicit.get(g, None) is None]

    # Sum of explicitly set (including 0s)
    set_sum = sum(v for v in explicit.values() if v is not None)

    if set_sum > 1.0:
        # Normalize the explicit ones first
        explicit = {g: v / set_sum for g, v in explicit.items() if v is not None}
        set_sum = 1.0

    free_share = 1.0 - set_sum

    # Original mix of the remaining
    orig_remaining_sum = sum(base_by_gamme.get(g, 0) for g in remaining_gammes) / total
    if orig_remaining_sum == 0:
        orig_remaining_sum = 1.0

    new_by_gamme = {}
    for g, orig_val in base_by_gamme.items():
        if g in explicit:
            new_by_gamme[g] = explicit[g] * total
        else:
            orig_pct = (orig_val / total) / orig_remaining_sum if orig_remaining_sum > 0 else 0
            new_by_gamme[g] = orig_pct * free_share * total

    # Round and adjust to exact total (due to floating point)
    new_total = sum(new_by_gamme.values())
    if new_total != total and new_total > 0:
        factor = total / new_total
        for g in new_by_gamme:
            new_by_gamme[g] *= factor

    return {g: round(v, 2) for g, v in new_by_gamme.items()}


@app.route("/api/reallocate", methods=["POST"])
def api_reallocate():
    data = request.get_json(force=True)
    base_by_gamme = data.get("base_by_gamme", {})
    desired = data.get("desired_mix", {})
    total_ca = data.get("total_ca", sum(base_by_gamme.values()))

    if HAS_BIZ:
        new_by_gamme = biz.predict_coherent_with_mix(base_by_gamme, desired, total_ca)
    else:
        new_by_gamme = reallocate_mix(base_by_gamme, desired)  # fallback

    return jsonify({
        "new_by_gamme": new_by_gamme,
        "new_total_ca": round(sum(new_by_gamme.values()), 0),
        "applied_desired": desired
    })

@app.route("/api/business_simulate", methods=["POST"])
def api_business_simulate():
    """Full métier flow (as per user spec):
    - POI/Meteo auto via enrich (not entered)
    - Director saisie: ROD hotel info + desired mix in %
    - ML gives natural profile
    - Volume from ROD (funnel)
    - If desired_mix provided: reallocate using model's natural attractiveness (coherent %)
    - Return natural vs forced + gain + P&L + best proposal
    """
    data = request.get_json(force=True)

    nb = int(data.get("nb_ch", 180))
    m_lin = float(data.get("m_lin", 5.0))
    concept = data.get("concept", "SIMPLY")
    desired_mix = data.get("desired_mix", {}) or {}
    to = float(data.get("to", 0.78))

    # 1. Base prediction from features (enriched + ROD saisies)
    loc = data.get("location", "centre_ville_dense")
    overrides = data.get("overrides", {})
    overrides[NB_CH_COL] = nb
    vec = build_feature_vector(nb_chambres=nb, location=loc, overrides=overrides)
    scaled = SCALER.transform(vec)
    pred = MODEL.predict(scaled)[0]
    base = aggregate_prediction(pred)

    natural_total = base["total_ca"]
    natural_profile = base["by_gamme"]

    # 2. Volume (what director controls indirectly via TO, nb_ch etc.)
    volume_buyers = biz.compute_volume_from_rod(nb, to) if HAS_BIZ else natural_total / 30.0

    # 3. Forced or natural
    if desired_mix and HAS_BIZ:
        adjusted = biz.predict_coherent_with_mix(natural_profile, desired_mix, natural_total)
        adj_total = sum(adjusted.values())
        gain = adj_total - natural_total
    else:
        adjusted = natural_profile
        adj_total = natural_total
        gain = 0

    # 4. Business numbers
    if HAS_BIZ:
        pnl = biz.simulate_pnl(nb, m_lin, concept, adjusted)
        recos = biz.recommend_best(nb, natural_profile)
    else:
        pnl = {"revenue": adj_total * (m_lin/5.0), "costs": m_lin*1800, "margin": 0, "margin_pct": 0}
        recos = []

    return jsonify({
        "natural_total": round(natural_total, 0),
        "natural_profile": natural_profile,
        "adjusted_total": round(adj_total, 0),
        "adjusted_profile": adjusted,
        "gain": round(gain, 0),
        "pnl": pnl,
        "recommendations": recos[:3],
        "volume_buyers_mois": round(volume_buyers, 1),
        "note": "POI/Meteo auto. Mix % from director. Coherent reallocation using ML shape."
    })


if __name__ == "__main__":
    print("Starting ROD-IA web server on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
