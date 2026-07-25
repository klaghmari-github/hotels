# Accor · Data & Model Studio

Application web **self-contained** pour :

1. **Éditer** les données hôtels Accor (Excel sous `data/`) en mode WYSIWYG paginé  
2. **Assembler** une table All Data (jointure multi-sources)  
3. **Préparer** un dataset d’apprentissage (`model_data`)  
4. **Entraîner** des modèles XGBoost (dossier `models/design/`)  
5. **Explorer** les arbres / importances / performances  
6. **Déployer** un modèle unique pour l’application (`models/deploy/`)

> Ce dépôt `accord/` est l’application **nouvelle**.  
> Le dossier `../archive/` (pipelines prepare historiques, sources brutes, etc.) n’est **pas** requis au runtime, sauf scripts utilitaires d’extraction ponctuelle (ex. coûts).

---

## Démarrage rapide

```bash
cd accord

# Environnement recommandé (ex. venv du monorepo)
# source ../archive/.venv/bin/activate   # optionnel

pip install -r requirements.txt

# Admin — données + model build
python run_admin.py
# → http://127.0.0.1:5055

# User — wizard directeur + simulateur ROD
python run_user.py
# → http://127.0.0.1:5056
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `--host` | `127.0.0.1` | Adresse d’écoute |
| `--port` | `5055` admin / `5056` user | Port HTTP |
| `--debug` | off | Mode debug Flask |

### Deux interfaces

| Entrée | Rôle |
|--------|------|
| **`run_admin.py`** | Saisie / rebuild datasets, jointures, Model Build / Explore / Deploy |
| **`run_user.py`** | Wizard directeur (identité, services, clients, corner) → enrichissement → **revenus ROD** + **coûts** (séparés) → marge → recommandation SIMPLY / LIBERTY / CONNECTED |

Le moteur de **revenus** et le moteur de **coûts** sont volontairement découplés (`user/rules/revenue.py` vs `user/rules/costs.py`) : une future étape IA pourra remplacer uniquement les revenus.

---

## Architecture

```
accord/
├── run_admin.py           # CLI admin → app.main()
├── run_user.py            # CLI user  → user.app.main()
├── app.py                 # Routes Flask admin (pages + API)
├── schemas.py             # Schémas des onglets / fichiers Excel
├── store.py               # Cache, pagination, lecture/écriture Excel
├── join_data.py           # Jointure All Data + fill nulls numériques
├── geo_weather.py         # Météo depuis lat/lon (Meteostat)
├── geo_proximity.py       # Proximité OSM (Overpass)
├── model_data.py          # Construction model_data.xlsx + méta rôles
├── model_train.py         # Entraînement XGBoost → design/ + deploy/
├── model_explore.py       # Analyse arbres, importances, perfs
├── extract_couts.py       # Extraction one-shot des grilles de coûts ROD
├── sync_data_files.py     # Aligne les Excel data/ sur les schémas UI
├── user/                  # Simulateur directeur (POO)
│   ├── app.py             # Flask user API + wizard
│   ├── models.py          # Request / résultats
│   ├── reference.py       # rod_reference.json
│   ├── rules/             # revenue · costs · recommendation
│   └── services/          # catalog, geocode, enrich, orchestrator
├── requirements.txt
├── data/                  # Excel métier + rod_reference.json
├── models/
│   ├── design/<nom>/      # Modèles entraînés (model.pkl + config.json)
│   ├── deploy/            # Un seul modèle actif (model.pkl + model.json)
│   └── last_trained.json  # Pointeur dernier entraînement
├── templates/
│   ├── index.html         # Shell UI admin
│   └── user/index.html    # Wizard ROD
└── static/
    ├── css/app.css · js/app.js
    └── user/css · user/js
```

### Flux de données

```
hotel_data / brand / weather / sales / holidays
        │
        ▼  [All Data → Reconstruire]
   all_data.xlsx          (grille hotel × année × mois)
        │
        ▼  [Model Data → Reconstruire]
   model_data.xlsx        (hôtels avec ventes, rôles id/desc/cible)
        │
        ▼  [Model Build → Build & Save]
   models/design/<nom>/   (pickle + config)
        │
        ▼  [Model Explore → Deploy]
   models/deploy/model.*  (modèle unique de production)
