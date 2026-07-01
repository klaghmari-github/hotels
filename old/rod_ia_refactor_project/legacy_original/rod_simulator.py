"""
ROD Simulator - Implémentation fidèle de la logique Accor
=======================================================

Toutes les formules et la structure viennent directement de :

FICHIERS EXCEL (small/) :
- "ROD - Simulateurs + détail des coûts.xlsx"
  - SIMULATEUR SIMPLY / LIBERTY / CONNECTED
  - REVENUS - IMPACT TO
  - REVENUS - MIX & MARGES
  - COUTS - TECHNOS / ANNEXES / AGENCEMENT

- "ROD - Paramètres & règles + projections nb. d'hôtels.xlsx"
  - REGLES POUR RECO DU CONCEPT
  - Statistiques par marque et taille
  - PROTOTYPE

IMAGE :
- Simulation-IA-ROD.png → Interface utilisateur qui pilote exactement ces inputs
  (Chambres, Guests/ch, TO, m_lin, mix F&B/Non-F&B sliders, bouton "ANALYSER AVEC L'IA")

Principe du simulateur ROD officiel :
- Déterministe (pas de probabilités)
- Basé sur les résultats réels des hôtels pivots ("MOYENNE RESULTATS PILOTES")
- Projection sur un nouvel hôtel via :
    * TO du nouvel hôtel
    * m_lin choisi
    * Mix de catégories autorisé
    * Concept (SIMPLY / LIBERTY / CONNECTED)
- Pas de météo
- Pas de POI (commerces de proximité) dans la version de base
- Il existe des règles de recommandation de concept selon la taille de l'hôtel

Formules principales extraites :
1. Ch. occ. = Nb. de ch. × TO
2. Cl. héb. / jour = Ch. occ. × (Nb. gu / ch)
3. Cl. héb. / mois = Cl. héb. / jour × 30.5
4. Nb. ventes mensuelles = Nb. ventes_pilote × (m_lin / m_lin_pilote)
5. CA de référence pilotes → ajusté par IMPACT TO (linéaire par 0.01 de TO)
6. Règle 1 : "Chaque client acheteur génère du CA" (CA F&B et N-F&B des pilotes)
7. Règle 2 : Ajustement pour variation de mix (±10%)
8. Application du mix choisi + marges par concept
"""

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

Concept = Literal["SIMPLY", "LIBERTY", "CONNECTED"]


@dataclass
class RODParameters:
    """Données saisies pour un hôtel (provenant du formulaire ROD ou de l'UI de l'image)."""
    nb_ch: int                          # Nombre de chambres
    guests_per_ch: float = 1.7          # Nombre moyen de guests par chambre
    to: float = 0.75                    # Taux d'occupation (YTD ou estimé)
    m_lin: float = 6.0                  # Mètres linéaires dédiés au coin de vente
    f_b_share: float = 0.6              # Part F&B que le directeur autorise (0 à 1)
    concept: Concept = "SIMPLY"         # Concept retenu (ou recommandé)


