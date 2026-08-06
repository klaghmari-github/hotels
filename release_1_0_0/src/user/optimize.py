"""
Optimisation de mix (type F&B / gammes) par balayage 10 %.

Pour chaque cle d'un groupe, on teste 0.0, 0.1, …, 1.0 ; l'ecart par rapport
a la valeur initiale est redistribue equitabelement sur les autres cles du groupe.
Chaque configuration est evaluee par sim_v1, sim_v2 et ml (3 solutions).
On retient la ligne au plus grand CA estime.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from src.user.business import enrich_prediction_with_costs, recommend

logger = logging.getLogger(__name__)

STEP = 0.1


def _grid(step: float = STEP) -> list[float]:
    n = int(round(1.0 / step))
    return [round(i * step, 10) for i in range(0, n + 1)]


def _norm_mix(mix: dict[str, Any] | None, defaults: dict[str, float]) -> dict[str, float]:
    raw = dict(mix or defaults)
    out: dict[str, float] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = max(0.0, float(v))
        except (TypeError, ValueError):
            continue
    if not out:
        out = dict(defaults)
    s = sum(out.values())
    if s <= 1e-12:
        n = len(out)
        return {k: 1.0 / n for k in out}
    return {k: v / s for k, v in out.items()}


def vary_one(
    base: dict[str, float],
    key: str,
    new_val: float,
) -> dict[str, float]:
    """
    Place `key` a new_val (clamp 0..1) et redistribue l'ecart equitabelement
    sur les autres cles du groupe, puis renormalise si besoin.
    """
    keys = list(base.keys())
    if key not in base:
        raise KeyError(key)
    others = [k for k in keys if k != key]
    new_val = max(0.0, min(1.0, float(new_val)))
    base_val = float(base[key])
    delta = base_val - new_val  # >0 si on baisse key → a redistribuer aux autres

    if not others:
        return {key: 1.0}

    out: dict[str, float] = {key: new_val}
    share = delta / len(others)
    for o in others:
        out[o] = max(0.0, float(base[o]) + share)

    s = sum(out.values())
    if s <= 1e-12:
        # cas extreme (tous a 0) : mass sur key
        return {k: (1.0 if k == key else 0.0) for k in keys}
    if abs(s - 1.0) > 1e-9:
        out = {k: v / s for k, v in out.items()}
    return {k: round(v, 8) for k, v in out.items()}


def mix_configs_for_group(
    base: dict[str, float],
    group_name: str,
    step: float = STEP,
) -> list[dict[str, Any]]:
    """Toutes les configs de variation pour un groupe (hors baseline pure)."""
    configs: list[dict[str, Any]] = []
    for key in base:
        for target in _grid(step):
            # skip si quasi identique a la base (evite doublons)
            if abs(float(base[key]) - target) < 1e-9:
                continue
            varied = vary_one(base, key, target)
            configs.append(
                {
                    "group": group_name,
                    "varied_key": key,
                    "varied_target": target,
                    "base_value": float(base[key]),
                    "mix": varied,
                }
            )
    return configs


def combine_gamme_mix(
    type_mix: dict[str, float],
    gamme_fb: dict[str, float],
    gamme_nfb: dict[str, float],
) -> dict[str, float]:
    """
    UI (parts dans la famille, somme 1) → format sim_v2
    (parts du total natures, somme 1) :
    part_totale = weight(type) * part_famille.
    Aligné sur t_dataset_mix : metric_value / nombre_natures_global.
    """
    w_fb = 0.0
    w_nfb = 0.0
    for k, v in type_mix.items():
        key = str(k).lower().replace("&", "").replace("_", " ")
        if "non" in key:
            w_nfb += float(v)
        elif "f" in key and "b" in key:
            w_fb += float(v)
    total = w_fb + w_nfb
    if total <= 1e-12:
        w_fb, w_nfb = 0.7, 0.3
    else:
        w_fb, w_nfb = w_fb / total, w_nfb / total
    out: dict[str, float] = {}
    for k, v in gamme_fb.items():
        out[str(k)] = out.get(str(k), 0.0) + w_fb * float(v)
    for k, v in gamme_nfb.items():
        out[str(k)] = out.get(str(k), 0.0) + w_nfb * float(v)
    s = sum(out.values())
    if s > 1e-12:
        out = {k: round(v / s, 8) for k, v in out.items()}
    return out


def run_mix_optimization(
    *,
    hotel_nb_chambres: float,
    hotel_to_annuel: float,
    hotel_guests_per_chambre: float,
    metres_lineaires: float,
    type_mix: dict[str, Any],
    gamme_mix_fb: dict[str, Any],
    gamme_mix_nfb: dict[str, Any],
    hotel_code: str | None = None,
    solutions: list[str] | None = None,
    evaluate_fn: Callable[..., list[dict[str, Any]]],
    step: float = STEP,
) -> dict[str, Any]:
    """
    evaluate_fn(type_mix=..., gamme_mix=..., gamme_mix_fb=..., gamme_mix_nfb=...)
    → liste de resultats enrichis (engine, solution, ca_monthly, ...).
    """
    base_type = _norm_mix(type_mix, {"F&B": 0.7, "NON F&B": 0.3})
    base_fb = _norm_mix(
        gamme_mix_fb,
        {
            "sans alcool": 0.4,
            "food salee": 0.28,
            "food sucree": 0.18,
            "alcool": 0.1,
            "formule": 0.04,
        },
    )
    base_nfb = _norm_mix(
        gamme_mix_nfb,
        {
            "accessoires": 0.35,
            "sos": 0.3,
            "cosmetique": 0.12,
            "pap": 0.1,
            "jeux enfants": 0.08,
            "souvenirs": 0.05,
        },
    )
    sols = solutions or ["simply", "liberty", "connected"]

    scenarios: list[dict[str, Any]] = [
        {
            "group": "baseline",
            "varied_key": None,
            "varied_target": None,
            "base_value": None,
            "type_mix": base_type,
            "gamme_mix_fb": base_fb,
            "gamme_mix_nfb": base_nfb,
        }
    ]

    for cfg in mix_configs_for_group(base_type, "type", step=step):
        scenarios.append(
            {
                **cfg,
                "type_mix": cfg["mix"],
                "gamme_mix_fb": base_fb,
                "gamme_mix_nfb": base_nfb,
            }
        )
    for cfg in mix_configs_for_group(base_fb, "gamme_fb", step=step):
        scenarios.append(
            {
                **cfg,
                "type_mix": base_type,
                "gamme_mix_fb": cfg["mix"],
                "gamme_mix_nfb": base_nfb,
            }
        )
    for cfg in mix_configs_for_group(base_nfb, "gamme_nfb", step=step):
        scenarios.append(
            {
                **cfg,
                "type_mix": base_type,
                "gamme_mix_fb": base_fb,
                "gamme_mix_nfb": cfg["mix"],
            }
        )

    trials: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    errors: list[dict[str, str]] = []

    for i, sc in enumerate(scenarios):
        tm = sc["type_mix"]
        fb = sc["gamme_mix_fb"]
        nfb = sc["gamme_mix_nfb"]
        gm = combine_gamme_mix(tm, fb, nfb)
        try:
            rows = evaluate_fn(
                type_mix=tm,
                gamme_mix=gm,
                gamme_mix_fb=fb,
                gamme_mix_nfb=nfb,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "scenario": f"{sc.get('group')}:{sc.get('varied_key')}={sc.get('varied_target')}",
                    "error": str(exc),
                }
            )
            continue

        for r in rows:
            ca_m = float(r.get("ca_monthly") or 0)
            # optimisation sur CA annuel (moteurs mensuels × 12)
            ca_a = float(r.get("ca_annual") if r.get("ca_annual") is not None else ca_m * 12.0)
            trial = {
                "scenario_index": i,
                "group": sc.get("group"),
                "varied_key": sc.get("varied_key"),
                "varied_target": sc.get("varied_target"),
                "base_value": sc.get("base_value"),
                "type_mix": tm,
                "gamme_mix_fb": fb,
                "gamme_mix_nfb": nfb,
                "gamme_mix": gm,
                "engine": r.get("engine"),
                "solution": r.get("solution"),
                "ca_monthly": ca_m,
                "ca_annual": ca_a,
                "marge_monthly": r.get("marge_monthly"),
                "marge_annual": r.get("marge_annual"),
                "marge_nette_monthly": r.get("marge_nette_monthly"),
                "marge_nette_annual": r.get("marge_nette_annual")
                or r.get("marge_nette_annuelle"),
                "result": r,
            }
            trials.append(trial)
            if best is None or ca_a > float(best.get("ca_annual") or -1e18):
                best = trial

        if (i + 1) % 25 == 0:
            logger.info("optimize mix: %s/%s scenarios", i + 1, len(scenarios))

    # Recommandation metier sur le meilleur mix (tous moteurs / solutions de ce mix)
    best_recommendation = None
    best_by_engine: dict[str, Any] = {}
    if best is not None:
        same_mix = [
            t["result"]
            for t in trials
            if t["scenario_index"] == best["scenario_index"]
        ]
        best_recommendation = recommend(
            same_mix, nb_chambres=hotel_nb_chambres
        )
        for eng in ("sim_v1", "sim_v2", "ml"):
            eng_rows = [r for r in same_mix if r.get("engine") == eng]
            best_by_engine[eng] = {
                "results": eng_rows,
                "recommendation": recommend(eng_rows, nb_chambres=hotel_nb_chambres)
                if eng_rows
                else {
                    "recommended": None,
                    "reason": "Pas de prediction pour ce moteur.",
                    "warnings": [],
                },
            }

    # Top 15 par CA pour affichage tableau
    top = sorted(
        trials, key=lambda t: float(t.get("ca_annual") or 0), reverse=True
    )[:15]
    top_light = [
        {
            "group": t["group"],
            "varied_key": t["varied_key"],
            "varied_target": t["varied_target"],
            "engine": t["engine"],
            "solution": t["solution"],
            "ca_monthly": t["ca_monthly"],
            "ca_annual": t["ca_annual"],
            "marge_nette_monthly": t["marge_nette_monthly"],
            "marge_nette_annual": t["marge_nette_annual"],
        }
        for t in top
    ]

    return {
        "ok": True,
        "hotel_code": hotel_code,
        "n_scenarios": len(scenarios),
        "n_trials": len(trials),
        "step": step,
        "baseline": {
            "type_mix": base_type,
            "gamme_mix_fb": base_fb,
            "gamme_mix_nfb": base_nfb,
            "gamme_mix": combine_gamme_mix(base_type, base_fb, base_nfb),
        },
        "best": best,
        "best_by_engine": best_by_engine,
        "best_recommendation": best_recommendation,
        "top": top_light,
        "errors": errors,
        "solutions": sols,
    }