```

---

## Onglets données

| Onglet | Fichier | Éditable | Notes |
|--------|---------|----------|-------|
| Hotel Brand Data | `hotel_brand_data.xlsx` | Oui | Marques + logos + `cat_*` (0/1) + effectifs `Nb_*` à saisir |

### Nulls / moyennes

| Fichier | Trous manquants |
|---------|-----------------|
| Sources (`hotel_data`, brand, sales, …) | **Laissés vides** (saisie ultérieure) |
| `all_data.xlsx` | **Laissés vides** après jointure |
| `model_data.xlsx` | **Imputés** : moyenne marque puis globale (TO, météo…) ; 0 pour counts/ventes |

```bash
# Retirer d'anciennes moyennes injectées dans hotel_data
python -m clean_source_fills
# Puis reconstruire
# (UI : Reconstruire All Data puis Model Data)
```

Sync marques → brand data :

```bash
cd accord
python -m sync_brand_data          # enrichit depuis data/marques/marques.xlsx
```
| Hotel Data | `hotel_data.xlsx` | Oui | Parc Accor scrape (identité, GPS, flags) + profils saisis |

```bash
# Remplir hotel_data depuis hotels_all (~tous les hôtels scrapés)
python -m sync_hotel_data
```
| Hotel Weather Data | `hotel_weather_data.xlsx` | Oui | Météo mensuelle |
| Hotel Proximity Data | `hotel_proximity_data.xlsx` | Oui | Commerces 100–500 m + plage 1–5 km |
| Hotel Sales Data | `hotel_sales_data.xlsx` | Oui | Ventes + mix % (sans fériés) |
| Hotel Holidays Data | `hotel_holidays_data.xlsx` | Oui | Fériés / vacances + listes de jours |
| **All Data** | `all_data.xlsx` | Oui | Jointure complète |
| **Model Data** | `model_data.xlsx` | **Lecture seule** | Dataset ML dérivé |

### All Data

- Grille **parfaite** : chaque hôtel (`hotel_data`) × chaque année pertinente × 12 mois  
- Jointure left des ventes, holidays, weather, brand  
- **Null numériques → 0** après jointure (mois sans ventes, etc.)  
- **Recharger** : relit le fichier sans recalculer  
- **Reconstruire** : `POST /api/datasets/all_data/rebuild`  

### Model Data

Construit depuis `all_data` avec les règles suivantes :

1. **Uniquement** les hôtels ayant au moins une vente > 0  
2. Suppression des colonnes **constantes**  
3. Colonnes en 3 rôles (couleurs d’en-tête) :

| Rôle | Couleur UI | Contenu |
|------|------------|---------|
| **id_detail** | Jaune / or | Code, nom, marque, adresse, ville, lat/lon, année, mois, zone… |
| **descriptive** | Neutre | Météo, équipements, brand stats, **mix saisi** : `pct_*_nombre_ventes` cat/sous-cat, `pct_categories_mois_*`, `nombre_categories_mois_*` |
| **target** | Vert | Volumes (`nombre_ventes`, `montant_ventes`, …) + **autres pct ventes** (montant, paniers, produits) |

4. Ordre des colonnes : id → descriptives → cibles  
5. Tri : année → mois → marque → hôtel  
6. **Dernière année = évaluation** (lignes en gras) ; le reste = train  
7. Stats sous la table : n ID, n desc, n cibles, n train, n éval  

**Cible principale** pour le scoring des modèles : `montant_ventes`.

---

## Model Build

- Source **fixe** : `model_data`  
- Features = **toutes** les colonnes descriptives  
- Split = train (années < max) / éval (année max)  
- UI : nom du modèle + hyperparamètres XGBoost  
- **Build & Save** →  
  - `models/design/<nom>/model.pkl`  
  - `models/design/<nom>/config.json`  
  - Écrase si le même nom existe  
  - Met à jour `models/last_trained.json`  

Hyperparamètres exposés : `n_estimators`, `max_depth`, `learning_rate`, `subsample`, `colsample_bytree`, `min_child_weight`, `reg_alpha`, `reg_lambda`, `gamma`, `random_state`.

---

## Model Explore

- Liste des modèles `design/` **triée par performance** (R² sur `montant_ventes` en éval)  
- Bannière : **dernier entraîné** / **top model**  
- Changement de modèle → **toutes** les zones se rechargent (perf, importance, table d’arbres, visualisation)  
- Table des arbres : profondeur, n features distinctes, R²/RMSE **cumulés** (boosting XGBoost)  
- Slider : visualise un arbre (SVG)  
- **Recharger** : rafraîchit la liste et l’UI  
- **Deploy** : copie le modèle sélectionné vers  
  - `models/deploy/model.pkl`  
  - `models/deploy/model.json`  
  (un seul modèle déployé à la fois)

> Note XGBoost : un arbre isolé prédit un **résidu** (correctif), pas la cible absolue.  
> La perf affichée par arbre est donc **cumulative** après *k* arbres.

---

## Coûts (`couts.xlsx`)

Grilles de coûts ROD extraites (valeurs calculées) :

| Feuille | Contenu |
|---------|---------|
| `resume` | Synthèse par solution (simply / liberty / connected) |
| `couts_technos` | Matériel, licences, frais ad hoc |
| `couts_annexes` | Électricité + personnel |
| `couts_agencement` | m linéaires × classic / premium / bespoke |
| `revenus_mix_marges` | Mix F&B / N-F&B et marges |
| `revenus_impact_to` | Impact TO / CA pilotes |
| `meta` | Source et notes |

Régénération (nécessite le fichier source sous `../archive/sources/raw/`) :

```bash
python extract_couts.py
```

---

## API HTTP

### Santé & datasets

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/health` | Sonde |
| GET | `/api/datasets` | Liste des onglets + schémas |
| GET | `/api/datasets/<id>?page=&page_size=&q=` | Page de lignes |
| PUT | `/api/datasets/<id>/rows` | Mise à jour lignes (`_index`) |
| POST | `/api/datasets/<id>/rows` | Ajout ligne |
| DELETE | `/api/datasets/<id>/rows` | Suppression (`indices`) |
| POST | `/api/datasets/<id>/reload` | Invalide le cache, relit le Excel |

