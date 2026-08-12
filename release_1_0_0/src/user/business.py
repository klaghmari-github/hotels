"""
Regles metier communes (couts, amortissement, recommandation).

Appliquees de la meme facon aux sorties sim_v1 / sim_v2 / ml.
Source : data/files/input/rod_reference.json (concepts.*).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.pipeline.paths import Paths


@lru_cache(maxsize=1)
def load_rod_reference(root: str | None = None) -> dict[str, Any]:
    paths = Paths(root).ensure() if root else Paths().ensure()
    path = paths.input / "rod_reference.json"
    if not path.exists():
        return {"concepts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


# Affichage UI : toujours Connected → Liberty → Simply (plus « chic » d abord).
# La meilleure solution reste identifiable via la recommandation / ROI.
SOLUTION_DISPLAY_ORDER: tuple[str, ...] = (
    "connected",
    "liberty",
    "simply",
)


def solution_sort_key(solution: Any) -> tuple[int, str]:
    """Cle de tri pour listes de resultats par solution."""
    s = str(solution or "").strip().lower()
    try:
        idx = SOLUTION_DISPLAY_ORDER.index(s)
    except ValueError:
        idx = len(SOLUTION_DISPLAY_ORDER)
    return (idx, s)


def sort_rows_by_solution(
    rows: list[dict[str, Any]],
    *,
    key: str = "solution",
) -> list[dict[str, Any]]:
    """Trie une liste de dicts selon SOLUTION_DISPLAY_ORDER."""
    return sorted(
        rows,
        key=lambda r: solution_sort_key(
            r.get(key) if isinstance(r, dict) else r
        ),
    )


def _concept_key(solution: str) -> str:
    s = (solution or "simply").strip().upper()
    if s in {"SIMPLY", "LIBERTY", "CONNECTED"}:
        return s
    return s


def compute_costs(
    solution: str,
    *,
    metres_lineaires: float = 6.0,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Couts mensuels / capex / amortissement pour une solution."""
    ref = reference or load_rod_reference()
    key = _concept_key(solution)
    cfg = (ref.get("concepts") or {}).get(key) or {}

    techno_m = float(cfg.get("techno_monthly") or 0)
    annexes_m = float(cfg.get("annexes_monthly") or 0)
    agencement_per_m = float(cfg.get("agencement_per_m") or 1000)
    amort_months = float(cfg.get("amort_months") or 84)
    fixed_capex = float(cfg.get("fixed_capex") or 0)
    m_lin = max(float(metres_lineaires or 0), 0.0)

    # Detail cost_lines si present
    cost_lines_ref = cfg.get("cost_lines") or {}
    lines_out: list[dict[str, Any]] = []
    techno_from_lines = 0.0
    annexes_from_lines = 0.0
    techno_capex = 0.0
    annexes_capex = 0.0

    for group, bucket in (
        ("techno", cost_lines_ref.get("techno") or []),
        ("annexes", cost_lines_ref.get("annexes") or []),
    ):
        for line in bucket:
            qty = float(line.get("qty_default") or 1)
            monthly_unit = float(line.get("monthly_unit") or 0)
            capex_unit = float(line.get("capex_unit") or 0)
            amort = float(line.get("amort_months") or 0)
            if monthly_unit > 0:
                monthly = monthly_unit * qty
                capex = capex_unit * qty
            elif capex_unit > 0 and amort > 0:
                capex = capex_unit * qty
                monthly = capex / amort
            else:
                monthly, capex = 0.0, capex_unit * qty
            if group == "techno":
                techno_from_lines += monthly
                techno_capex += capex
            else:
                annexes_from_lines += monthly
                annexes_capex += capex
            lines_out.append(
                {
                    "id": line.get("id", ""),
                    "label": line.get("label", line.get("id", "")),
                    "group": group,
                    "qty": qty,
                    "monthly": round(monthly, 4),
                    "capex": round(capex, 4),
                }
            )

    if techno_from_lines > 0 or annexes_from_lines > 0:
        techno_m = techno_from_lines
        annexes_m = annexes_from_lines

    agencement_cfg = dict(cost_lines_ref.get("agencement") or {})
    if agencement_cfg.get("capex_per_m") is not None:
        agencement_per_m = float(agencement_cfg["capex_per_m"])
    if agencement_cfg.get("amort_months") is not None:
        amort_months = float(agencement_cfg["amort_months"])

    agencement_capex = agencement_per_m * m_lin
    agencement_m = agencement_capex / amort_months if amort_months else 0.0
    lines_out.append(
        {
            "id": "agencement",
            "label": agencement_cfg.get("label", "Agencement"),
            "group": "agencement",
            "qty": m_lin,
            "monthly": round(agencement_m, 4),
            "capex": round(agencement_capex, 4),
        }
    )

    monthly = techno_m + annexes_m + agencement_m
    capex = fixed_capex + techno_capex + annexes_capex + agencement_capex

    return {
        "solution": key,
        "monthly_cost": round(monthly, 4),
        "annual_cost": round(monthly * 12, 4),
        "capex": round(capex, 4),
        "techno_monthly": round(techno_m, 4),
        "annexes_monthly": round(annexes_m, 4),
        "agencement_monthly": round(agencement_m, 4),
        "amort_months": amort_months,
        "metres_lineaires": m_lin,
        "cost_lines": lines_out,
    }