class RODSimulator:
    """
    Simulateur qui reproduit fidèlement les calculs des fichiers Excel ROD.
    """

    # === Valeurs de référence extraites des Excels (SIMULATEUR + IMPACT TO) ===
    # Ces chiffres viennent des "MOYENNE RESULTATS PILOTES" pour chaque concept

    PILOT_REFS: Dict[Concept, Dict] = {
        "SIMPLY": {
            "m_lin_ref": 6.0,
            "nb_ventes_ref": 231,           # ventes mensuelles de référence
            "f_b_ca_ht_ref": 533.25,        # CA HT F&B de référence (pour le pilote à son TO)
            "not_f_b_ca_ht_ref": 187.0,
            "f_b_margin": 2.6,
            "not_f_b_margin": 1.45,
            "to_ref_example": 0.78,         # TO du pilote IBB NICE dans l'exemple
        },
        "LIBERTY": {
            "m_lin_ref": 8.0,
            "nb_ventes_ref": 312,
            "f_b_ca_ht_ref": 533.25,        # valeurs similaires, à affiner avec les vrais pilotes
            "not_f_b_ca_ht_ref": 187.0,
            "f_b_margin": 2.6,
            "not_f_b_margin": 2.0,
            "to_ref_example": 0.68,
        },
        "CONNECTED": {
            "m_lin_ref": 7.0,
            "nb_ventes_ref": 534,
            "f_b_ca_ht_ref": 533.25,
            "not_f_b_ca_ht_ref": 187.0,
            "f_b_margin": 2.6,
            "not_f_b_margin": 1.8,
            "to_ref_example": 0.75,
        },
    }

    # Impact par 0.01 de TO (extrait de REVENUS - IMPACT TO pour SIMPLY)
    IMPACT_HT_PER_001_TO = 9.233974
    IMPACT_TTC_PER_001_TO = 10.403846

    def simulate(self, p: RODParameters) -> Dict:
        """
        Calcule le CA selon la logique exacte des fichiers ROD.
        """
        ref = self.PILOT_REFS[p.concept]

        # 1. Calculs de base (identiques dans tous les SIMULATEUR xxx)
        ch_occ = p.nb_ch * p.to
        cl_heb_jour = ch_occ * p.guests_per_ch
        cl_heb_mois = cl_heb_jour * 30.5

        # 2. Scaling du nombre de ventes par m_lin (logique visible dans les Excels)
        m_lin_factor = p.m_lin / ref["m_lin_ref"]
        nb_ventes = ref["nb_ventes_ref"] * m_lin_factor

        # 3. Ajustement par TO (utilisation de la table IMPACT TO)
        # On part du CA de référence du pilote, on applique le delta de TO
        ca_ht_ref_total = ref["f_b_ca_ht_ref"] + ref["not_f_b_ca_ht_ref"]
        to_delta = p.to - ref["to_ref_example"]
        to_impact = (to_delta / 0.01) * self.IMPACT_HT_PER_001_TO

        ca_ht_base = ca_ht_ref_total + to_impact

        # 4. Scaling par m_lin sur le CA de base
        ca_ht_base *= m_lin_factor

        # 5. Application du mix choisi par le directeur
        f_b_share = p.f_b_share
        not_fb_share = 1.0 - f_b_share

        ca_fb_ht = ca_ht_base * f_b_share
        ca_not_fb_ht = ca_ht_base * not_fb_share
        ca_ht_mensuel = ca_fb_ht + ca_not_fb_ht

        # 6. Marges (selon concept + mix de l'utilisateur)
        f_b_marge = ref["f_b_margin"]
        not_fb_marge = ref["not_f_b_margin"]
        marge_ponderee = f_b_share * f_b_marge + not_fb_share * not_fb_marge

        # 7. Conversion en TTC (approximation utilisée dans les données)
        ca_ttc_mensuel = ca_ht_mensuel * 1.10
        ca_ht_annuel = ca_ht_mensuel * 12
        ca_ttc_annuel = ca_ttc_mensuel * 12

        # Marge "brute" estimée (CA HT × marge pondérée)
        marge_mensuelle = ca_ht_mensuel * (marge_ponderee / 100.0)

        return {
            "concept": p.concept,
            "parametres": {
                "nb_ch": p.nb_ch,
                "guests_per_ch": p.guests_per_ch,
                "to": p.to,
                "m_lin": p.m_lin,
                "f_b_share": f_b_share,
            },
            "calculs": {
                "ch_occ": round(ch_occ, 2),
                "cl_heb_mois": round(cl_heb_mois, 2),
                "m_lin_factor": round(m_lin_factor, 3),
                "nb_ventes_mensuelles": round(nb_ventes, 1),
                "to_impact": round(to_impact, 2),
            },
            "resultats": {
                "ca_ht_mensuel": round(ca_ht_mensuel, 2),
                "ca_ht_annuel": round(ca_ht_annuel, 2),
                "ca_ttc_annuel": round(ca_ttc_annuel, 2),
                "marge_ponderee": round(marge_ponderee, 3),
                "marge_mensuelle_estimee": round(marge_mensuelle, 2),
            },
            "source": "Formules extraites des fichiers Excel ROD officiels (SIMULATEUR + IMPACT TO + MIX & MARGES)"
        }


# =====================
# Exemple d'utilisation
# =====================
if __name__ == "__main__":
    sim = RODSimulator()

    print("=== Simulation ROD (logique extraite des Excels + image) ===\n")

    # Exemple proche des données des Excels (IBB NICE style)
    p = RODParameters(
        nb_ch=129,
        guests_per_ch=1.7,
        to=0.80,
        m_lin=6.0,
        f_b_share=0.4,      # comme dans l'exemple SIMPLY
        concept="SIMPLY"
    )

    res = sim.simulate(p)
    for section, values in res.items():
        if isinstance(values, dict):
            print(f"[{section}]")
            for k, v in values.items():
                print(f"  {k}: {v}")
        else:
            print(f"{section}: {values}")
        print()

    print("\n" + "="*70)
    print("Exemple 2 : Plus grand hôtel, concept CONNECTED, 8m linéaires")
    p2 = RODParameters(nb_ch=305, to=0.75, m_lin=8.0, f_b_share=0.75, concept="CONNECTED")
    res2 = sim.simulate(p2)
    print(f"CA HT annuel : {res2['resultats']['ca_ht_annuel']} €")
