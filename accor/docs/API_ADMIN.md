# API Admin (port 5055)

Serveur : `accor.app` — `python run_admin.py` ou `accor-admin`.

Base URL : `http://127.0.0.1:5055`

Réponses JSON en UTF-8 (`JSON_AS_ASCII = False`). Erreurs métier typiques :
`{ "error": "…" }` avec HTTP 400 / 404.

---

## Pages

### `GET /`

SPA admin (`templates/index.html`). Charge `static/js/admin/app.js`.

### `GET /favicon.ico`

204 vide (évite le 404 console).

### `GET /api/health`

```json
{ "status": "ok", "app": "accord-data-model-studio" }
```

---

## Logos marques

### `GET /api/marques/logos/<path:relpath>`

Sert un PNG/SVG sous `data/marques/`.

Exemples d’URL :

- `/api/marques/logos/economy/ibis.png`
- `/api/marques/logos/midscale/mercure.png`

Résolution ancrée sur `PROJECT_ROOT/data/marques/`, indépendante du cwd.
404 si fichier absent. Cache navigateur 300 s.

---

## Datasets

Les `dataset_id` valides sont ceux de `schemas.DATASETS` :
`brand`, `hotel`, `proximity`, `holidays`, `weather`, `sales_raw`, `sales`,
`all_data`, `model_data`, `concept_pilote`.

### `GET /api/datasets`

Liste des onglets avec métadonnées UI (label, description, colonnes, readonly…).

```json
{ "datasets": [ { "id": "hotel", "label": "…", … }, … ] }
```

### `GET /api/datasets/<dataset_id>`

Page de lignes.

| Query | Type | Défaut | Rôle |
|-------|------|--------|------|
| `page` | int | 1 | numéro de page |
| `page_size` | int | schéma | taille page |
| `q` | str | | filtre texte toutes colonnes |

Réponse typique : `rows`, `columns`, `page`, `total`, `total_pages`,
`key_columns`, `readonly`, stats éventuelles (model_data).

### `PUT /api/datasets/<dataset_id>/rows`

Met à jour des lignes puis réécrit l’Excel.

```json
{
  "rows": [
    { "_index": 12, "hotel_code": "H0373", "hotel_nb_chambres": 120 }
  ]
}
```

`_index` = index pandas en mémoire. Seules les colonnes éditables du schéma
sont prises en compte. Datasets `readonly` → erreur.

### `POST /api/datasets/<dataset_id>/rows`

Ajoute une ligne.

```json
{ "values": { "hotel_code": "H9999", "hotel_name": "Test" } }
```

`values` optionnel (ligne quasi vide sinon).

### `DELETE /api/datasets/<dataset_id>/rows`

```json
{ "indices": [0, 3, 12] }
```

### `POST /api/datasets/<dataset_id>/reload`

Relecture Excel → invalide le cache mémoire du dataset.

---

## Rebuilds

Tous en `POST`. Peuvent être lents (météo, proximité, sales). Invalident
le cache store concerné.

### `POST /api/datasets/all_data/rebuild`  
Alias : `POST /api/datasets/data/rebuild`

Body optionnel :

```json
{ "fill_weather": false, "fill_proximity": false }
```

Construit `data/all_data.xlsx` (jointures). Invalide aussi le cache
`model_data`.

### `POST /api/datasets/model_data/rebuild`

`all_data` → `model_data.xlsx` + `model_data_meta.json` (filtre, rôles,
imputation ML).

### `POST /api/datasets/sales/rebuild`

`hotel_sales_raw_data` → `hotel_sales_data` (agrégats mensuels + mix).

### `POST /api/datasets/weather/rebuild`

Recalcule `hotel_weather_data` (Meteostat, mois terminés).

### `POST /api/datasets/proximity/rebuild`

Recalcule `hotel_proximity_data` (Overpass OSM).

### `POST /api/datasets/holidays/rebuild`

Recalcule `hotel_holidays_data` (fériés FR, vacances scolaires).

### `POST /api/datasets/concept_pilote/rebuild`

Recalcule `concept_pilote.xlsx` (hôtel × année).

---

## Modèles

### `GET /api/model/config`

Hyperparams par défaut, grilles suggérées, cible principale, dernier
modèle entraîné. Source features = `model_data`.

### `GET /api/model/list`

```json
{
  "models": [ { "id": "xgb_sales", "name": "…", "score_r2": 0.8, … } ],
  "last_trained": { … },
  "top_model": { … }
}
```

### `POST /api/model/build`

Lance un batch d’entraînement (async par défaut).

```json
{
  "model_name": "xgb_sales",
  "xgb_params": { "max_depth": 6, "n_estimators": 200, "learning_rate": 0.05 },
  "grid_search": { "max_depth": [4, 6], "learning_rate": [0.05, 0.1] },
  "main_target": "montant_ventes",
  "rank_metric": "r2",
  "async": true
}
```

Suivre : `GET /api/model/build/progress`.  
Sans async, un seul modèle (pas de grille).

### `GET /api/model/build/progress`

État du batch : jobs done/total, modèle en cours, erreurs, meilleurs scores.

### `POST /api/model/build/count`

Compte les jobs (manuel + produit cartésien grille) sans entraîner.

### `POST /api/model/deploy`

```json
{ "model_name": "xgb_sales" }
```

Copie vers `models/deploy/model.pkl` + `model.json`.

### `GET /api/model/eval/meta`

Prépare l’onglet Evaluation :

```json
{
  "ok": true,
  "target_cols": ["nombre_ventes", "montant_ventes", …],
  "main_target": "montant_ventes",
  "eval_year": 2026,
  "n_eval_rows": 20,
  "models": [ … ],
  "top_model": { … },
  "divisor_months": 12,
  "method": "…"
}
```

### `GET|POST /api/model/eval`

Évalue un modèle sur l’année incomplete.

Body ou query : `model_id`, `target`, `year`.

Métrique : par hôtel, `avg = sum(mois dispo) / 12` (prédit vs réel),
puis MAE/RMSE/R²/MAPE/biais + tables détail.

Enregistré **avant** `/api/model/<model_id>` pour ne pas capturer `eval`
comme id.

### `GET /api/model/<model_id>`

Contenu de `models/design/<id>/config.json` + chemin.

### `GET /api/model/<model_id>/explore`

Vue d’ensemble : méta, perfs train/eval, importances, n arbres.

### `GET /api/model/<model_id>/tree`

| Query | Rôle |
|-------|------|
| `target` | index de cible (défaut = principale) |
| `tree` | index d’arbre (défaut 0) |

JSON arbre pour le SVG.

### `GET /api/model/<model_id>/trees`  
### `GET /api/model/<model_id>/tree-metrics`

Table des arbres (profondeur, n features, R²/RMSE **cumulés**).

### `GET /api/model/<model_id>/importance`

Feature importance (cible principale).

---

## Exemples curl

```bash
# page hotels
curl -s 'http://127.0.0.1:5055/api/datasets/hotel?page=1&page_size=10&q=paris'

# eval
curl -s -X POST http://127.0.0.1:5055/api/model/eval \
  -H 'Content-Type: application/json' \
  -d '{"target":"montant_ventes","year":2026}'

# deploy
curl -s -X POST http://127.0.0.1:5055/api/model/deploy \
  -H 'Content-Type: application/json' \
  -d '{"model_name":"xgb_sales"}'
```
