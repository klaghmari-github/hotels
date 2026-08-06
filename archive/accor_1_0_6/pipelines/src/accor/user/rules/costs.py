"""
Coûts mensuels ROD — fidèle à ``simulateur_rules.html`` §10–11.

Coûts = Techno + Annexes + Agencement
- Techno : équipement principal, vitrine, frigos, licence, frais OS (amort 60 mois ou lease)
- Annexes : électricité + staff (proportionnels au nb d'équipements)
- Agencement : €/ML selon Classic|Premium|Bespoke, amorti 84 mois
"""

from __future__ import annotations

from typing import Any

from archive.accor_1_0_6.pipelines.src.accor.user.models import CostResult, SimulationRequest
from archive.accor_1_0_6.pipelines.src.accor.user.reference import RodReference
from archive.accor_1_0_6.pipelines.src.accor.user.rules.pilot_table import AGENCEMENT_AMORT_MONTHS, AGENCEMENT_EUR_PER_ML


class CostRules:
    """Capex + opex mensuels ligne à ligne (spec Excel)."""

    def __init__(self, reference: RodReference | None = None) -> None:
        self._ref = reference or RodReference()

    @staticmethod
    def _hotel_has_vitrine(request: SimulationRequest) -> bool:
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

    def compute(self, request: SimulationRequest, concept: str) -> CostResult:
        concept = (concept or "").upper().strip()
        if request.store is None:
            raise ValueError("store requis pour le calcul des coûts")

        store = request.store
        m_lin = max(float(store.m_lin or 0), 0.0)
        mix_fb = float(store.mix_fb or 0.0)
        if mix_fb > 1.0:
            mix_fb /= 100.0
        mix_nfb = 1.0 - mix_fb

        contract = str(getattr(store, "contract", None) or "BUY").upper()
        if contract not in ("BUY", "LEASE"):
            contract = "BUY"
        agencement = str(getattr(store, "agencement", None) or "CLASSIC").upper()
        if agencement not in ("CLASSIC", "PREMIUM", "BESPOKE"):
            agencement = "CLASSIC"

        nb_scanners = max(int(getattr(store, "nb_scanners", 1) or 1), 0)
        nb_caisses = max(int(getattr(store, "nb_caisses", 1) or 1), 0)
        nb_vitrines = max(int(getattr(store, "nb_vitrines", 1) or 0), 0)
        nb_frigos_froid = max(int(getattr(store, "nb_frigos_froid", 3) or 0), 0)
        nb_frigos_ambiant = max(int(getattr(store, "nb_frigos_ambiant", 0) or 0), 0)

        # Garde-fous équipements (spec)
        has_vitrine_hotel = self._hotel_has_vitrine(request)
        if concept in ("SIMPLY", "LIBERTY"):
            # min 1 vitrine à équiper si l'hôtel n'en a pas déjà
            if not has_vitrine_hotel and nb_vitrines < 1:
                nb_vitrines = 1
            if has_vitrine_hotel:
                nb_vitrines = 0  # déjà en place → pas de coût vitrine

        if concept == "CONNECTED":
            if mix_fb < 0.10:
                nb_frigos_froid = 0
            if mix_nfb < 0.10:
                nb_frigos_ambiant = 0

        lines: list[dict[str, Any]] = []
        warnings: list[str] = []

        def add_line(
            *,
            lid: str,
            label: str,
            group: str,
            qty: float,
            capex_unit: float = 0.0,
            monthly_unit: float = 0.0,
            amort: float = 60.0,
        ) -> None:
            if qty <= 0:
                return
            if monthly_unit > 0:
                monthly = monthly_unit * qty
                capex = capex_unit * qty
            elif capex_unit > 0 and amort > 0:
                capex = capex_unit * qty
                monthly = capex / amort
            else:
                monthly, capex = 0.0, capex_unit * qty
            lines.append(
                {
                    "id": lid,
                    "label": label,
                    "group": group,
                    "qty": qty,
                    "monthly": round(monthly, 4),
                    "capex": round(capex, 4),
                }
            )

        # ---------- TECHNO ----------
        if concept == "SIMPLY":
            add_line(
                lid="scanner",
                label="Scanner",
                group="techno",
                qty=max(nb_scanners, 1),
                capex_unit=500.0,
                monthly_unit=500.0 / 60.0,
                amort=60.0,
            )
            add_line(
                lid="vitrine",
                label="Vitrine",
                group="techno",
                qty=nb_vitrines,
                capex_unit=800.0,
                monthly_unit=800.0 / 60.0,
                amort=60.0,
            )
            add_line(
                lid="licence",
                label="Licence logicielle",
                group="techno",
                qty=1,
                capex_unit=3000.0,
                monthly_unit=50.0,
                amort=60.0,
            )
            add_line(
                lid="frais_os",
                label="Frais OS",
                group="techno",
                qty=1,
                capex_unit=1000.0,
                monthly_unit=1000.0 / 60.0,
                amort=60.0,
            )
        elif concept == "LIBERTY":
            if contract == "LEASE":
                add_line(
                    lid="caisse",
                    label="Caisse (lease)",
                    group="techno",
                    qty=max(nb_caisses, 1),
                    monthly_unit=250.0,
                    capex_unit=0.0,
                )
            else:
                # BUY : 15 000 × 0,80 = 12 000 → /60 = 200 €/mois
                add_line(
                    lid="caisse",
                    label="Caisse (BUY −20 %)",
                    group="techno",
                    qty=max(nb_caisses, 1),
                    capex_unit=12000.0,
                    monthly_unit=12000.0 / 60.0,
                    amort=60.0,
                )
            add_line(
                lid="vitrine",
                label="Vitrine",
                group="techno",
                qty=nb_vitrines,
                capex_unit=800.0,
                monthly_unit=800.0 / 60.0,
                amort=60.0,
            )
            add_line(
                lid="licence",
                label="Licence logicielle",
                group="techno",
                qty=1,
                capex_unit=3000.0,
                monthly_unit=50.0,
                amort=60.0,
            )
            add_line(
                lid="frais_os",
                label="Frais OS",
                group="techno",
                qty=1,
                capex_unit=2000.0,
                monthly_unit=2000.0 / 60.0,
                amort=60.0,
            )
        else:  # CONNECTED
            if contract == "LEASE":
                add_line(
                    lid="frigo_froid",
                    label="Frigo froid (lease)",
                    group="techno",
                    qty=nb_frigos_froid,
                    monthly_unit=450.0,
                    capex_unit=0.0,
                )
            else:
                add_line(
                    lid="frigo_froid",
                    label="Frigo froid (BUY)",
                    group="techno",
                    qty=nb_frigos_froid,
                    capex_unit=27000.0,
                    monthly_unit=27000.0 / 60.0,
                    amort=60.0,
                )
            # Frigo ambiant si N-F&B
            if nb_frigos_ambiant > 0:
                add_line(
                    lid="frigo_ambiant",
                    label="Frigo ambiant",
                    group="techno",
                    qty=nb_frigos_ambiant,
                    capex_unit=24000.0,
                    monthly_unit=24000.0 / 60.0,
                    amort=60.0,
                )
            add_line(
                lid="frais_os",
                label="Frais OS",
                group="techno",
                qty=1,
                capex_unit=3000.0,
                monthly_unit=3000.0 / 60.0,
                amort=60.0,
            )

        # ---------- ANNEXES (proportionnels qty) ----------
        if concept == "SIMPLY":
            add_line(
                lid="elec_scanner",
                label="Élec. scanner",
                group="annexes",
                qty=max(nb_scanners, 1),
                monthly_unit=2.0,
            )
            add_line(
                lid="elec_vitrine",
                label="Élec. vitrine",
                group="annexes",
                qty=nb_vitrines,
                monthly_unit=10.0,
            )
            add_line(lid="staff", label="Staff", group="annexes", qty=1, monthly_unit=3.0)
        elif concept == "LIBERTY":
            add_line(
                lid="elec_caisse",
                label="Élec. caisse",
                group="annexes",
                qty=max(nb_caisses, 1),
                monthly_unit=10.0,
            )
            add_line(
                lid="elec_vitrine",
                label="Élec. vitrine",
                group="annexes",
                qty=nb_vitrines,
                monthly_unit=10.0,
            )
            add_line(lid="staff", label="Staff", group="annexes", qty=1, monthly_unit=10.0)
        else:
            add_line(
                lid="elec_frigo_froid",
                label="Élec. frigo froid",
                group="annexes",
                qty=nb_frigos_froid,
                monthly_unit=20.0,
            )
            add_line(
                lid="elec_frigo_ambiant",
                label="Élec. frigo ambiant",
                group="annexes",
                qty=nb_frigos_ambiant,
                monthly_unit=15.0,
            )
            add_line(lid="staff", label="Staff", group="annexes", qty=1, monthly_unit=10.0)

        # ---------- AGENCEMENT ----------
        # Connected : ML d'agencement = ml_ref pilote ou m_lin saisi (si > 0)
        ml_ag = m_lin if m_lin > 0 else float(
            {"SIMPLY": 6, "LIBERTY": 8, "CONNECTED": 7}.get(concept, 6)
        )
        if concept == "CONNECTED" and m_lin <= 0:
            ml_ag = 7.0
        prix_ml = AGENCEMENT_EUR_PER_ML.get(concept, {}).get(agencement, 1000.0)
        ag_capex = prix_ml * ml_ag
        ag_monthly = ag_capex / AGENCEMENT_AMORT_MONTHS if AGENCEMENT_AMORT_MONTHS else 0.0
        lines.append(
            {
                "id": "agencement",
                "label": f"Agencement {agencement.title()}",
                "group": "agencement",
                "qty": ml_ag,
                "monthly": round(ag_monthly, 4),
                "capex": round(ag_capex, 4),
            }
        )

        if has_vitrine_hotel and concept in ("SIMPLY", "LIBERTY"):
            warnings.append("Vitrine déjà en place — coût vitrine non ajouté.")

        techno_m = sum(float(x["monthly"]) for x in lines if x["group"] == "techno")
        annexes_m = sum(float(x["monthly"]) for x in lines if x["group"] == "annexes")
        agencement_m = ag_monthly
        monthly = techno_m + annexes_m + agencement_m
        capex = sum(float(x["capex"]) for x in lines)

        # Coût total sur 60 mois (spec amortissement)
        licence_monthly = sum(
            float(x["monthly"])
            for x in lines
            if x["id"] in ("licence",) or "licence" in str(x["label"]).lower()
        )
        cost_60 = (
            sum(float(x["capex"]) for x in lines if float(x["capex"]) > 0)
            + 60.0 * (licence_monthly + annexes_m + agencement_m)
        )
        # pour lease sans capex : 60 × monthly techno
        lease_monthly = sum(
            float(x["monthly"])
            for x in lines
            if x["group"] == "techno" and float(x["capex"]) <= 0
        )
        cost_60 += 60.0 * lease_monthly

        return CostResult(
            concept=concept,
            monthly_cost=monthly,
            annual_cost=monthly * 12,
            capex=capex,
            techno_monthly=techno_m,
            annexes_monthly=annexes_m,
            agencement_monthly=agencement_m,
            cost_lines=lines,
            warnings=warnings,
            cost_over_60m=float(cost_60),
        )
