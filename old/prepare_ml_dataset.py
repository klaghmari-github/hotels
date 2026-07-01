"""
prepare_ml_dataset.py

Reproduit ton pipeline IA pour les données de ventes + fusion POI + Météo.

Étapes :
1. Charger les données de ventes (data.csv)
2. Supprimer les données 2026 (train sur le reste)
3. Calculer CA (montant) et nombre de ventes
4. Agréger par mois + TYPE (FB / NON_FB) + GAMME (ALCOOL, JEU_ENFANTS, etc.)
5. Créer les features larges par mois (m01__FB__ALCOOL__ca, m01__FB__ALCOOL__ventes, ...)
6. Fusionner avec POI (poi_prepared_data.xlsx) et Météo (weather_prepared_data.xlsx)
7. Garder uniquement les hôtels avec toutes les infos (5 lignes)
8. Sauvegarder le dataset final prêt pour l'IA (~5 x 5000 colonnes)

Le modèle peut ensuite apprendre à prédire les CA et nb_ventes par type/catégorie par mois,
en fonction des features POI + Météo + caractéristiques hôtel (ROD).

Pour un nouvel hôtel :
- Tu auras ses features POI + Météo (via enrich_hotel)
- Tu prédis les patterns de ventes mensuelles par catégorie
- Tu ajustes ensuite avec le m_lin choisi et les catégories autorisées
"""

import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(".")

def prepare_sales_monthly_wide(drop_2026: bool = True) -> pd.DataFrame:
    """
    Charge les ventes, filtre 2026 si demandé,
    agrège par hôtel + mois + TYPE + GAMME,
    pivote en format large.
    """
    print("Chargement des données de ventes...")
    sales = pd.read_csv(DATA_DIR / "data.csv")

    # Nettoyage basique
    sales["DATETIME"] = pd.to_datetime(sales["DATETIME"])
    sales["annee"] = sales["DATETIME"].dt.year
    sales["mois"] = sales["DATETIME"].dt.month

    if drop_2026:
        print("Suppression des données 2026 pour l'entraînement...")
        sales = sales[sales["annee"] < 2026].copy()
        print(f"  → {len(sales)} lignes conservées")

    # Calcul du CA
    sales["montant"] = sales["QUANTITE"] * sales["PRIX TTC"]

    # On utilise ORDER ID pour compter les ventes (tickets uniques) comme dans tes notebooks
    # ou simplement la somme des quantités si tu préfères "nombre de ventes = unités vendues"
    # Ici on suit ta description : "le nombre des ventes"
    # Dans transaction_data.ipynb tu utilisais nunique(ORDER ID) pour nbr_ventes

    # Agrégation
    grouped = (
        sales.groupby(["HOTEL_NAME", "annee", "mois", "TYPE", "GAMME"], dropna=False)
        .agg(
            ca=("montant", "sum"),
            nbr_ventes=("ORDER ID (TICKET DE CAISSE)", "nunique"),  # nombre de tickets
            # ou "nbr_ventes": ("QUANTITE", "sum") si tu veux les unités
        )
        .reset_index()
    )

    # Créer la colonne mois formatée pour le pivot (m01, m02, ...)
    grouped["month_key"] = "m" + grouped["mois"].astype(str).str.zfill(2)

    # Pivot large : features par mois, indépendamment de l'année (somme sur les années < 2026)
    # Colonnes au format que tu utilises : 
    # m01__FB__ALCOOL__montant
    # m01__FB__ALCOOL__nbr_ventes
    # (croisement mois + TYPE (F&B / NON-F&B) + GAMME/catégorie + indicateur)

    pivot_montant = grouped.pivot_table(
        index="HOTEL_NAME",
        columns=["month_key", "TYPE", "GAMME"],
        values="ca",
        aggfunc="sum",
        fill_value=0
    )

    pivot_ventes = grouped.pivot_table(
        index="HOTEL_NAME",
        columns=["month_key", "TYPE", "GAMME"],
        values="nbr_ventes",
        aggfunc="sum",
        fill_value=0
    )

    # Renommer exactement dans ton style
    pivot_montant.columns = [
        f"{m}__{t}__{g}__montant" for m, t, g in pivot_montant.columns
    ]
    pivot_ventes.columns = [
        f"{m}__{t}__{g}__nbr_ventes" for m, t, g in pivot_ventes.columns
    ]

    wide = pd.concat([pivot_montant, pivot_ventes], axis=1).reset_index()

    print(f"  → {wide.shape[1]-1} features de ventes créées pour {len(wide)} hôtels")
    return wide


