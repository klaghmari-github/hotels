"""
Business Logic for ROD-IA - understands the métier.

- Client/buyer funnel from ROD params (nb_ch, to, guests_per_ch)
- Mix / conversion rates from predicted profile
- Coherent reallocation when user changes desired mix (e.g. no alcohol)
- Full P&L simulation (revenue from profile + m_lin scaling, costs from ROD, margin)
- Simple optimizer for best concept/m_lin/mix
"""

from typing import Dict, List, Tuple
import numpy as np

def compute_funnel(nb_ch: int, to: float, guests_per_ch: float = 1.7) -> Dict:
    """Compute expected clients and buyers per month from hotel params."""
    ch_occ = nb_ch * to
    cl_heb_jour = ch_occ * guests_per_ch
    cl_heb_mois = cl_heb_jour * 30.5
    # Assume some % of guests buy something in the corner (typical 30-40% from pivots)
    buyers_mois = cl_heb_mois * 0.35
    return {
        "ch_occ": round(ch_occ, 1),
        "cl_heb_mois": round(cl_heb_mois, 1),
        "buyers_mois": round(buyers_mois, 1),
        "total_clients_mois": round(cl_heb_mois, 1)
    }

def profile_to_mix(full_targets: Dict[str, float]) -> Dict[str, float]:
    """From full predicted targets (montant columns), compute % mix per GAMME."""
    gammes = {}
    total = 0.0
    for col, val in full_targets.items():
        if "__montant" in col:
            parts = col.split("__")
            if len(parts) > 2:
                g = parts[2]
                gammes[g] = gammes.get(g, 0.0) + val
                total += val
    if total == 0:
        return {}
    return {g: round(v / total, 4) for g, v in gammes.items()}

def reallocate_mix(base_mix: Dict[str, float], desired: Dict[str, float], total: float = 1.0) -> Dict[str, float]:
    """
    Reallocate when user sets desired percentages.
    desired e.g. {"ALCOOL": 0.0, "F&B": 0.10} or per gamme.
    Remaining share is redistributed proportionally to original base_mix of the non-forced categories.
    """
    if not base_mix:
        return {}

    # Identify forced (set explicitly, including 0)
    forced = {g: v for g, v in desired.items() if g in base_mix}
    remaining = [g for g in base_mix if g not in forced]

    forced_sum = sum(forced.values())
    if forced_sum > 1.0:
        forced = {g: v / forced_sum for g, v in forced.items()}
        forced_sum = 1.0

    free = max(0.0, 1.0 - forced_sum)

    # Original weight of remaining
    orig_remaining = sum(base_mix.get(g, 0) for g in remaining)
    if orig_remaining == 0:
        orig_remaining = 1.0

    new_mix = {}
    for g in forced:
        new_mix[g] = forced[g]

    for g in remaining:
        weight = base_mix.get(g, 0) / orig_remaining
        new_mix[g] = weight * free

    # Scale to total (for absolute)
    new_mix = {g: v * total for g, v in new_mix.items()}
    # Normalize to exact total
    s = sum(new_mix.values())
    if s > 0:
        new_mix = {g: round(v * total / s, 2) for g, v in new_mix.items()}
    return new_mix

def simulate_pnl(nb_ch: int, m_lin: float, concept: str, adjusted_profile: Dict[str, float],
                 f_b_share: float = 0.5) -> Dict:
    """
    Simple P&L using ROD-like formulas + adjusted ML profile.
    Revenue = sum of (profile * m_lin_factor)
    Costs = simplified from m_lin and concept.
    """
    m_lin_ref = {"SIMPLY": 6.0, "LIBERTY": 8.0, "CONNECTED": 7.0}.get(concept, 6.0)
    m_lin_factor = m_lin / m_lin_ref

    base_revenue = sum(adjusted_profile.values()) * m_lin_factor

    # Very simplified costs (inspired by rod_full_simulator)
    cost_per_m = {"SIMPLY": 1800, "LIBERTY": 2100, "CONNECTED": 2400}.get(concept, 2000)
    annual_cost = m_lin * cost_per_m * 0.8   # amort + opex

    margin = base_revenue - annual_cost
    margin_pct = (margin / base_revenue * 100) if base_revenue > 0 else 0

    return {
        "revenue": round(base_revenue, 0),
        "costs": round(annual_cost, 0),
        "margin": round(margin, 0),
        "margin_pct": round(margin_pct, 1),
        "m_lin_factor": round(m_lin_factor, 2)
    }

def recommend_best(nb_ch: int, base_profile: Dict[str, float], m_lin_range=(3,10)) -> List[Dict]:
    """Grid search simple recommendations."""
    concepts = ["SIMPLY", "LIBERTY", "CONNECTED"]
    results = []
    for c in concepts:
        for m in [round(x,1) for x in np.arange(m_lin_range[0], m_lin_range[1]+0.1, 0.5)]:
            pnl = simulate_pnl(nb_ch, m, c, base_profile)
            pnl["concept"] = c
            pnl["m_lin"] = m
            results.append(pnl)
    # Sort by margin
    results.sort(key=lambda x: x["margin"], reverse=True)
    return results[:3]  # top 3

def compute_volume_from_rod(nb_ch: int, to: float = 0.78, guests_per_ch: float = 1.7, 
                            buyer_conversion: float = 0.35) -> float:
    """Compute expected monthly buyers (volume) from ROD params."""
    ch_occ = nb_ch * to
    cl_heb_jour = ch_occ * guests_per_ch
    cl_heb_mois = cl_heb_jour * 30.5
    buyers_mois = cl_heb_mois * buyer_conversion
    return round(buyers_mois, 1)

def predict_coherent_with_mix(base_by_gamme: Dict[str, float], desired_mix: Dict[str, float], 
                              base_total: float, volume_buyers: float = None) -> Dict[str, float]:
    """
    Core métier logic:
    - base_by_gamme: from ML prediction (natural profile)
    - desired_mix: user's choice in % (e.g. {'ALCOOL': 0.0, 'FOOD_SALEE': 0.4, ...} or partial)
    - Reallocate the profile to respect desired % while preserving relative attractiveness from ML.
    - Scale to desired volume if provided.
    Returns new_by_gamme with coherent totals.
    """
    if not base_by_gamme or sum(base_by_gamme.values()) == 0:
        return base_by_gamme

    # Normalize desired to sum to 1.0 (user can set some, others redistribute)
    explicit = {g: max(0.0, float(v)) for g, v in desired_mix.items() if g in base_by_gamme}
    forced_sum = sum(explicit.values())
    if forced_sum > 1.0:
        explicit = {g: v / forced_sum for g, v in explicit.items()}
        forced_sum = 1.0

    remaining = [g for g in base_by_gamme if g not in explicit]
    free_share = max(0.0, 1.0 - forced_sum)

    # Original weights of remaining (from ML base = attractiveness)
    orig_rem_sum = sum(base_by_gamme.get(g, 0) for g in remaining)
    if orig_rem_sum <= 0:
        orig_rem_sum = 1.0

    new_profile = {}
    for g in explicit:
        new_profile[g] = explicit[g] * base_total

    for g in remaining:
        weight = base_by_gamme.get(g, 0) / orig_rem_sum
        new_profile[g] = weight * free_share * base_total

    # If volume_buyers given, we could further scale, but here we keep the base_total as anchor
    # (volume is used to set expectations, but ML gives the CA level)
    new_total = sum(new_profile.values())
    if new_total > 0:
        scale = base_total / new_total
        new_profile = {g: round(v * scale, 2) for g, v in new_profile.items()}

    return new_profile