def enrich_prediction_with_costs(
    *,
    solution: str,
    ca_monthly: float | None,
    marge_monthly: float | None,
    metres_lineaires: float = 6.0,
    engine: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Applique les couts sur une prediction / simulation.

    Les moteurs (sim_v1/v2/ml) sortent du **mensuel**
    (montant_*_par_mois). On conserve le mensuel pour l'amortissement
    et on expose l'**annuel** (= mensuel × 12) pour l'UI estimation.
    """
    costs = compute_costs(solution, metres_lineaires=metres_lineaires)
    ca_m = float(ca_monthly or 0)
    marge_m = float(marge_monthly or 0)
    cout_m = float(costs["monthly_cost"] or 0)
    marge_nette_m = marge_m - cout_m
    capex = float(costs.get("capex") or 0)
    # Amortissement (mois) = capex / ROI mensuel si ROI > 0
    if marge_nette_m > 1e-6 and capex > 0:
        payback_months = capex / marge_nette_m
    elif marge_nette_m <= 0:
        payback_months = None  # ROI <= 0 : non amortissable
    else:
        payback_months = 0.0

    ca_a = ca_m * 12.0
    marge_a = marge_m * 12.0
    marge_nette_a = marge_nette_m * 12.0
    cout_a = cout_m * 12.0

    costs_annual = {
        **costs,
        "monthly_cost": round(cout_m, 4),
        "annual_cost": round(cout_a, 4),
    }

    out = {
        "engine": engine,
        "solution": costs["solution"],
        # mensuel (source moteurs)
        "ca_monthly": round(ca_m, 4),
        "marge_monthly": round(marge_m, 4),
        # ROI = (prix vente − prix achat) − couts solution
        "marge_nette_monthly": round(marge_nette_m, 4),
        "roi_monthly": round(marge_nette_m, 4),
        "cout_monthly": round(cout_m, 4),
        # annuel (affichage estimation = × 12)
        "ca_annual": round(ca_a, 4),
        "marge_annual": round(marge_a, 4),
        "marge_nette_annual": round(marge_nette_a, 4),
        "marge_nette_annuelle": round(marge_nette_a, 4),  # alias FR
        "roi_annual": round(marge_nette_a, 4),
        "cout_annual": round(cout_a, 4),
        "period": "annual",
        "period_label": "€ / an",
        "conversion": "monthly_x12",
        "payback_months": (
            round(payback_months, 1) if payback_months is not None else None
        ),
        "payback_years": (
            round(payback_months / 12.0, 2) if payback_months is not None else None
        ),
        "costs": costs_annual,
    }
    if extra:
        out["detail"] = extra
    return out


def recommend(
    rows: list[dict[str, Any]],
    *,
    nb_chambres: float | None = None,
) -> dict[str, Any]:
    """
    Recommandation : meilleur ROI annuel
    (marge ventes PV−PA − couts solution) parmi les candidats.

    Filtre leger taille : < 50 chambres → prefere SIMPLY si present.
    """
    if not rows:
        return {
            "recommended": None,
            "reason": "Aucune simulation disponible.",
            "warnings": [],
        }

    warnings: list[str] = []
    candidates = list(rows)
    n = float(nb_chambres or 0)
    if n and n < 50:
        simply = [r for r in candidates if str(r.get("solution", "")).upper() == "SIMPLY"]
        if simply:
            warnings.append("Hotel < 50 chambres — SIMPLY privilegie (regle taille).")
            candidates = simply

    def _roi(r: dict[str, Any]) -> float:
        for k in ("roi_annual", "marge_nette_annual", "marge_nette_annuelle"):
            if r.get(k) is not None:
                try:
                    return float(r[k])
                except (TypeError, ValueError):
                    pass
        return -1e18

    best = max(candidates, key=_roi)
    sol = best.get("solution")
    engine = best.get("engine")
    reason = (
        f"{sol} ({engine}) offre le meilleur ROI annuel "
        f"({_roi(best):,.0f} €)."
    )
    return {
        "recommended": sol,
        "recommended_engine": engine,
        "reason": reason,
        "warnings": warnings,
        "best": best,
    }