### Jointures / dérivés

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/api/datasets/all_data/rebuild` | Jointure → `all_data.xlsx` |
| POST | `/api/datasets/model_data/rebuild` | `all_data` → `model_data.xlsx` |

### Modèles

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/model/config` | Hyperparams + stats model_data + dernier modèle |
| GET | `/api/model/list` | Modèles design triés + last/top |
| POST | `/api/model/build` | Entraîne + sauve design (`model_name`, `xgb_params`) |
| POST | `/api/model/deploy` | Copie design → deploy (`model_name`) |
| GET | `/api/model/<id>` | Config JSON d’un modèle |
| GET | `/api/model/<id>/explore` | Vue d’ensemble (importances, perfs) |
| GET | `/api/model/<id>/trees` | Table des arbres (cible principale) |
| GET | `/api/model/<id>/tree?tree=0` | Structure d’un arbre (JSON) |
| GET | `/api/model/<id>/importance` | Feature importance |

---

## Modules Python (rôle)

| Module | Rôle |
|--------|------|
| `schemas.py` | `DatasetSchema` + registre `DATASETS` (colonnes éditables, clés, readonly) |
| `store.py` | Cache thread-safe, pagination, coercion types, projection schéma ↔ Excel |
| `join_data.py` | Grille hotel×année×mois, merges anti-doublons, fill météo/proximité, `fill_numeric_nulls` |
| `geo_weather.py` | Meteostat 2.x : stations proches + agrégats mensuels → `hotel_weather_data` |
| `geo_proximity.py` | Overpass : commerces 100–500 m / plage 1–5 km → `hotel_proximity_data.xlsx` (load or compute) |
| `geo_holidays.py` | Assure `hotel_holidays_data.xlsx` (fichier local, archive, ou grille minimale) |
| `model_data.py` | Filtre hôtels, rôles id/desc/cible, split année éval |
| `model_train.py` | XGB multi-output, design/, deploy/, last_trained |
| `model_explore.py` | Parse dump XGBoost, profondeur, features, perfs cumulées |
| `extract_couts.py` | Parse grilles simulateur ROD → `couts.xlsx` |
| `sync_data_files.py` | Réécrit les Excel pour coller aux colonnes UI |

---

## UI (front)

- **Sidebar** : onglets datasets + Model Build + Model Explore  
- **Tables** : inputs par cellule, dirty map, Ctrl+S pour sauver  
- **Model Data** : en-têtes colorés (id / desc / cible), lignes d’éval en gras  
- **Thème** : sombre (navy + or), polices DM Sans / Instrument Serif  

Fichiers : `templates/index.html`, `static/js/app.js`, `static/css/app.css`.

---

## Scripts utiles

```bash
# Aligner tous les Excel data/ sur les schémas + rebuild all_data
python sync_data_files.py

# Reconstruire uniquement model_data (via Python)
python -c "from model_data import rebuild_model_data; print(rebuild_model_data())"

# Extraire les coûts ROD
python extract_couts.py
```

---

## Dépendances

Voir `requirements.txt` :

- Flask, pandas, openpyxl  
- requests, meteostat (météo optionnelle au rebuild)  
- scikit-learn, xgboost, numpy (ML)

---

## Conventions

- Identité hôtel = **code Accor** (`hotel_code`), pas les slugs/noms seuls  
- Les fichiers sous `data/` sont la source de vérité éditable  
- `model_data` et `all_data` sont **dérivés** (boutons Reconstruire)  
- Les modèles d’exploration vivent dans `models/design/` ; la prod dans `models/deploy/`  

---

## Licence / contexte

Projet interne d’analyse et de simulation retail / corner pour hôtels Accor (ROD).  
L’archive historique (`../archive/`) conserve les pipelines de préparation de données d’origine.
