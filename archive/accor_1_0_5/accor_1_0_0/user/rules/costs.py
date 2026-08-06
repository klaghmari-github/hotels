"""
Règles de **coûts** ROD — indépendantes des revenus.

Sources
-------
* ``rod_reference.json`` → ``concepts.{C}.cost_lines`` (techno, annexes, agencement)
* fallback agrégés : techno_monthly, annexes_monthly, agencement_per_m

Ce module reste stable lorsque le moteur de revenus est remplacé par l'IA.
"""

from __future__ import annotations

from archive.accor_1_0_5.accor_1_0_0.user.models import CostResult, SimulationRequest
from archive.accor_1_0_5.accor_1_0_0.user.reference import RodReference


class CostRules:
    """Capex + opex mensuels ligne à ligne (SIMULATEUR * Excel)."""

    def __init__(self, reference: RodReference) -> None:
        self._ref = reference

    @staticmethod
    def _line_monthly(line: dict, qty_override: float | None = None) -> tuple[float, float]:
        qty = float(qty_override if qty_override is not None else line.get("qty_default", 1))
        monthly_unit = float(line.get("monthly_unit", 0.0) or 0.0)
        capex_unit = float(line.get("capex_unit", 0.0) or 0.0)
        amort = float(line.get("amort_months", 0.0) or 0.0)

        if monthly_unit > 0:
            return monthly_unit * qty, capex_unit * qty
        if capex_unit > 0 and amort > 0:
            capex = capex_unit * qty
            return capex / amort, capex
        return 0.0, 0.0

    def _sum_lines(self, lines: list[dict]) -> tuple[float, float, list[dict]]:
        total_m, total_c = 0.0, 0.0
        detail: list[dict] = []
        for line in lines:
            monthly, capex = self._line_monthly(line)
            qty = float(line.get("qty_default", 1) or 1)
            total_m += monthly
            total_c += capex
            detail.append(
                {
                    "id": line.get("id", ""),
                    "label": line.get("label", line.get("id", "")),
                    "group": line.get("group", ""),
                    "qty": qty,
                    "monthly": round(monthly, 4),
                    "capex": round(capex, 4),
                }
            )
        return total_m, total_c, detail

    def compute(self, request: SimulationRequest, concept: str) -> CostResult:
        concept = concept.upper()
        if request.store is None:
            raise ValueError("store requis pour le calcul des coûts")

        key = f"concepts.{concept}"
        cost_lines_ref = self._ref.get(f"{key}.cost_lines") or {}
        techno_lines = list(cost_lines_ref.get("techno") or [])
        annexes_lines = list(cost_lines_ref.get("annexes") or [])
        agencement_cfg = dict(cost_lines_ref.get("agencement") or {})

        techno_m, techno_c, techno_d = self._sum_lines(techno_lines)
        annexes_m, annexes_c, annexes_d = self._sum_lines(annexes_lines)

        warnings: list[str] = []
        if not techno_lines and not annexes_lines:
            techno_m = float(self._ref.get(f"{key}.techno_monthly", 0) or 0)
            annexes_m = float(self._ref.get(f"{key}.annexes_monthly", 0) or 0)
            warnings.append(
                f"cost_lines absents pour {concept} — agrégats techno/annexes utilisés."
            )

        agencement_per_m = float(
            agencement_cfg.get("capex_per_m")
            or self._ref.get(f"{key}.agencement_per_m", 1000)
            or 1000
        )
        amort_months = float(
            agencement_cfg.get("amort_months")
            or self._ref.get(f"{key}.amort_months", 84)
            or 84
        )
        m_lin = float(request.store.m_lin)
        agencement_capex = agencement_per_m * m_lin
        agencement_m = agencement_capex / amort_months if amort_months else 0.0

        fixed_capex = float(self._ref.get(f"{key}.fixed_capex", 0) or 0)
        capex = fixed_capex + techno_c + annexes_c + agencement_capex
        monthly = techno_m + annexes_m + agencement_m

        if monthly <= 0:
            warnings.append(f"Coût mensuel nul pour {concept}.")

        all_lines = techno_d + annexes_d + [
            {
                "id": "agencement",
                "label": agencement_cfg.get("label", "Agencement"),
                "group": "agencement",
                "qty": m_lin,
                "monthly": round(agencement_m, 4),
                "capex": round(agencement_capex, 4),
            }
        ]

        return CostResult(
            concept=concept,
            monthly_cost=monthly,
            annual_cost=monthly * 12,
            capex=capex,
            techno_monthly=techno_m,
            annexes_monthly=annexes_m,
            agencement_monthly=agencement_m,
            cost_lines=all_lines,
            warnings=warnings,
        )
