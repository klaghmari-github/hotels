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
    """Applique les couts sur une prediction CA / marge marche."""
    costs = compute_costs(solution, metres_lineaires=metres_lineaires)
    ca = float(ca_monthly or 0)
    marge = float(marge_monthly or 0)
    marge_nette_m = marge - costs["monthly_cost"]
    out = {
        "engine": engine,
        "solution": costs["solution"],
        "ca_monthly": round(ca, 4),
        "marge_monthly": round(marge, 4),
        "marge_nette_monthly": round(marge_nette_m, 4),
        "marge_nette_annuelle": round(marge_nette_m * 12, 4),
        "costs": costs,
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
    Recommandation : meilleure marge nette annuelle parmi les candidats.

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

    best = max(candidates, key=lambda r: float(r.get("marge_nette_annuelle") or -1e18))
    sol = best.get("solution")
    engine = best.get("engine")
    reason = (
        f"{sol} ({engine}) offre la meilleure marge nette annuelle "
        f"({float(best.get('marge_nette_annuelle') or 0):,.0f} €)."
    )
    return {
        "recommended": sol,
        "recommended_engine": engine,
        "reason": reason,
        "warnings": warnings,
        "best": best,
    }
