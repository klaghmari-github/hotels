"""
Optimisation de mix (type F&B / gammes).

Deux modes :
- product_rank (defaut) : top N produits par rang de marge (m_lin × densite)
  → mix F&B / gammes deduit, puis evaluation sim_v1 / sim_v2 / ml
- grid : balayage 10 % historique (fallback)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from src.user.business import enrich_prediction_with_costs, recommend

logger = logging.getLogger(__name__)

STEP = 0.1

# GAMME ventes (SANS_ALCOOL) → cle UI ("sans alcool")
_GAMME_TO_UI = {
    "SANS_ALCOOL": "sans alcool",
    "FOOD_SALEE": "food salee",
    "FOOD_SUCREE": "food sucree",
    "ALCOOL": "alcool",
    "FORMULE": "formule",
    "ACCESSOIRES": "accessoires",
    "SOS": "sos",
    "COSMETIQUE": "cosmetique",
    "PAP": "pap",
    "JEUX_ENFANTS": "jeux enfants",
    "SOUVENIRS": "souvenirs",
}


def _gamme_ui(key: str) -> str:
    k = str(key or "").strip().upper().replace(" ", "_")
    if k in _GAMME_TO_UI:
        return _GAMME_TO_UI[k]
    return str(key or "").lower().replace("_", " ").strip()


def _map_mix_keys_ui(mix: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in (mix or {}).items():
        uk = _gamme_ui(k)
        try:
            out[uk] = out.get(uk, 0.0) + float(v)
        except (TypeError, ValueError):
            continue
    s = sum(out.values())
    if s > 1e-12:
        out = {k: round(v / s, 6) for k, v in out.items()}
    return out


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
    Place `key` a new_val (clamp 0..1).

    L'ecart (ajout ou retrait) est repercute sur les autres cles
    **proportionnellement** a leur part actuelle relative.

    Exemple : A=0.50, B=0.30, C=0.20 ; A → 0.60
    → on retire 0.10 de B+C au prorata 0.30:0.20 → B=0.24, C=0.16.
    """
    keys = list(base.keys())
    if key not in base:
        raise KeyError(key)
    others = [k for k in keys if k != key]
    new_val = max(0.0, min(1.0, float(new_val)))

    if not others:
        return {key: 1.0}

    rem = max(0.0, 1.0 - new_val)
    others_sum = sum(max(0.0, float(base[o])) for o in others)
    out: dict[str, float] = {key: new_val}

    if others_sum <= 1e-12:
        each = rem / len(others)
        for o in others:
            out[o] = each
    else:
        for o in others:
            w = max(0.0, float(base[o])) / others_sum
            out[o] = rem * w

    s = sum(out.values())
    if s <= 1e-12:
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


