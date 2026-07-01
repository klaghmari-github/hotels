"""
ROD Rules Engine
================

Implémentation des règles officielles de recommandation de concept
provenant du fichier :
"ROD - Paramètres & règles + projections nb. d'hôtels.xlsx"
  - Feuille "REGLES POUR RECO DU CONCEPT"

Règles principales extraites :

REGLE #1 (principale - taille hôtel) :
- 0 à 49 chambres  → SIMPLY
- + de 50 chambres → LIBERTY ou CONNECTED (selon autres règles)

REGLE #2 :
- L'hôtel doit avoir au moins 1 des 5 catégories Non-F&B :
  Cosmetics, Kids items, Ready-to-wear, Accessories, Souvenirs

REGLE #3 (m_lin) :
- Si l'hôtel veut + de 4 mètres linéaires → LIBERTY STORE
- <= 4 m lin → plutôt SIMPLY (sous conditions)

REGLE #4 (équipement existant) :
- Si l'hôtel possède déjà une vitrine réfrigérée (YES) → impact sur le choix

REGLE #5 (final) :
- Tri selon TO moyen (YTD) < 70% vs >= 70%

Politique stratégique (signalée par l'utilisateur) :
- Toujours proposer la **haute gamme** (CONNECTED ou LIBERTY haut de gamme)
  aux **hôtels haut de gamme** (grands Novotel, Mercure haut de gamme, TO élevé, positionnement premium),
  même si le calcul de marge pure dirait le contraire.

Répartition des marques (pour projections groupe) :
- Très déséquilibrée : Ibis Budget (342) + Ibis Styles = gros volume
- Novotel et Mercure beaucoup moins nombreux.
- Les règles et projections doivent tenir compte de ce volume par marque/taille.

Ce module permet de :
- Calculer les concepts autorisés/recommandés pour un hôtel donné en respectant les règles.
- Filtrer l'optimiseur IA pour ne proposer que des solutions conformes aux règles.
"""

from typing import List, Dict
import pandas as pd
from pathlib import Path

# ============================================================
# Règles codifiées
# ============================================================

def get_allowed_concepts(
    nb_ch: int,
    brand: str = "",
    to: float = 0.75,
    desired_m_lin: float = 6.0,
    has_refrigerated_display: bool = False,   # REGLE #4
    has_min_non_fb_categories: bool = True,   # REGLE #2
    force_high_end_policy: bool = True        # Politique "haute gamme aux haut de gamme"
) -> List[str]:
    """
    Retourne la liste des concepts autorisés selon les règles ROD.

    force_high_end_policy=True : force CONNECTED/LIBERTY pour les hôtels haut de gamme
    même si la rentabilité pure serait meilleure avec un concept inférieur.
    """
    allowed = set()

    # === REGLE #1 : Taille principale ===
    if nb_ch <= 49:
        allowed.add("SIMPLY")
    else:
        # Grand hôtel → LIBERTY ou CONNECTED
        if desired_m_lin > 4:
            allowed.add("LIBERTY")
            allowed.add("CONNECTED")
        else:
            allowed.add("LIBERTY")
            # SIMPLY possible dans certains cas, mais rare pour >50ch

    # === REGLE #3 : m_lin ===
    if desired_m_lin > 4:
        allowed.discard("SIMPLY")   # force au moins LIBERTY
        if "LIBERTY" not in allowed and "CONNECTED" not in allowed:
            allowed.add("LIBERTY")

    # === REGLE #2 : Catégories Non-F&B obligatoires ===
    if not has_min_non_fb_categories:
        # Dans ce cas, on reste sur des concepts plus basiques
        allowed.discard("CONNECTED")
        if nb_ch > 49:
            allowed.add("LIBERTY")  # fallback

    # === REGLE #4 : Vitrine réfrigérée existante ===
    if has_refrigerated_display:
        # L'hôtel a déjà du froid → on peut monter plus facilement en gamme
        if nb_ch > 49:
            allowed.add("CONNECTED")

    # === REGLE #5 : TO (tri final, pas de blocage dur ici) ===
    # On peut l'utiliser pour prioriser, mais pas pour filtrer strictement ici.

    # === Politique stratégique "Haute gamme aux hôtels haut de gamme" ===
    if force_high_end_policy:
        is_high_end_hotel = (
            nb_ch >= 150 or
            brand.upper() in ["NOVOTEL", "MERCURE"] or
            (to >= 0.75 and nb_ch >= 100)
        )
        if is_high_end_hotel:
            # On force au moins LIBERTY, et idéalement CONNECTED pour les vrais haut de gamme
            if nb_ch >= 200 or brand.upper() == "NOVOTEL":
                allowed.add("CONNECTED")
            else:
                allowed.add("LIBERTY")
            # On peut retirer SIMPLY pour ces hôtels
            allowed.discard("SIMPLY")

    # Nettoyage final
    if not allowed:
        allowed = {"SIMPLY"}  # fallback conservateur

    return sorted(list(allowed))