def merge_poi_weather(sales_wide: pd.DataFrame) -> pd.DataFrame:
    """Fusionne avec POI et Météo. Garde seulement les lignes complètes (inner join)."""
    print("Chargement POI et Météo...")

    poi = pd.read_excel(DATA_DIR / "poi_prepared_data.xlsx")
    weather = pd.read_excel(DATA_DIR / "weather_prepared_data.xlsx")

    # Merge sur HOTEL_NAME (comme tu fais)
    merged = sales_wide.merge(poi, on="HOTEL_NAME", how="inner")
    print(f"  Après merge POI : {len(merged)} hôtels")

    merged = merged.merge(weather, on=["HOTEL_LAT", "HOTEL_LON"], how="inner")  # ou sur HOTEL_NAME si renommé
    print(f"  Après merge Météo : {len(merged)} hôtels")

    # Si le merge sur lat/lon ne passe pas bien, fallback sur HOTEL_NAME
    if len(merged) < 5:
        print("  Merge sur lat/lon a donné peu de résultats, tentative sur HOTEL_NAME...")
        merged = sales_wide.merge(poi, on="HOTEL_NAME", how="inner")
        # weather a aussi HOTEL_NAME dans certaines versions
        if "HOTEL_NAME" in weather.columns:
            merged = merged.merge(weather.drop(columns=["HOTEL_LAT", "HOTEL_LON"], errors="ignore"),
                                  on="HOTEL_NAME", how="inner")
        else:
            merged = merged.merge(weather, left_on=["HOTEL_NAME"], right_on=["HOTEL_NAME"], how="inner")

    merged = merged.dropna(how="all", axis=1)  # nettoyage colonnes vides

    print(f"\nDataset final : {merged.shape[0]} lignes × {merged.shape[1]} colonnes")
    print("Hôtels conservés :", merged["HOTEL_NAME"].tolist())

    return merged


def main():
    print("="*60)
    print("PRÉPARATION DU DATASET ML - VENTES + POI + MÉTÉO")
    print("="*60)

    # 1. Sales features (avec filtre 2026)
    sales_wide = prepare_sales_monthly_wide(drop_2026=True)

    # 2. Merge
    final = merge_poi_weather(sales_wide)

    # 3. Sauvegarde
    output_path = DATA_DIR / "ml_training_data_prepared.xlsx"
    final.to_excel(output_path, index=False)
    print(f"\nFichier sauvegardé : {output_path}")

    # Optionnel : aussi en CSV pour le modèle
    final.to_csv(DATA_DIR / "ml_training_data_prepared.csv", index=False)
    print("Fichier CSV aussi sauvegardé.")

    # Affichage rapide des colonnes cibles (exemples)
    montant_cols = [c for c in final.columns if "__montant" in c]
    ventes_cols = [c for c in final.columns if "__nbr_ventes" in c]
    print(f"\nExemples de colonnes Chiffre d'Affaire / Montant des ventes : {montant_cols[:3]} ... ({len(montant_cols)} au total)")
    print(f"Exemples de colonnes Nombre des ventes : {ventes_cols[:3]} ... ({len(ventes_cols)} au total)")
    print("\nCes colonnes sont croisées : mois × TYPE (F&B ou NON-F&B) × GAMME (catégorie produit) × indicateur (montant ou nbr_ventes)")

    return final


if __name__ == "__main__":
    df = main()
    print("\nAperçu des 5 premières colonnes + quelques features :")
    print(df.iloc[:, :5].head())