def normalize_mix_exact(
    mix: dict[str, Any] | None,
    defaults: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Renormalise un mix pour que la somme soit exactement 1.0.
    Residu place sur la plus grande part (evite les rejets sim_v2
    sur les arrondis float).
    """
    out: dict[str, float] = {}
    for k, v in (mix or {}).items():
        key = str(k).strip()
        if not key:
            continue
        try:
            val = max(0.0, float(v))
        except (TypeError, ValueError):
            val = 0.0
        out[key] = out.get(key, 0.0) + val
    s = sum(out.values())
    if s <= 1e-12:
        out = {}
        for k, v in (defaults or {}).items():
            key = str(k).strip()
            if not key:
                continue
            try:
                val = max(0.0, float(v))
            except (TypeError, ValueError):
                val = 0.0
            out[key] = out.get(key, 0.0) + val
        s = sum(out.values())
        if s <= 1e-12:
            if not out:
                out = dict(defaults or {"F&B": 0.7, "NON F&B": 0.3})
            n = max(len(out), 1)
            out = {k: 1.0 / n for k in out}
            s = 1.0
    out = {k: v / s for k, v in out.items()}
    # residu float sur la plus grande cle → somme exacte 1.0
    if out:
        max_k = max(out, key=lambda k: out[k])
        residual = 1.0 - sum(out.values())
        out[max_k] = max(0.0, out[max_k] + residual)
    return out


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
    tm = normalize_mix_exact(type_mix, {"F&B": 0.7, "NON F&B": 0.3})
    w_fb = 0.0
    w_nfb = 0.0
    for k, v in tm.items():
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

    default_fb = {
        "sans alcool": 0.40,
        "food salee": 0.28,
        "food sucree": 0.18,
        "alcool": 0.10,
        "formule": 0.04,
    }
    default_nfb = {
        "accessoires": 0.35,
        "sos": 0.30,
        "cosmetique": 0.12,
        "pap": 0.10,
        "jeux enfants": 0.08,
        "souvenirs": 0.05,
    }
    fb = normalize_mix_exact(gamme_fb, default_fb) if w_fb > 1e-12 else {}
    nfb = normalize_mix_exact(gamme_nfb, default_nfb) if w_nfb > 1e-12 else {}

    out: dict[str, float] = {}
    for k, v in fb.items():
        out[str(k)] = out.get(str(k), 0.0) + w_fb * float(v)
    for k, v in nfb.items():
        out[str(k)] = out.get(str(k), 0.0) + w_nfb * float(v)
    return normalize_mix_exact(out, {**default_fb, **default_nfb})


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
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """
    evaluate_fn(type_mix=..., gamme_mix=..., gamme_mix_fb=..., gamme_mix_nfb=...)
    → liste de resultats enrichis (engine, solution, ca_monthly, ...).

    progress_cb(done, total, message) optionnel.
    """
    def _progress(done: int, total: int, message: str) -> None:
        if progress_cb is not None:
            try:
                progress_cb(done, total, message)
            except Exception:  # noqa: BLE001
                pass

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
    from src.user.business import SOLUTION_DISPLAY_ORDER

    # ordre d evaluation / affichage : connected → liberty → simply
    sols = list(solutions) if solutions else list(SOLUTION_DISPLAY_ORDER)

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
    n_sc = max(len(scenarios), 1)
    _progress(0, n_sc, "Estimation du CA…")

    for i, sc in enumerate(scenarios):
        _progress(
            i,
            n_sc,
            f"Estimation du CA ({i + 1}/{n_sc})…",
        )
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

    _progress(n_sc, n_sc, "Finalisation…")

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
        from src.user.business import sort_rows_by_solution

        for eng in ("sim_v1", "sim_v2", "ml"):
            eng_rows = sort_rows_by_solution(
                [r for r in same_mix if r.get("engine") == eng]
            )
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
        "method": "grid",
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
        "apply_mix": {
            "type_mix": best["type_mix"] if best else base_type,
            "gamme_mix_fb": best["gamme_mix_fb"] if best else base_fb,
            "gamme_mix_nfb": best["gamme_mix_nfb"] if best else base_nfb,
            "gamme_mix": best["gamme_mix"]
            if best
            else combine_gamme_mix(base_type, base_fb, base_nfb),
        }
        if best
        else None,
    }


def _active_keys(mix: dict[str, Any] | None, thr: float = 0.02) -> list[str]:
    out: list[str] = []
    for k, v in (mix or {}).items():
        try:
            if float(v) > thr:
                out.append(str(k))
        except (TypeError, ValueError):
            continue
    return out


def run_product_rank_optimization(
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
    recommend_fn: Callable[..., dict[str, Any]],
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """
    Optimisation par assortiment : densite produits/m_lin × rangs marge.

    recommend_fn(solution, metres_lineaires, allowed_types, allowed_gammes)
    → payload optimal_mix.

    progress_cb(done, total, message) optionnel pour barre de progression.
    """
    def _progress(done: int, total: int, message: str) -> None:
        if progress_cb is not None:
            try:
                progress_cb(done, total, message)
            except Exception:  # noqa: BLE001
                pass

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
    sols = [str(s).strip().upper() for s in (solutions or ["SIMPLY", "LIBERTY", "CONNECTED"])]

    # Filtres : types / gammes actives dans l'UI (parts > seuil)
    allowed_types = _active_keys(base_type, thr=0.02)
    allowed_gammes_ui = _active_keys(base_fb, thr=0.02) + _active_keys(base_nfb, thr=0.02)
    # vers codes ventes pour le filtre SQL (SANS_ALCOOL …)
    ui_to_raw = {v: k for k, v in _GAMME_TO_UI.items()}
    allowed_gammes_raw = [
        ui_to_raw.get(_gamme_ui(g), str(g).upper().replace(" ", "_"))
        for g in allowed_gammes_ui
    ]

    # total etapes : 1 prep + 1 reco par solution + 1 evaluation par scenario
    total_steps = 1 + len(sols) + max(len(sols), 1)
    step_i = 0
    _progress(step_i, total_steps, "Preparation…")

    scenarios: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    assortments: dict[str, Any] = {}

    for sol in sols:
        step_i += 1
        _progress(
            step_i,
            total_steps,
            f"Calcul du mix recommande ({step_i}/{total_steps})…",
        )
        try:
            reco = recommend_fn(
                solution=sol,
                metres_lineaires=metres_lineaires,
                allowed_types=allowed_types or None,
                allowed_gammes=allowed_gammes_raw or None,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"scenario": f"assortment:{sol}", "error": str(exc)})
            continue

        tm = reco.get("type_mix") or base_type
        fb = _map_mix_keys_ui(reco.get("gamme_mix_fb") or {})
        nfb = _map_mix_keys_ui(reco.get("gamme_mix_nfb") or {})
        if not fb:
            fb = base_fb
        if not nfb:
            nfb = base_nfb
        # renormalise familles
        fb = _norm_mix(fb, base_fb)
        nfb = _norm_mix(nfb, base_nfb)
        tm = _norm_mix(tm, base_type)

        assortments[sol] = reco
        scenarios.append(
            {
                "group": "product_rank",
                "varied_key": "assortment",
                "varied_target": sol,
                "base_value": reco.get("n_products_selected"),
                "type_mix": tm,
                "gamme_mix_fb": fb,
                "gamme_mix_nfb": nfb,
                "assortment": reco,
                "solution_focus": sol,
            }
        )

    if not scenarios:
        raise ValueError(
            "Impossible de construire un assortiment optimal. "
            + (errors[0]["error"] if errors else "")
        )

    # recalibre total si certains assortiments ont echoue
    total_steps = 1 + len(sols) + len(scenarios)
    _progress(step_i, total_steps, "Estimation du CA…")

    trials: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None

    for i, sc in enumerate(scenarios):
        step_i += 1
        _progress(
            step_i,
            total_steps,
            f"Estimation du CA ({step_i}/{total_steps})…",
        )
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
                    "scenario": f"product_rank:{sc.get('solution_focus')}",
                    "error": str(exc),
                }
            )
            continue

        for r in rows:
            ca_m = float(r.get("ca_monthly") or 0)
            ca_a = float(
                r.get("ca_annual") if r.get("ca_annual") is not None else ca_m * 12.0
            )
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
                "assortment": sc.get("assortment"),
            }
            trials.append(trial)
            # Prefer trial matching assortment solution when equal CA
            if best is None or ca_a > float(best.get("ca_annual") or -1e18):
                best = trial
            elif abs(ca_a - float(best.get("ca_annual") or 0)) < 1e-6:
                focus_sol = str(sc.get("solution_focus") or "").upper()
                if str(r.get("solution") or "").upper() == focus_sol:
                    best = trial

    _progress(total_steps, total_steps, "Finalisation…")

    best_recommendation = None
    best_by_engine: dict[str, Any] = {}
    if best is not None:
        same_mix = [
            t["result"] for t in trials if t["scenario_index"] == best["scenario_index"]
        ]
        from src.user.business import sort_rows_by_solution

        best_recommendation = recommend(same_mix, nb_chambres=hotel_nb_chambres)
        for eng in ("sim_v1", "sim_v2", "ml"):
            eng_rows = sort_rows_by_solution(
                [r for r in same_mix if r.get("engine") == eng]
            )
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

    top = sorted(trials, key=lambda t: float(t.get("ca_annual") or 0), reverse=True)[
        :15
    ]
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

    apply_mix = None
    if best is not None:
        apply_mix = {
            "type_mix": best["type_mix"],
            "gamme_mix_fb": best["gamme_mix_fb"],
            "gamme_mix_nfb": best["gamme_mix_nfb"],
            "gamme_mix": best["gamme_mix"],
        }

    return {
        "ok": True,
        "method": "product_rank",
        "hotel_code": hotel_code,
        "n_scenarios": len(scenarios),
        "n_trials": len(trials),
        "step": None,
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
        "assortments": assortments,
        "apply_mix": apply_mix,
        "metres_lineaires": metres_lineaires,
    }
