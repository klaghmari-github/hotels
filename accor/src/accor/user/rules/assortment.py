"""
Répartition assortiment F&B / N-F&B (parts relatives par catégorie).

- Parts **relatives à la catégorie** : somme F&B = 1, somme N-F&B = 1.
- Produits désactivés → part 0 (exclus de la normalisation).
- Règle 3 : score = base(produits actifs) × qualité(répartition vs égalitaire).
- Optimisation : grille mix F&B + stratégies de parts → max CA HT.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from accor.user.rules.coeffs import (
    CLIENT_NEED_LABELS,
    RULE3_FB_COEFFS,
    RULE3_NFB_COEFFS,
)

FB_KEYS: tuple[str, ...] = tuple(RULE3_FB_COEFFS.keys())
NFB_KEYS: tuple[str, ...] = tuple(RULE3_NFB_COEFFS.keys())

# Grille mix F&B pour optimisation (complément N-F&B = 1 − mix)
# Pas de 10 % imposé côté UI ; pas de 5 % pour explorer le R2
MIX_FB_GRID: tuple[float, ...] = (
    0.20,
    0.30,
    0.40,
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
    0.75,
    0.80,
    0.90,
)


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        x = float(v)
        if x != x:  # NaN
            return default
        return x
    except (TypeError, ValueError):
        return default


def normalize_shares(
    shares: dict[str, float] | None,
    keys: Iterable[str],
    *,
    enabled: dict[str, bool] | None = None,
) -> dict[str, float]:
    """
    Normalise les parts pour que la somme fasse 1 sur les produits actifs.

    Si somme ≤ 0 → répartitionage égalitaire sur les actifs.
    Produits inactifs → 0.
    """
    keys = list(keys)
    out: dict[str, float] = {k: 0.0 for k in keys}
    active: list[str] = []
    for k in keys:
        on = True
        if enabled is not None:
            on = bool(enabled.get(k, False))
        if not on:
            continue
        raw = _as_float((shares or {}).get(k), 0.0)
        if raw < 0:
            raw = 0.0
        # part strictement nulle mais produit actif → reste actif (sera égalisé si tout 0)
        out[k] = raw
        active.append(k)

    if not active:
        return out

    s = sum(out[k] for k in active)
    if s <= 1e-12:
        eq = 1.0 / len(active)
        for k in active:
            out[k] = eq
        return out

    coef = 1.0 / s
    for k in active:
        out[k] = out[k] * coef
    return out


def enabled_from_shares(
    shares: dict[str, float] | None,
    keys: Iterable[str],
    *,
    needs: dict[str, bool] | None = None,
) -> dict[str, bool]:
    """Actif si besoin True (si fourni) et/ou part > 0."""
    out: dict[str, bool] = {}
    for k in keys:
        if needs is not None and k in needs:
            out[k] = bool(needs[k])
        else:
            out[k] = _as_float((shares or {}).get(k), 0.0) > 1e-12
    return out


def needs_from_shares(shares_fb: dict[str, float], shares_nfb: dict[str, float]) -> dict[str, bool]:
    needs: dict[str, bool] = {}
    for k in FB_KEYS:
        needs[k] = _as_float(shares_fb.get(k), 0.0) > 1e-12
    for k in NFB_KEYS:
        needs[k] = _as_float(shares_nfb.get(k), 0.0) > 1e-12
    return needs


def equal_shares(keys: Iterable[str], enabled: dict[str, bool] | None = None) -> dict[str, float]:
    keys = list(keys)
    active = [k for k in keys if enabled is None or enabled.get(k, True)]
    out = {k: 0.0 for k in keys}
    if not active:
        return out
    eq = 1.0 / len(active)
    for k in active:
        out[k] = eq
    return out


def prop_coeff_shares(
    coeffs: dict[str, float],
    enabled: dict[str, bool] | None = None,
    *,
    power: float = 1.0,
) -> dict[str, float]:
    """Parts ∝ coefficient^power (relatives aux actifs)."""
    keys = list(coeffs.keys())
    active = [k for k in keys if enabled is None or enabled.get(k, True)]
    out = {k: 0.0 for k in keys}
    if not active:
        return out
    weights = []
    for k in active:
        w = max(float(coeffs[k]), 1e-9) ** power
        weights.append(w)
    s = sum(weights)
    for k, w in zip(active, weights):
        out[k] = w / s
    return out


def top_heavy_shares(
    coeffs: dict[str, float],
    enabled: dict[str, bool] | None = None,
    *,
    top_share: float = 0.55,
) -> dict[str, float]:
    """Concentre top_share sur le meilleur coeff, le reste à égalité."""
    keys = list(coeffs.keys())
    active = [k for k in keys if enabled is None or enabled.get(k, True)]
    out = {k: 0.0 for k in keys}
    if not active:
        return out
    if len(active) == 1:
        out[active[0]] = 1.0
        return out
    best = max(active, key=lambda k: float(coeffs[k]))
    rest = [k for k in active if k != best]
    out[best] = top_share
    eq = (1.0 - top_share) / len(rest)
    for k in rest:
        out[k] = eq
    return out


def cumul_rule3_from_shares(
    shares: dict[str, float] | None,
    coeffs: dict[str, float],
) -> float:
    """
    Cumul règle 3 à partir de parts relatives (somme ≈ 1 sur actifs).

    - base = Σ coeffs des produits avec part > 0  (équivalent assortiment binaire)
    - qualité = (Σ c·s) / (Σ c · 1/|E|)  = |E| · (Σ c·s) / Σ c
      → 1 si répartition égalitaire ; > 1 si on pèse les forts coeffs
    - cumul = base × qualité  (borné pour rester réaliste)
    """
    active = [k for k, c in coeffs.items() if _as_float((shares or {}).get(k), 0.0) > 1e-12]
    if not active:
        return 0.0
    # normaliser
    ssum = sum(_as_float((shares or {}).get(k), 0.0) for k in active)
    if ssum <= 1e-12:
        return sum(float(coeffs[k]) for k in active)
    base = sum(float(coeffs[k]) for k in active)
    if base <= 0:
        return 0.0
    weighted = sum(
        float(coeffs[k]) * (_as_float((shares or {}).get(k), 0.0) / ssum) for k in active
    )
    equal_w = base / len(active)
    quality = weighted / equal_w if equal_w > 0 else 1.0
    quality = min(max(quality, 0.35), 1.85)
    return base * quality


def parse_shares_payload(
    body: dict[str, Any],
    *,
    default_needs: dict[str, bool] | None = None,
) -> tuple[dict[str, float], dict[str, float], dict[str, bool], bool]:
    """
    Extrait parts F&B / N-F&B + needs + flag normalisé.

    Accepte :
      category_shares: { fb: {...}, nfb: {...} }
      shares_fb / shares_nfb
      client_needs (bool) → parts égalitaires sur actifs
    """
    needs = dict(default_needs or {})
    raw_needs = body.get("client_needs") if isinstance(body.get("client_needs"), dict) else {}
    for k, v in raw_needs.items():
        needs[str(k)] = bool(v)

    cat = body.get("category_shares") if isinstance(body.get("category_shares"), dict) else {}
    shares_fb = cat.get("fb") if isinstance(cat.get("fb"), dict) else body.get("shares_fb")
    shares_nfb = cat.get("nfb") if isinstance(cat.get("nfb"), dict) else body.get("shares_nfb")
    if not isinstance(shares_fb, dict):
        shares_fb = {}
    if not isinstance(shares_nfb, dict):
        shares_nfb = {}

    # Si pas de parts mais needs → égalitaire
    if not shares_fb and needs:
        shares_fb = equal_shares(FB_KEYS, {k: bool(needs.get(k, False)) for k in FB_KEYS})
    if not shares_nfb and needs:
        shares_nfb = equal_shares(NFB_KEYS, {k: bool(needs.get(k, False)) for k in NFB_KEYS})

    en_fb = enabled_from_shares(shares_fb, FB_KEYS, needs=needs if needs else None)
    en_nfb = enabled_from_shares(shares_nfb, NFB_KEYS, needs=needs if needs else None)
    # Si needs vides, déduire des parts
    if not needs:
        needs = needs_from_shares(shares_fb or {}, shares_nfb or {})
        en_fb = enabled_from_shares(shares_fb, FB_KEYS, needs=needs)
        en_nfb = enabled_from_shares(shares_nfb, NFB_KEYS, needs=needs)

    fb_n = normalize_shares(shares_fb, FB_KEYS, enabled=en_fb)
    nfb_n = normalize_shares(shares_nfb, NFB_KEYS, enabled=en_nfb)
    needs = needs_from_shares(fb_n, nfb_n)
    return fb_n, nfb_n, needs, True


def build_share_strategies(
    enabled_fb: dict[str, bool],
    enabled_nfb: dict[str, bool],
) -> list[tuple[str, dict[str, float], dict[str, float]]]:
    """Stratégies de répartition candidates pour l'optimiseur."""
    strats: list[tuple[str, dict[str, float], dict[str, float]]] = []
    strats.append(
        (
            "equal",
            equal_shares(FB_KEYS, enabled_fb),
            equal_shares(NFB_KEYS, enabled_nfb),
        )
    )
    strats.append(
        (
            "prop_coeff",
            prop_coeff_shares(RULE3_FB_COEFFS, enabled_fb, power=1.0),
            prop_coeff_shares(RULE3_NFB_COEFFS, enabled_nfb, power=1.0),
        )
    )
    strats.append(
        (
            "prop_coeff_sq",
            prop_coeff_shares(RULE3_FB_COEFFS, enabled_fb, power=2.0),
            prop_coeff_shares(RULE3_NFB_COEFFS, enabled_nfb, power=2.0),
        )
    )
    strats.append(
        (
            "top_heavy",
            top_heavy_shares(RULE3_FB_COEFFS, enabled_fb, top_share=0.55),
            top_heavy_shares(RULE3_NFB_COEFFS, enabled_nfb, top_share=0.55),
        )
    )
    return strats


