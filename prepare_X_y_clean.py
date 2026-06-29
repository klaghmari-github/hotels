"""
prepare_X_y_clean.py

But : Identifier proprement les variables cibles et préparer X / y sans fuite.

Règles claires (selon tes indications) :
- Toute colonne qui contient "montant" ou "nbr_ventes" (ou "ca", "ventes") est une **variable cible**.
- Ces colonnes sont croisées : mois × TYPE (F&B / NON-F&B) × GAMME (catégorie produit).
- Pour l'entraînement et la prédiction sur nouveaux hôtels :
  → On n'utilise **jamais** ces colonnes dans les features (X).
  → On prédit uniquement ces colonnes (y).

Cela évite le "serpent qui se mord la queue".

Dataset actuel (après ton pipeline) :
- 5 hôtels
- 286 colonnes cibles (143 montant + 143 nbr_ventes)
- ~5127 colonnes features (POI + météo + ROD + lat/lon + dummies marques, etc.)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import re

DATA_DIR = Path(".")

def identify_target_columns(df: pd.DataFrame) -> list:
    """
    Identifie toutes les colonnes qui sont des variables cibles.
    Règle : contient 'montant' ou 'nbr_ventes' (insensible à la casse).
    """
    target_patterns = ['montant', 'nbr_ventes', 'ca_', 'ventes']
    target_cols = []
    
    for col in df.columns:
        col_lower = col.lower()
        if any(p in col_lower for p in target_patterns):
            target_cols.append(col)
    
    return target_cols

def clean_gamme_name(name: str) -> str:
    """Nettoie les noms de GAMME sales (ex: '#REF!' -> 'ND')."""
    if not isinstance(name, str):
        return "ND"
    name = name.strip().upper().replace(" ", "_").replace("/", "_")
    if "#REF" in name or name == "":
        return "ND"
    return name

def prepare_X_y(
    input_file: str = "ml_training_data_prepared.xlsx",
    drop_target_from_X: bool = True,
    group_targets: bool = False   # False = les 286 colonnes, True = versions agrégées plus stables
) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """
    Retourne (X, y, target_col_list)
    
    - X : uniquement les features (aucune colonne de ventes)
    - y : les variables cibles (chiffre d'affaire + nombre de ventes)
    """
    print(f"Chargement de {input_file} ...")
    df = pd.read_excel(DATA_DIR / input_file)
    
    # Nettoyage basique des noms d'hôtel
    if "HOTEL_NAME" in df.columns:
        df["HOTEL_NAME"] = df["HOTEL_NAME"].astype(str).str.strip()
    
    # 1. Identifier les cibles
    target_cols = identify_target_columns(df)
    print(f"\nNombre de colonnes cibles identifiées : {len(target_cols)}")
    
    # Afficher la structure
    print("\nStructure des cibles (exemples) :")
    for c in target_cols[:4]:
        print(f"  {c}")
    print("  ...")
    
    # 2. Séparer X et y
    if drop_target_from_X:
        X = df.drop(columns=target_cols, errors="ignore")
    else:
        X = df.copy()
    
    # Retirer HOTEL_NAME des features (pas utile pour prédiction)
    if "HOTEL_NAME" in X.columns:
        X = X.drop(columns=["HOTEL_NAME"])
    
    y = df[target_cols].copy()
    
    # 3. Nettoyage léger des noms de colonnes cibles (optionnel mais recommandé)
    y.columns = [c.replace("FOOD SALEE", "FOOD_SALEE").replace("JEUX / ENFANTS", "JEUX_ENFANTS") 
                 for c in y.columns]
    
    print(f"\nX shape (features seulement) : {X.shape}")
    print(f"y shape (cibles)            : {y.shape}")
    
    # Vérification anti-fuite
    overlap = set(X.columns) & set(target_cols)
    if overlap:
        print(f"\n⚠️  ATTENTION : {len(overlap)} colonnes cibles sont encore dans X !")
        print("   Exemples :", list(overlap)[:3])
    else:
        print("\n✅ Aucune colonne cible dans X. Pas de fuite.")
    
    # 4. Option : versions agrégées plus stables (recommandé pour commencer)
    if group_targets:
        print("\n[Option] Création de cibles agrégées plus stables...")
        
        # CA total par mois
        monthly_ca = {}
        for m in range(1, 13):
            m_str = f"m{m:02d}"
            cols = [c for c in y.columns if c.startswith(m_str) and "__montant" in c]
            monthly_ca[f"{m_str}_total_ca"] = y[cols].sum(axis=1)
        
        y_agg = pd.DataFrame(monthly_ca)
        
        # Part F&B vs Non-F&B (moyenne sur l'année)
        fb_cols = [c for c in y.columns if "F&B" in c and "__montant" in c]
        nonfb_cols = [c for c in y.columns if "NON-F&B" in c and "__montant" in c]
        
        y_agg["annual_fb_share"] = y[fb_cols].sum(axis=1) / y.sum(axis=1).replace(0, 1)
        
        print(f"  Cibles agrégées créées : {y_agg.shape[1]} (plus stables pour N=5)")
        y = y_agg   # on remplace y par la version agrégée si demandé
    
    return X, y, target_cols

def get_feature_groups(X: pd.DataFrame) -> dict:
    """Regroupe les features par catégorie pour faciliter la réduction."""
    groups = {
        "poi": [c for c in X.columns if c.startswith(("fb_", "not_fb_"))],
        "weather": [c for c in X.columns if re.match(r"m\d{2}_", c)],
        "rod": [c for c in X.columns if "etape_rod" in c or "HOTEL_" in c.upper()],
        "brand": [c for c in X.columns if c.startswith(("IBIS", "MERCURE", "NOVOTEL"))],
        "other": []
    }
    
    used = set()
    for g in groups.values():
        used.update(g)
    groups["other"] = [c for c in X.columns if c not in used]
    
    for name, cols in groups.items():
        if cols:
            print(f"  {name}: {len(cols)} colonnes")
    
    return groups

if __name__ == "__main__":
    import re   # pour le script standalone
    
    X, y, target_cols = prepare_X_y(
        input_file="ml_training_data_prepared.xlsx",
        drop_target_from_X=True,
        group_targets=False   # mets True si tu veux des cibles plus stables au début
    )
    
    print("\n=== Aperçu des features ===")
    groups = get_feature_groups(X)
    
    print("\nExemple de ligne X (premières colonnes non-weather) :")
    non_weather = [c for c in X.columns if not re.match(r"m\d{2}_", c)][:6]
    print(X[non_weather].head(2).to_string())
    
    print("\nExemple de y (premières cibles) :")
    print(y.iloc[:2, :4].to_string())
    
    # Sauvegarde propre
    X.to_csv("X_features_clean.csv", index=False)
    y.to_csv("y_targets_clean.csv", index=False)
    print("\nFichiers sauvegardés : X_features_clean.csv + y_targets_clean.csv")
    print("Prêts pour XGBoost (ou autre modèle) sans fuite de données.")