def get_recommended_concept(
    nb_ch: int,
    brand: str = "",
    to: float = 0.75,
    desired_m_lin: float = 6.0,
    has_refrigerated_display: bool = False,
    has_min_non_fb_categories: bool = True,
    force_high_end_policy: bool = True
) -> str:
    """
    Retourne le concept principal recommandé en suivant les règles + politique.
    Ordre de préférence pour les grands hôtels : CONNECTED > LIBERTY > SIMPLY
    """
    allowed = get_allowed_concepts(
        nb_ch, brand, to, desired_m_lin,
        has_refrigerated_display, has_min_non_fb_categories,
        force_high_end_policy
    )

    # Priorité pour haute gamme
    if "CONNECTED" in allowed:
        return "CONNECTED"
    elif "LIBERTY" in allowed:
        return "LIBERTY"
    else:
        return "SIMPLY"


# ============================================================
# Distribution des marques (pour projections et pondération)
# ============================================================

def load_brand_distribution() -> pd.DataFrame:
    """
    Charge la répartition réelle des hôtels par marque et taille.
    Utile pour estimer le volume total quand on projette sur tout le groupe.
    """
    f = Path("small/ROD - Paramètres & règles + projections nb. d'hôtels.xlsx")
    df = pd.read_excel(f, sheet_name="NB CH 2", header=None)

    # Extraction simplifiée des totaux par marque (basé sur les données vues)
    data = [
        {"brand": "IBIS BUDGET", "total_hotels": 342, "pct": 342/1343},
        {"brand": "IBIS STYLES", "total_hotels": 267, "pct": 267/1343},
        {"brand": "NOVOTEL",     "total_hotels": 117, "pct": 117/1343},
        {"brand": "MERCURE",     "total_hotels": 255, "pct": 255/1343},
    ]
    return pd.DataFrame(data)


# ============================================================
# Exemple d'utilisation des règles
# ============================================================

if __name__ == "__main__":
    print("=== Test des règles ROD ===\n")

    examples = [
        {"name": "Ibis Budget petit", "nb_ch": 45, "brand": "IBIS BUDGET", "to": 0.65, "m_lin": 3.0},
        {"name": "Ibis Budget moyen", "nb_ch": 120, "brand": "IBIS BUDGET", "to": 0.72, "m_lin": 5.0},
        {"name": "Novotel haut de gamme", "nb_ch": 220, "brand": "NOVOTEL", "to": 0.78, "m_lin": 8.0},
        {"name": "Mercure premium", "nb_ch": 180, "brand": "MERCURE", "to": 0.81, "m_lin": 7.0},
    ]

    for ex in examples:
        rec = get_recommended_concept(
            nb_ch=ex["nb_ch"],
            brand=ex["brand"],
            to=ex["to"],
            desired_m_lin=ex["m_lin"],
            force_high_end_policy=True
        )
        allowed = get_allowed_concepts(
            nb_ch=ex["nb_ch"],
            brand=ex["brand"],
            to=ex["to"],
            desired_m_lin=ex["m_lin"],
            force_high_end_policy=True
        )
        print(f"{ex['name']:25} | nb_ch={ex['nb_ch']:3} | brand={ex['brand']:12} | TO={ex['to']:.2f} | m_lin={ex['m_lin']}")
        print(f"  → Recommandé : {rec}")
        print(f"  → Autorisés  : {allowed}\n")

    print("Distribution des marques (volume) :")
    print(load_brand_distribution())