def shares_for_api(shares_fb: dict[str, float], shares_nfb: dict[str, float]) -> dict[str, Any]:
    """Payload UI : parts + % + labels."""

    def _pack(shares: dict[str, float], coeffs: dict[str, float]) -> list[dict[str, Any]]:
        rows = []
        for k, c in coeffs.items():
            s = _as_float(shares.get(k), 0.0)
            rows.append(
                {
                    "id": k,
                    "label": CLIENT_NEED_LABELS.get(k, k),
                    "share": round(s, 4),
                    "pct": round(s * 100.0, 1),
                    "enabled": s > 1e-12,
                    "coeff": c,
                }
            )
        return rows

    sum_fb = sum(_as_float(v) for v in shares_fb.values())
    sum_nfb = sum(_as_float(v) for v in shares_nfb.values())
    return {
        "fb": _pack(shares_fb, RULE3_FB_COEFFS),
        "nfb": _pack(shares_nfb, RULE3_NFB_COEFFS),
        "sum_fb": round(sum_fb, 4),
        "sum_nfb": round(sum_nfb, 4),
        "normalized": abs(sum_fb - 1.0) < 0.02 and abs(sum_nfb - 1.0) < 0.02,
    }


def optimize_repartition(
    *,
    simulate_fn,
    enabled_fb: dict[str, bool],
    enabled_nfb: dict[str, bool],
    mix_grid: Iterable[float] = MIX_FB_GRID,
    m_lin: float = 6.0,
    user_mix_fb: float | None = None,
) -> dict[str, Any]:
    """
    Pour chaque mix F&B de la grille (et le mix user si fourni), teste
    plusieurs répartitions de sous-catégories ; score = (marge_nette, CA)
    de la solution recommandée par l'arbre (règles simulateur).

    ``simulate_fn(mix_fb, shares_fb, shares_nfb) -> dict``
    attendu : ``ca_ht``, ``marge_nette`` (optionnel), ``recommended``.
    """
    best: dict[str, Any] | None = None
    best_score = (-1e99, -1e99)  # (marge_nette, ca_ht)
    trials = 0

    mixes: list[float] = []
    seen: set[float] = set()
    if user_mix_fb is not None:
        um = min(max(float(user_mix_fb), 0.05), 0.95)
        mixes.append(round(um, 4))
        seen.add(round(um, 4))
    for m in mix_grid:
        m = min(max(float(m), 0.05), 0.95)
        key = round(m, 4)
        if key not in seen:
            seen.add(key)
            mixes.append(key)

    strategies = build_share_strategies(enabled_fb, enabled_nfb)
    for mix_fb in mixes:
        for name, sh_fb, sh_nfb in strategies:
            trials += 1
            try:
                res = simulate_fn(mix_fb, sh_fb, sh_nfb)
            except Exception:
                continue
            if not res:
                continue
            ca = _as_float(res.get("ca_ht"), -1e99)
            # Prefer explicit marge nette ; fallback CA
            marge = res.get("marge_nette")
            if marge is None:
                marge = ca
            else:
                marge = _as_float(marge, ca)
            score = (float(marge), float(ca))
            if score > best_score:
                best_score = score
                best = {
                    "strategy": name,
                    "mix_fb": mix_fb,
                    "mix_nf": round(1.0 - mix_fb, 4),
                    "shares_fb": sh_fb,
                    "shares_nfb": sh_nfb,
                    "ca_ht": ca,
                    "marge_nette": float(marge),
                    "recommended": res.get("recommended"),
                    "result": res,
                }
    if best is None:
        sh_fb = equal_shares(FB_KEYS, enabled_fb)
        sh_nfb = equal_shares(NFB_KEYS, enabled_nfb)
        return {
            "ok": False,
            "error": "Aucune répartition évaluable",
            "mix_fb": 0.7,
            "shares_fb": sh_fb,
            "shares_nfb": sh_nfb,
            "trials": trials,
        }
    best["ok"] = True
    best["trials"] = trials
    best["m_lin"] = m_lin
    best["category_shares"] = shares_for_api(best["shares_fb"], best["shares_nfb"])
    return best
