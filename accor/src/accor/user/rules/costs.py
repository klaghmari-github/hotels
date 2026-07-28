"""
Règles de coûts ROD — indépendantes des revenus.

Sources
-------
  data/rod_reference.json → concepts.{C}.cost_lines
    (techno, annexes, agencement : qty, monthly_unit, capex, amort…)
  fallbacks agrégés : techno_monthly, annexes_monthly, agencement_per_m

Chaque ligne : opex mensuel = monthly_unit × qty, ou capex/amort si pas
de monthly_unit. Attention aux quantités déjà incluses dans un forfait
(ex. CONNECTED) pour ne pas double-compter.

Module volontairement stable si le moteur de revenus change.
"""

from __future__ import annotations

from accor.user.models import CostResult, SimulationRequest
from accor.user.reference import RodReference


class CostRules:
    """Capex + opex mensuels ligne à ligne (SIMULATEUR * Excel)."""

    def __init__(self, reference: RodReference) -> None:
        self._ref = reference

    @staticmethod
    def _qty(line: dict, qty_override: float | None = None) -> float:
        """Lit qty_default en respectant 0 (ne pas traiter 0 comme falsy → 1)."""
        if qty_override is not None:
            return float(qty_override)
        raw = line.get("qty_default", 1)
        if raw is None or raw == "":
            return 1.0
        return float(raw)

    @staticmethod
    def _line_monthly(line: dict, qty_override: float | None = None) -> tuple[float, float]:
        qty = CostRules._qty(line, qty_override)
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
            qty = self._qty(line)
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

    @staticmethod
    def _hotel_has_vitrine(request: SimulationRequest) -> bool:
        """True si l'hôtel a déjà une vitrine / frigo lobby (pas de coût vitrine à ajouter)."""
        services = getattr(request, "services", None)
        if services is None:
            return False
        if isinstance(services, dict):
            return bool(
                services.get("lobby_fridge")
                or services.get("has_vitrine")
                or services.get("vitrine_refrigeree")
                or services.get("corner_fb_frigo")
            )
        return bool(
            getattr(services, "lobby_fridge", False)
            or getattr(services, "corner_fb_frigo", False)
        )

    def _apply_vitrine_rule(
        self, techno_lines: list[dict], annexes_lines: list[dict], concept: str, has_vitrine: bool
    ) -> tuple[list[dict], list[dict], list[str]]:
        """
        SIMPLY / LIBERTY :
          * vitrine déjà présente → qty vitrine (techno + élec) = 0
          * sinon → qty = 1 (coût vitrine à ajouter)
        CONNECTED : pas de ligne vitrine (frigos dédiés) — inchangé.
        """
        notes: list[str] = []
        if concept not in ("SIMPLY", "LIBERTY"):
            return techno_lines, annexes_lines, notes

        # Barème Excel (couts_technos) : 800 € / 60 mois = 13,333 €/mois
        VITRINE_CAPEX = 800.0
        VITRINE_MONTHLY = 800.0 / 60.0
        ELEC_VITRINE_CAPEX = 600.0
        ELEC_VITRINE_MONTHLY = 10.0

        qty = 0.0 if has_vitrine else 1.0
        notes.append(
            "Vitrine déjà présente — coût vitrine non ajouté."
            if has_vitrine
            else "Pas de vitrine — coût vitrine ajouté (SIMPLY/LIBERTY)."
        )

        techno_out: list[dict] = []
        found_vitrine = False
        for line in techno_lines:
            ln = dict(line)
            lid = str(ln.get("id") or "").lower()
            lab = str(ln.get("label") or "").lower()
            if lid == "vitrine" or "vitrine" in lab:
                found_vitrine = True
                ln["qty_default"] = qty
                # SIMPLY a parfois 0/0 en rod_reference — reprend le barème Excel
                if float(ln.get("capex_unit") or 0) <= 0 and qty > 0:
                    ln["capex_unit"] = VITRINE_CAPEX
                if float(ln.get("monthly_unit") or 0) <= 0 and qty > 0:
                    ln["monthly_unit"] = VITRINE_MONTHLY
                if float(ln.get("amort_months") or 0) <= 0:
                    ln["amort_months"] = 60.0
            techno_out.append(ln)
        if not found_vitrine and qty > 0:
            techno_out.append(
                {
                    "id": "vitrine",
                    "label": "Vitrine",
                    "group": "techno",
                    "qty_default": qty,
                    "capex_unit": VITRINE_CAPEX,
                    "monthly_unit": VITRINE_MONTHLY,
                    "amort_months": 60.0,
                }
            )

        annexes_out: list[dict] = []
        found_elec = False
        for line in annexes_lines:
            ln = dict(line)
            lid = str(ln.get("id") or "").lower()
            lab = str(ln.get("label") or "").lower()
            if lid in ("elec_vitrine", "vitrine") or "elec" in lab and "vitr" in lab:
                found_elec = True
                ln["qty_default"] = qty
                if float(ln.get("capex_unit") or 0) <= 0 and qty > 0:
                    ln["capex_unit"] = ELEC_VITRINE_CAPEX
                if float(ln.get("monthly_unit") or 0) <= 0 and qty > 0:
                    ln["monthly_unit"] = ELEC_VITRINE_MONTHLY
            annexes_out.append(ln)
        if not found_elec and qty > 0:
            annexes_out.append(
                {
                    "id": "elec_vitrine",
                    "label": "Elec. vitrine",
                    "group": "annexes",
                    "qty_default": qty,
                    "capex_unit": ELEC_VITRINE_CAPEX,
                    "monthly_unit": ELEC_VITRINE_MONTHLY,
                    "amort_months": 60.0,
                }
            )
        return techno_out, annexes_out, notes

    def compute(self, request: SimulationRequest, concept: str) -> CostResult:
        concept = concept.upper()
        if request.store is None:
            raise ValueError("store requis pour le calcul des coûts")

        key = f"concepts.{concept}"
        cost_lines_ref = self._ref.get(f"{key}.cost_lines") or {}
        techno_lines = list(cost_lines_ref.get("techno") or [])
        annexes_lines = list(cost_lines_ref.get("annexes") or [])
        agencement_cfg = dict(cost_lines_ref.get("agencement") or {})

        has_vitrine = self._hotel_has_vitrine(request)
        techno_lines, annexes_lines, vitrine_notes = self._apply_vitrine_rule(
            techno_lines, annexes_lines, concept, has_vitrine
        )

        techno_m, techno_c, techno_d = self._sum_lines(techno_lines)
        annexes_m, annexes_c, annexes_d = self._sum_lines(annexes_lines)

        warnings: list[str] = list(vitrine_notes)
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
