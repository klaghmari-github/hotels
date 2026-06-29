"""
ml_xgboost_baseline.py

Remplacement de l'approche réseau de neurones dans ml.ipynb par XGBoost.

Contexte :
- 5 hôtels seulement
- ~5000+ colonnes (features POI + météo mensuelle + ROD + les 286 cibles croisées)
- Cibles : CA (montant) et nombre de ventes par mois × TYPE (F&B / NON-F&B) × GAMME

Problèmes de l'approche NN actuelle :
- N=5, p≈5000 → surapprentissage garanti
- Variables sur des échelles complètement différentes (pas de normalisation faite)
- Features très corrélées (météo mensuelle surtout)

Pourquoi XGBoost est mieux ici :
- Gère bien les données tabulaires de petite taille
- Feature importance native
- Régularisation intégrée
- Pas besoin de normalisation stricte (mais ça aide un peu)
- Moins sensible au bruit dans ce régime

ATTENTION : même avec XGBoost, avec seulement 5 échantillons il faut :
- Réduire fortement la dimensionnalité
- Utiliser beaucoup de régularisation
- Valider en Leave-One-Out
- Idéalement, ne pas prédire les 286 colonnes indépendamment (trop bruité)

Recommandation : commencer par prédire des agrégats (CA total mensuel, part F&B, etc.)
et garder le XGBoost pour apprendre les ajustements par rapport au simulateur ROD.
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import LeaveOneOut
from sklearn.preprocessing import StandardScaler
from sklearn.multioutput import MultiOutputRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from xgboost import XGBRegressor
import warnings
warnings.filterwarnings("ignore")

print("="*70)
print("ML avec XGBoost sur les données préparées (5 hôtels)")
print("="*70)

# === 1. Chargement ===
df = pd.read_excel("ml_training_data_prepared.xlsx")
print(f"\nShape : {df.shape}")

# Séparation features / targets
# Les cibles sont les colonnes croisées (montant + nbr_ventes)
target_cols = [c for c in df.columns if "__montant" in c or "__nbr_ventes" in c]
feature_cols = [c for c in df.columns if c not in target_cols and c != "HOTEL_NAME"]

X = df[feature_cols].select_dtypes(include=[np.number]).fillna(0)
y = df[target_cols].fillna(0)

print(f"Features : {X.shape[1]} colonnes")
print(f"Targets  : {y.shape[1]} colonnes (CA + ventes croisées)")

# === 2. Réduction de dimensionnalité (CRUCIAL avec N=5) ===
# La météo représente probablement des milliers de colonnes très corrélées.
# On fait une réduction simple ici (on peut raffiner plus tard).

# Gardons seulement les features "robustes" pour commencer :
# - features POI (déjà agrégées)
# - quelques stats météo de base (on va prendre la moyenne annuelle approximative)
# - features ROD (nb chambres, etc.)

# Pour l'instant, on fait une réduction agressive via variance + corrélation
print("\n[Étape 1] Réduction de dimension...")

# Supprimer les colonnes avec variance quasi nulle
variances = X.var()
X = X.loc[:, variances > 1e-6]

# On peut aussi faire un screening très simple : garder les colonnes les plus corrélées avec le target total
y_total = y[[c for c in target_cols if "__montant" in c]].sum(axis=1)
corrs = X.corrwith(y_total).abs().sort_values(ascending=False)
top_features = corrs.head(200).index.tolist()   # on garde les 200 plus corrélées (à affiner)
X_reduced = X[top_features]

print(f"Features après réduction : {X_reduced.shape[1]}")

# === 3. Modèle XGBoost (MultiOutput) ===
print("\n[Étape 2] XGBoost MultiOutput avec forte régularisation...")

# Paramètres très conservateurs pour N=5
xgb = XGBRegressor(
    n_estimators=50,
    max_depth=2,               # très faible
    learning_rate=0.05,
    reg_alpha=2.0,             # L1
    reg_lambda=2.0,            # L2
    subsample=0.8,
    colsample_bytree=0.6,
    min_child_weight=2,
    random_state=42,
    verbosity=0
)

model = MultiOutputRegressor(xgb)

# === 4. Validation Leave-One-Out (la seule qui a du sens avec 5 échantillons) ===
loo = LeaveOneOut()

all_preds = []
all_trues = []

for train_idx, test_idx in loo.split(X_reduced):
    X_train, X_test = X_reduced.iloc[train_idx], X_reduced.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    # Scaling (même si XGBoost n'en a pas absolument besoin, c'est plus stable)
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model.fit(X_train_s, y_train)
    pred = model.predict(X_test_s)

    all_preds.append(pred[0])
    all_trues.append(y_test.values[0])

all_preds = np.array(all_preds)
all_trues = np.array(all_trues)

# === 5. Évaluation sur le CA total annuel (somme de tous les montants) ===
montant_cols_idx = [i for i, c in enumerate(target_cols) if "__montant" in c]
total_ca_true = all_trues[:, montant_cols_idx].sum(axis=1)
total_ca_pred = all_preds[:, montant_cols_idx].sum(axis=1)

print("\n=== Leave-One-Out sur CA annuel total (somme de tous les montants) ===")
print("Vrai  :", np.round(total_ca_true, 0))
print("Prédit:", np.round(total_ca_pred, 0))
print(f"MAE   : {mean_absolute_error(total_ca_true, total_ca_pred):.0f}")
print(f"R2    : {r2_score(total_ca_true, total_ca_pred):.3f}")

# Feature importance globale (moyenne sur les modèles)
importances = np.mean([est.feature_importances_ for est in model.estimators_], axis=0)
feat_imp = pd.Series(importances, index=X_reduced.columns).sort_values(ascending=False)
print("\nTop 10 features les plus importantes :")
print(feat_imp.head(10))

print("\n" + "="*70)
print("CONCLUSION")
print("="*70)
print("""
Avec seulement 5 échantillons, même XGBoost sur-apprend facilement.
Les résultats ci-dessus sont probablement optimistes.

Bonnes pratiques recommandées :
1. Réduire encore plus les features (PCA sur la météo, sélection par importance, ou garder seulement les features ROD + POI résumés).
2. Ne pas prédire les 286 colonnes directement. Prédire plutôt :
   - CA total mensuel
   - Part F&B vs Non-F&B
   - Distribution des catégories (plus stable)
3. Utiliser le modèle pour prédire des AJUSTEMENTS par rapport au simulateur ROD (approche hybride), pas pour tout prédire de zéro.
4. Valider sur de nouveaux hôtels (pas seulement LOO sur les 5 pivots).

XGBoost est clairement une bien meilleure base que le réseau de neurones simple que tu avais.
""")
