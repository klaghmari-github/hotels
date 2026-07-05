"""Coûts ROD — technos, annexes, agencement ligne à ligne (feuilles SIMULATEUR *)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from rod_ia.domain.models.simulation import RodSimulationRequest
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.rules.traceability import RuleTrace


@dataclass
class CostComputation:
    annual_cost: float
    monthly_cost: float
    capex: float
    opex_monthly: float
    techno_monthly: float
    annexes_monthly: float
    agencement_monthly: float
    trace: List[RuleTrace]
    warnings: List[str]
    cost_lines: List[dict] = field(default_factory=list)


class RodCostRules:
    """Capex + opex mensuels — somme des lignes extraites du SIMULATEUR (E/H colonnes)."""

    def __init__(self, reference: ReferenceRepository) -> None:
        self._reference = reference

    @staticmethod
    def _line_monthly(line: dict, qty_override: float | None = None) -> tuple[float, float]:
        qty = float(qty_override if qty_override is not None else line.get("qty_default", 1))
        monthly_unit = float(line.get("monthly_unit", 0.0) or 0.0)
        capex_unit = float(line.get("capex_unit", 0.0) or 0.0)
        amort = float(line.get("amort_months", 0.0) or 0.0)

        if monthly_unit > 0:
            monthly = monthly_unit * qty
            capex = capex_unit * qty
        elif capex_unit > 0 and amort > 0:
            capex = capex_unit * qty
            monthly = capex / amort
        else:
            monthly = 0.0
            capex = 0.0
        return monthly, capex

    def _sum_lines(
        self,
        lines: list[dict],
        qty_map: dict[str, float] | None = None,
    ) -> tuple[float, float, list[dict]]:
        qty_map = qty_map or {}
        total_monthly = 0.0
        total_capex = 0.0
        detail: list[dict] = []
        for line in lines:
            line_id = str(line.get("id", ""))
            monthly, capex = self._line_monthly(line, qty_map.get(line_id))
            qty = float(qty_map.get(line_id, line.get("qty_default", 1)))
            total_monthly += monthly
            total_capex += capex
            detail.append(
                {
                    "id": line_id,
                    "label": line.get("label", line_id),
                    "group": line.get("group", ""),
                    "qty": qty,
                    "monthly": monthly,
                    "capex": capex,
                }
            )
        return total_monthly, total_capex, detail

    def compute(self, request: RodSimulationRequest, concept: str) -> CostComputation:
        store = request.store
        if store is None:
            raise ValueError("store requis pour le calcul coûts")
        warnings: list[str] = []
        key = f"concepts.{concept}"

        cost_lines_ref = self._reference.get(f"{key}.cost_lines") or {}
        techno_lines = list(cost_lines_ref.get("techno") or [])
        annexes_lines = list(cost_lines_ref.get("annexes") or [])
        agencement_cfg = dict(cost_lines_ref.get("agencement") or {})

        techno_monthly, techno_capex, techno_detail = self._sum_lines(techno_lines)
        annexes_monthly, annexes_capex, annexes_detail = self._sum_lines(annexes_lines)

        agencement_per_m = float(
            agencement_cfg.get("capex_per_m")
            or self._reference.get(f"{key}.agencement_per_m", 1000.0)
            or 1000.0
        )
        amort_months = float(
            agencement_cfg.get("amort_months")
            or self._reference.get(f"{key}.amort_months", 84.0)
            or 84.0
        )
        agencement_capex = agencement_per_m * store.m_lin
        agencement_monthly = (
            agencement_capex / amort_months if amort_months else 0.0
        )

        fixed_capex = float(self._reference.get(f"{key}.fixed_capex", 0.0) or 0.0)
        capex = fixed_capex + techno_capex + annexes_capex + agencement_capex
        monthly_cost = techno_monthly + annexes_monthly + agencement_monthly

        if not techno_lines and not annexes_lines:
            techno_monthly = float(self._reference.get(f"{key}.techno_monthly", 0.0) or 0.0)
            annexes_monthly = float(self._reference.get(f"{key}.annexes_monthly", 0.0) or 0.0)
            monthly_cost = techno_monthly + annexes_monthly + agencement_monthly
            warnings.append(
                f"Coûts agrégés utilisés pour {concept} — cost_lines absent de la référence."
            )

        if monthly_cost == 0:
            warnings.append(f"Coûts mensuels nuls pour {concept} — vérifier références Excel.")

        all_lines = techno_detail + annexes_detail + [
            {
                "id": "agencement",
                "label": agencement_cfg.get("label", "Agencement"),
                "group": "agencement",
                "qty": store.m_lin,
                "monthly": agencement_monthly,
                "capex": agencement_capex,
            }
        ]

        trace = [
            RuleTrace(
                rule_id="COST_LINE_BY_LINE",
                workbook="ROD - Simulateurs + détail des coûts.xlsx",
                sheet=f"SIMULATEUR {concept}",
                cells=["E147:E166", "H147:H166", "E168/H168"],
                excel_formula="Σ lignes techno + annexes + agencement amorti",
                business_description="Coûts mensuels détaillés par ligne équipement.",
                python_method="RodCostRules.compute",
                status="implemented_from_documentation",
            )
        ]
        return CostComputation(
            annual_cost=monthly_cost * 12,
            monthly_cost=monthly_cost,
            capex=capex,
            opex_monthly=techno_monthly + annexes_monthly,
            techno_monthly=techno_monthly,
            annexes_monthly=annexes_monthly,
            agencement_monthly=agencement_monthly,
            trace=trace,
            warnings=warnings,
            cost_lines=all_lines,
        )