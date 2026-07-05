"""Coûts détaillés corner — lease (location) vs buy (achat amorti)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List

from rod_ia.domain.repositories.reference_repository import ReferenceRepository

LEASE_TERM_MONTHS = 36
LEASE_AGENCEMENT_AMORT_MONTHS = 48
BUY_AMORT_MONTHS = 84

# Location : €/m²/mois (écran détail Liberty — CLASSIQUE 12 €/M²)
AGENCEMENT_LEASE_EUR_M2_MONTH: Dict[str, float] = {
    "classique": 12.0,
    "premium": 14.0,
    "sur_mesure": 26.0,
}

# Achat : capex €/m² amorti sur BUY_AMORT_MONTHS
AGENCEMENT_BUY_EUR_M2: Dict[str, float] = {
    "classique": 126.0,
    "premium": 146.0,
    "sur_mesure": 266.0,
}

# Équipements : loyer mensuel unitaire (buy capex = lease × BUY_AMORT_MONTHS)
CONCEPT_EQUIPMENT: Dict[str, Dict[str, dict]] = {
    "SIMPLY": {
        "scanner": {"label": "Scanner", "lease_monthly": 8.0},
        "vitrine": {"label": "Vitrine réfrigérée", "lease_monthly": 13.0},
    },
    "LIBERTY": {
        "caisse": {"label": "Caisse code-barres", "lease_monthly": 250.0},
        "vitrine": {"label": "Vitrine réfrigérée", "lease_monthly": 13.0},
    },
    "CONNECTED": {
        "armoire_froid": {"label": "Armoire connectée (froid)", "lease_monthly": 45.0},
        "armoire_ambiant": {"label": "Armoire connectée (ambiant)", "lease_monthly": 35.0},
    },
}


@dataclass
class ConceptFinancing:
    """Options lease/buy du panneau détail solution."""

    mode: str = "lease"
    agencement_type: str = "classique"
    equipment_qty: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> ConceptFinancing:
        data = data or {}
        return cls(
            mode=str(data.get("mode", "lease")).lower(),
            agencement_type=str(data.get("agencement_type", "classique")).lower(),
            equipment_qty={
                str(k): int(v) for k, v in (data.get("equipment_qty") or {}).items()
            },
        )

    @property
    def is_lease(self) -> bool:
        return self.mode != "buy"


@dataclass
class FinancingCostBreakdown:
    monthly_cost: float
    marge_nette_mensuelle: float
    marge_produit_mensuelle: float
    ca_ht_mensuel: float
    ca_fb_ht_mensuel: float
    ca_nf_ht_mensuel: float
    equipment_monthly: float
    agencement_monthly: float
    annexes_monthly: float
    fixed_capex_monthly: float
    capex_total: float
    amort_months: int
    financing_mode: str
    agencement_type: str
    equipment_lines: List[dict]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class FinancingCostRules:
    """Calcule les coûts mensuels selon lease ou buy."""

    def __init__(self, reference: ReferenceRepository) -> None:
        self._reference = reference

    @staticmethod
    def default_equipment_qty(concept: str) -> Dict[str, int]:
        catalog = CONCEPT_EQUIPMENT.get(concept, {})
        return {equip_id: 1 for equip_id in catalog}

    @staticmethod
    def equipment_specs(concept: str) -> Dict[str, dict]:
        return dict(CONCEPT_EQUIPMENT.get(concept, {}))

    @staticmethod
    def amort_months(financing: ConceptFinancing) -> int:
        if financing.is_lease:
            return LEASE_AGENCEMENT_AMORT_MONTHS
        return BUY_AMORT_MONTHS

    def _equipment_monthly(
        self, concept: str, financing: ConceptFinancing
    ) -> tuple[float, list[dict], float]:
        catalog = CONCEPT_EQUIPMENT.get(concept, {})
        qty_map = financing.equipment_qty or self.default_equipment_qty(concept)
        lines: list[dict] = []
        total = 0.0
        capex = 0.0

        for equip_id, spec in catalog.items():
            qty = max(int(qty_map.get(equip_id, 0)), 0)
            lease_unit = float(spec["lease_monthly"])
            buy_unit_capex = lease_unit * BUY_AMORT_MONTHS

            if financing.is_lease:
                line_monthly = lease_unit * qty
            else:
                line_monthly = (buy_unit_capex * qty) / BUY_AMORT_MONTHS

            total += line_monthly
            capex += buy_unit_capex * qty
            lines.append(
                {
                    "id": equip_id,
                    "label": spec["label"],
                    "qty": qty,
                    "lease_monthly_unit": lease_unit,
                    "buy_capex_unit": buy_unit_capex,
                    "monthly_cost": line_monthly,
                }
            )
        return total, lines, capex

    def _agencement_monthly(
        self, m_lin: float, financing: ConceptFinancing
    ) -> tuple[float, float]:
        ag_key = financing.agencement_type
        if ag_key not in AGENCEMENT_LEASE_EUR_M2_MONTH:
            ag_key = "classique"

        if financing.is_lease:
            monthly = m_lin * AGENCEMENT_LEASE_EUR_M2_MONTH[ag_key]
            capex = 0.0
        else:
            capex = m_lin * AGENCEMENT_BUY_EUR_M2[ag_key]
            monthly = capex / BUY_AMORT_MONTHS
        return monthly, capex

    def compute(
        self,
        concept: str,
        m_lin: float,
        financing: ConceptFinancing,
        *,
        marge_produit_mensuelle: float,
        ca_ht_mensuel: float,
        ca_fb_ht_mensuel: float,
        ca_nf_ht_mensuel: float,
    ) -> FinancingCostBreakdown:
        warnings: list[str] = []
        key = f"concepts.{concept}"

        annexes_monthly = float(
            self._reference.get(f"{key}.annexes_monthly", 0.0) or 0.0
        )

        equipment_monthly, equipment_lines, equip_capex = self._equipment_monthly(
            concept, financing
        )
        agencement_monthly, agencement_capex = self._agencement_monthly(
            m_lin, financing
        )

        # Panneau détail : lease/buy porte sur équipements + agencement uniquement.
        fixed_capex_monthly = 0.0
        capex_total = equip_capex + agencement_capex

        monthly_cost = (
            equipment_monthly
            + agencement_monthly
            + annexes_monthly
            + fixed_capex_monthly
        )
        marge_nette = marge_produit_mensuelle - monthly_cost

        if monthly_cost == 0:
            warnings.append(f"Coûts mensuels nuls pour {concept} ({financing.mode}).")

        return FinancingCostBreakdown(
            monthly_cost=monthly_cost,
            marge_nette_mensuelle=marge_nette,
            marge_produit_mensuelle=marge_produit_mensuelle,
            ca_ht_mensuel=ca_ht_mensuel,
            ca_fb_ht_mensuel=ca_fb_ht_mensuel,
            ca_nf_ht_mensuel=ca_nf_ht_mensuel,
            equipment_monthly=equipment_monthly,
            agencement_monthly=agencement_monthly,
            annexes_monthly=annexes_monthly,
            fixed_capex_monthly=fixed_capex_monthly,
            capex_total=capex_total,
            amort_months=self.amort_months(financing),
            financing_mode=financing.mode,
            agencement_type=financing.agencement_type,
            equipment_lines=equipment_lines,
            warnings=warnings,
        )