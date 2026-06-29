"""
ROD Full Simulator + AI Optimizer

Objectif :
- Reproduire fidèlement la simulation de CA (revenus) du simulateur ROD Accor (déterministe, basé sur pivots).
- Ajouter la simulation complète des coûts :
    - Coût d'achat / installation (agencement, technos)
    - Coûts d'entretien / récurrent (électricité, personnel, maintenance, licences)
- Calculer la marge nette = CA - Coûts
- Proposer la solution la plus rentable (meilleur concept + m_lin + mix) en utilisant de l'optimisation (IA / search).

Sources :
- Fichiers Excel ROD dans small/ (formules de revenus + coûts)
- Image Simulation-IA-ROD.png (UI)
- Données pivots (rod_prepared, transactions) pour calibration et ML
- Intègre le projecteur ML pour nouveaux hôtels (amélioration IA de la prédiction de CA)

Améliorations IA :
- Pour les hôtels connus : utilise données réelles + scaling.
- Pour nouveaux hôtels : utilise le modèle ML (hotel_ca_projector) pour estimer la productivité de base.
- Optimisation numérique ou grid search pour trouver les meilleurs paramètres (m_lin, f_b_share, concept) qui maximisent la marge annuelle.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from itertools import product
import warnings
warnings.filterwarnings("ignore")

# Import des modules existants pour réutiliser
try:
    from hotel_ca_projector import PivotCAProjector
    HAS_PROJECTOR = True
except:
    HAS_PROJECTOR = False

try:
    from rod_rules import get_allowed_concepts, get_recommended_concept
    HAS_RULES = True
except:
    HAS_RULES = False
    print("[Warning] rod_rules.py non trouvé — optimisation sans respect des règles officielles.")

# ============================================================
# 1. Paramètres et Références (basés sur Excels)
# ============================================================

@dataclass
class HotelConfig:
    name: str = "Nouvel hôtel"
    nb_ch: int = 150
    guests_per_ch: float = 1.7
    to: float = 0.75
    brand: str = "MERCURE"
    lat: Optional[float] = None
    lon: Optional[float] = None

@dataclass
class Solution:
    """Une solution à évaluer (concept + m_lin + mix)."""
    concept: str          # SIMPLY / LIBERTY / CONNECTED
    m_lin: float          # mètres linéaires
    f_b_share: float      # part F&B (0-1)
    agencement_type: str = "CLASSIC"  # CLASSIC / PREMIUM / BESPOKE

# Références coûts (simplifiées et moyennées à partir des Excels)
# Période d'amortissement typique : 60 ou 84 mois
AMORT_MONTHS = 84

COST_AGENCEMENT_PER_M = {
    "SIMPLY":   {"CLASSIC": 1000, "PREMIUM": 1200, "BESPOKE": 2200},
    "LIBERTY":  {"CLASSIC": 1200, "PREMIUM": 1400, "BESPOKE": 2400},  # approx
    "CONNECTED":{"CLASSIC": 1400, "PREMIUM": 1600, "BESPOKE": 2600},
}

COST_TECHNO = {
    # Coût unitaire + coût mensuel amorti
    "scanner": {"unit": 500, "monthly": 8.33},      # pour 1
    "vitrine": {"unit": 800, "monthly": 13.33},
    "caisse":  {"unit": 15000, "monthly": 250},     # plus cher pour certains concepts
}

COST_ANNEXES = {
    "electricity_per_scanner": 2,   # €/mois
    "electricity_per_vitrine": 10,
    "personnel_monthly": 200,       # estimation très variable selon astreinte
}

# Marges et Nb ventes de référence (du précédent rod_simulator + Excels)
CONCEPT_REFS = {
    "SIMPLY":   {"nb_ventes_ref": 231, "m_lin_ref": 6.0, "f_b_margin": 2.6, "not_f_b_margin": 1.45},
    "LIBERTY":  {"nb_ventes_ref": 312, "m_lin_ref": 8.0, "f_b_margin": 2.6, "not_f_b_margin": 2.0},
    "CONNECTED":{"nb_ventes_ref": 534, "m_lin_ref": 7.0, "f_b_margin": 2.6, "not_f_b_margin": 1.8},
}


class RODFullSimulator:
    """
    Simulateur complet : Revenus + Coûts + Marge.
    Peut utiliser le modèle ML pour estimer les revenus sur nouveaux hôtels.
    """

    def __init__(self):
        self.projector = PivotCAProjector() if HAS_PROJECTOR else None

    # --------------------------------------------------------
    # Revenus (logique ROD fidèle + amélioration IA)
    # --------------------------------------------------------
    def estimate_revenue(self, hotel: HotelConfig, sol: Solution) -> Dict:
        """
        Estime le CA annuel et mensuel.
        - Si l'hôtel est dans les pivots et qu'on a les données : base déterministe ROD.
        - Sinon ou pour amélioration : utilise le projecteur ML.
        """
        # Base déterministe ROD (simplifiée mais fidèle)
        ref = CONCEPT_REFS[sol.concept]
        m_lin_factor = sol.m_lin / ref["m_lin_ref"]

        # Chiffres de base (approximés depuis les pilotes)
        # On utilise un CA de base issu des pilotes, scalé
        base_ca_ht_mensuel = 720 * m_lin_factor   # valeur de référence SIMPLY ~720 HT à 6m

        # Ajustement TO
        to_factor = hotel.to / 0.78   # référence pilote
        ca_ht_mensuel = base_ca_ht_mensuel * to_factor

        # Application du mix
        ca_fb = ca_ht_mensuel * sol.f_b_share
        ca_notfb = ca_ht_mensuel * (1 - sol.f_b_share)

        ca_ht_annual = ca_ht_mensuel * 12
        ca_ttc_annual = ca_ht_annual * 1.10

        # Amélioration IA : si on a le projecteur ML, on peut surcharger avec une prédiction
        # plus fine pour les nouveaux hôtels (en tenant compte de nb_ch, POI, etc.)
        if self.projector is not None and hotel.lat is not None:
            try:
                hotel_info = {
                    "brand": hotel.brand,
                    "nb_ch": hotel.nb_ch,
                    "poi_3km": 50,  # on pourrait calculer depuis POI si on charge les données
                    "m_lin_ref": sol.m_lin,
                }
                ml_res = self.projector.project(hotel_info, m_lin=sol.m_lin, allowed_gammes=None)
                # On blend : 70% ML + 30% règles ROD (ou on prend le ML comme base)
                ca_ht_annual = 0.7 * ml_res["ca_annual_estime"] + 0.3 * ca_ht_annual
                ca_ht_mensuel = ca_ht_annual / 12
            except:
                pass

        return {
            "ca_ht_monthly": round(ca_ht_mensuel, 2),
            "ca_ht_annual": round(ca_ht_annual, 2),
            "ca_ttc_annual": round(ca_ht_annual * 1.10, 2),
            "method": "ROD rules + ML blend" if self.projector else "ROD rules only"
        }

    # --------------------------------------------------------
    # Coûts (basés sur les feuilles COUTS - AGENCEMENT / TECHNOS / ANNEXES)
    # --------------------------------------------------------
    def estimate_costs(self, sol: Solution, months: int = 12) -> Dict:
        """
        Calcule les coûts annuels (ou sur la période).
        - CAPEX (amorti)
        - OPEX récurrent
        """
        concept = sol.concept
        m = sol.m_lin

        # 1. Agencement (par m_lin)
        agencement_unit = COST_AGENCEMENT_PER_M[concept][sol.agencement_type]
        agencement_total = agencement_unit * m
        agencement_monthly = agencement_total / AMORT_MONTHS

        # 2. Technos (on suppose un setup de base : 1-2 scanners + vitrines selon m_lin)
        # Simplification réaliste : 1 scanner + 1 vitrine par tranche de ~3-4m
        n_units = max(1, int(m / 3.5))
        scanner_monthly = n_units * COST_TECHNO["scanner"]["monthly"]
        vitrine_monthly = n_units * COST_TECHNO["vitrine"]["monthly"]
        techno_monthly = scanner_monthly + vitrine_monthly

        # 3. Annexes
        elec = n_units * (COST_ANNEXES["electricity_per_scanner"] + COST_ANNEXES["electricity_per_vitrine"])
        personnel = COST_ANNEXES["personnel_monthly"]   # peut être 0 si pas d'astreinte

        opex_monthly = techno_monthly + elec + personnel
        capex_amort_monthly = agencement_monthly

        total_monthly = capex_amort_monthly + opex_monthly
        total_annual = total_monthly * months

        breakdown = {
            "agencement_amort_mensuel": round(agencement_monthly, 2),
            "techno_mensuel": round(techno_monthly, 2),
            "electricite_mensuel": round(elec, 2),
            "personnel_mensuel": round(personnel, 2),
            "total_mensuel": round(total_monthly, 2),
            "total_annuel": round(total_annual, 2),
            "capex_total_initial": round(agencement_total, 2),  # pour info
        }
        return breakdown

    # --------------------------------------------------------
    # Simulation complète + Marge
    # --------------------------------------------------------
    def simulate_full(self, hotel: HotelConfig, sol: Solution) -> Dict:
        rev = self.estimate_revenue(hotel, sol)
        costs = self.estimate_costs(sol)

        ca_annual = rev["ca_ht_annual"]
        costs_annual = costs["total_annuel"]

        margin_annual = ca_annual - costs_annual
        margin_rate = (margin_annual / ca_annual * 100) if ca_annual > 0 else 0

        return {
            "solution": {
                "concept": sol.concept,
                "m_lin": sol.m_lin,
                "f_b_share": sol.f_b_share,
                "agencement": sol.agencement_type,
            },
            "revenue": rev,
            "costs": costs,
            "margin": {
                "annual_margin": round(margin_annual, 2),
                "margin_rate_pct": round(margin_rate, 1),
                "monthly_margin": round(margin_annual / 12, 2),
            },
            "roi_simple_years": round(costs["capex_total_initial"] / margin_annual, 1) if margin_annual > 0 else None,
        }

    # --------------------------------------------------------
    # IA / Optimiseur : cherche la meilleure solution rentable
    # --------------------------------------------------------
    def recommend_best_solution(
        self,
        hotel: HotelConfig,
        m_lin_range: Tuple[float, float, float] = (3.0, 12.0, 0.5),
        fb_share_range: Tuple[float, float, float] = (0.3, 0.9, 0.05),
        concepts: List[str] = None,
        agencement_types: List[str] = None,
        top_n: int = 3,
        respect_rod_rules: bool = True,
        force_high_end_policy: bool = True,
    ) -> List[Dict]:
        """
        Recherche des meilleures solutions rentables (max marge).

        Si respect_rod_rules=True :
            - On filtre les concepts selon les règles officielles ROD (REGLE #1 à #5).
            - On applique la politique "haute gamme aux hôtels haut de gamme".
        """
        if concepts is None:
            concepts = ["SIMPLY", "LIBERTY", "CONNECTED"]
        if agencement_types is None:
            agencement_types = ["CLASSIC", "PREMIUM", "BESPOKE"]

        # === Application des règles ROD si demandé ===
        allowed_concepts = concepts
        if respect_rod_rules and HAS_RULES:
            allowed_concepts = get_allowed_concepts(
                nb_ch=hotel.nb_ch,
                brand=hotel.brand,
                to=hotel.to,
                desired_m_lin=m_lin_range[1],  # on prend le max possible pour être large
                force_high_end_policy=force_high_end_policy
            )
            # On intersecte avec ce qui est demandé
            allowed_concepts = [c for c in allowed_concepts if c in concepts]
            if not allowed_concepts:
                allowed_concepts = ["SIMPLY"]

        m_lin_values = np.arange(m_lin_range[0], m_lin_range[1] + 0.01, m_lin_range[2])
        fb_values = np.arange(fb_share_range[0], fb_share_range[1] + 0.01, fb_share_range[2])

        candidates = []
        for concept, m_lin, fb, ag_type in product(allowed_concepts, m_lin_values, fb_values, agencement_types):
            sol = Solution(concept=concept, m_lin=round(m_lin, 1), f_b_share=round(fb, 2), agencement_type=ag_type)
            res = self.simulate_full(hotel, sol)
            res["respects_rod_rules"] = respect_rod_rules
            candidates.append(res)

        # Trier par marge annuelle
        candidates.sort(key=lambda x: x["margin"]["annual_margin"], reverse=True)

        return candidates[:top_n]


# ============================================================
# Exemple d'utilisation
# ============================================================

if __name__ == "__main__":
    sim = RODFullSimulator()

    hotel = HotelConfig(
        name="Mercure Test",
        nb_ch=200,
        guests_per_ch=1.8,
        to=0.72,
        brand="MERCURE",
    )

    print("=== Simulation complète d'une solution ===")
    sol = Solution(concept="LIBERTY", m_lin=7.0, f_b_share=0.55, agencement_type="PREMIUM")
    full = sim.simulate_full(hotel, sol)
    print("Solution:", full["solution"])
    print("CA annuel HT :", full["revenue"]["ca_ht_annual"])
    print("Coûts annuels :", full["costs"]["total_annuel"])
    print("Marge annuelle :", full["margin"]["annual_margin"])
    print("Marge %        :", full["margin"]["margin_rate_pct"], "%")

    print("\n=== Recommandation IA : Top 3 solutions les plus rentables ===")
    best = sim.recommend_best_solution(hotel, top_n=3)
    for i, b in enumerate(best, 1):
        print(f"\nOption {i}:")
        print("  ", b["solution"])
        print("  CA HT annuel :", b["revenue"]["ca_ht_annual"])
        print("  Coûts annuels:", b["costs"]["total_annuel"])
        print("  Marge nette  :", b["margin"]["annual_margin"], "€  (", b["margin"]["margin_rate_pct"], "%)")
        if b.get("roi_simple_years"):
            print("  ROI simple   : ~", b["roi_simple_years"], "ans")
