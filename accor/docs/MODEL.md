# Modèles ML

Code : `model_data.py`, `model_train.py`, `model_explore.py`, `model_eval.py`.

---

## Données d’apprentissage

Source : `data/model_data.xlsx` (+ meta JSON).

- Features = colonnes **descriptive**  
- Targets = colonnes **target** (multi-output)  
- Split temporel : `_is_eval == 0` train, `== 1` eval (dernière année
  calendaire présente dans les données)

Imputation **uniquement** sur model_data (pas sur all_data) :
moyennes pilotes par catégorie de marque, sinon voisins, sinon 0 pour
counts/flags. Voir `impute_model` + `brand_category`.

---

## Entraînement

`model_train` :

1. Charge le frame model_data  
2. `MultiOutputRegressor(XGBRegressor(**params))`  
3. Fit sur train  
4. Métriques train + eval (par cible + agrégat)  
5. Sauve `models/design/<slug>/model.pkl` + `config.json`  

UI batch :

- job manuel (params saisis)  
- + grille (produit cartésien dédupliqué)  
- progression : `BuildProgress` / `GET /api/model/build/progress`  

Ranking des modèles : souvent R² (ou RMSE/MAE) sur la **cible principale**
`montant_ventes`.

### Deploy

`deploy_model(id)` → copie vers `models/deploy/` (un seul modèle déployé
à la fois).

---

## Exploration

`model_explore` :

- overview (perfs, n arbres, importances)  
- table arbres avec métriques **cumulées** après k arbres  
  (en boosting un arbre isolé n’est pas une prédiction de la cible)  
- dump arbre JSON → SVG (`tree-svg.js`)  

---

## Évaluation année incomplete

`model_eval` — cas 2026 (ou `eval_year` meta) avec mois partiels.

Pour chaque hôtel :

```
avg_monthly_true = sum(y_true sur mois présents) / 12
avg_monthly_pred = sum(y_pred sur les mêmes mois) / 12
```

Diviseur **toujours 12** (référentiel « mensuel moyen annuel »), pas le
nombre de mois disponibles.

Puis :

- métriques globales sur les moyennes hôtel (MAE, RMSE, R², MAPE, biais)  
- métriques mois à mois (secondaires)  
- tables détail hôtel + mois  

Cible sélectionnable (défaut = principale).

API : `/api/model/eval/meta`, `/api/model/eval`  
UI : onglet Evaluation  

---

## Bundle pickle

Contenu typique du `model.pkl` :

```python
{
  "model": MultiOutputRegressor(...),
  "feature_cols": [...],
  "target_cols": [...],
  # éventuellement name, metrics…
}
```

`load_design_model` lit aussi `config.json` à côté.

---

## Warnings version

Unpickle d’un modèle entraîné avec une ancienne sklearn/xgboost peut
émettre des warnings. En général la prédiction marche ; pour un état
propre : ré-entraîner + redéployer.
