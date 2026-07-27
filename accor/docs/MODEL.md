# Modèles ML

Code : `model_data.py`, `model_train.py`, `model_final.py`, `model_explore.py`,
`model_eval.py`.

## Architecture à deux étages

| Zone UI | Rôle | Stockage |
|---------|------|----------|
| **Modèles intermédiaires** | Multi-output XGB (toutes cibles) | `models/design/` |
| **Modèle final** | Stacking enrichi → `montant_ventes` | `models/final/design/` |

Chaque zone a **Build · Explore · Évaluation** (évaluations **séparées**).

```
model_data (descriptives + cibles)
        │
        ▼
┌───────────────────────────┐
│  Modèles intermédiaires   │  MultiOutput XGB
│  models/design/           │  pred_toutes_cibles
└───────────┬───────────────┘
            │ pred_* sur train + eval
            ▼
┌───────────────────────────┐
│  Modèle final             │  X = descriptives + pred_*
│  models/final/design/     │  y = montant_ventes
└───────────────────────────┘
```

Ce n’est **pas** un meta-model sur les preds seules : les variables
descriptives restent dans X, aux côtés des `pred_*`.

---

## Données d’apprentissage

Source : `data/model_data.xlsx` (+ meta JSON).

- Features = colonnes **descriptive**  
- Targets = colonnes **target** (multi-output)  
- Split temporel : `_is_eval == 0` train, `== 1` eval (dernière année)

Imputation **uniquement** sur model_data (pas sur all_data) :
moyennes pilotes par catégorie de marque, sinon voisins, sinon 0.
Voir `impute_model` + `brand_category`.

Cible principale de ranking : `montant_ventes` (`MAIN_TARGET`).

---

## Étape 1 — Modèles intermédiaires

`model_train` :

1. Charge model_data  
2. `MultiOutputRegressor(XGBRegressor(**params))`  
3. Fit train  
4. Métriques train + eval (par cible + agrégat)  
5. Sauve `models/design/<slug>/model.pkl` + `config.json`  

UI : **Modèles intermédiaires → Build / Explore / Évaluation**.  
API : `/api/model/build`, `/api/model/list`, `/api/model/<id>/…`,
`/api/model/eval?tier=intermediate`.

Ranking : R² / RMSE / MAE sur `montant_ventes`.

Deploy intermédiaire : `deploy_model` → `models/deploy/`.

---

## Étape 2 — Modèle final (stacking enrichi)

`model_final` :

1. Charger un intermédiaire multi-output (top ou choisi)  
2. Prédire **toutes** les cibles sur model_data → `pred_<cible>`  
3. Features finales = **descriptives + toutes les pred_***  
4. Fit XGB **mono-cible** sur `montant_ventes`  
5. Sauve `models/final/design/<slug>/`  

UI : **Modèle final → Build / Explore / Évaluation**.  
API : `/api/model/final/config|list|build|…`,
`/api/model/eval?tier=final`.

Deploy final : `deploy_final_model` → `models/final/deploy/`.

---

## Exploration

`model_explore` (paramètre `tier=intermediate|final`) :

- overview (perfs, n arbres, importances)  
- table arbres avec métriques **cumulées** après k arbres  
- dump arbre JSON → SVG (`tree-svg.js`)  

Pour le final, les features d’eval reconstituent le stacking
(intermédiaire + `pred_*`).

---

## Évaluation ML (année incomplete)

`model_eval` — **uniquement XGBoost** (pas le Simulateur ROD).

Deux onglets UI distincts :

| Onglet | `tier` | Modèles listés |
|--------|--------|----------------|
| Intermédiaires → Évaluation | `intermediate` | `models/design` |
| Final → Évaluation | `final` | `models/final/design` |

Cas 2026 (ou `eval_year`) avec mois partiels, **par hôtel** :

```
avg_monthly_true = sum(y_true sur mois présents) / 12
avg_monthly_pred = sum(y_pred sur les mêmes mois) / 12
```

Diviseur **toujours 12**. Puis MAE, RMSE, R², MAPE, biais + tables hôtel / mois.

API : `GET /api/model/eval/meta?tier=…`, `POST /api/model/eval` body
`{ model_id, target, year, tier }`.

---

## Bundle pickle

**Intermédiaire** :

```python
{
  "model": MultiOutputRegressor(...),
  "feature_cols": [...],
  "target_cols": [...],
}
```

**Final** :

```python
{
  "model": XGBRegressor(...),
  "feature_cols": [...],          # descriptives + pred_*
  "base_feature_cols": [...],
  "pred_feature_cols": [...],
  "target_cols": ["montant_ventes"],
  "intermediate_model_id": "...",
  "tier": "final",
}
```

---

## Roadmap — ML vs simulateur ROD (même 2026)

Aujourd’hui :

* **Éval intermédiaire / final** : pred XGBoost vs réel (Σ/12)  
* **Simulateur ROD** : estimation règles Excel vs réel (Σ/12)  

**Plus tard** : même hôtel / même 2026 — comparer **pred ML** (final de
préférence) et **sim ROD** face au réel. Voir [ROD_ADMIN.md](ROD_ADMIN.md).
