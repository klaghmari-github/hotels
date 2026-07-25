# Synthèse exhaustive — `accord/`

> Application active **Data & Model Studio** + **simulateur user ROD**.  
> Dossier exploré : `/media/laghmari/ssd-data/dev/hotels/accord/`  
> Date d’analyse : 2026-07-25.

---

## 1. Rôle global d’`accord/`

`accord/` est l’**application nouvelle** du monorepo hotels, self-contained, destinée à l’analyse et à la simulation retail / corner pour hôtels Accor (projet **ROD**).

Elle couvre deux parcours distincts :

| Parcours | Entrée | Port | Rôle |
|----------|--------|------|------|
| **Admin** | `run_admin.py` → `app.main()` | **5055** | Édition WYSIWYG des Excel `data/`, rebuild des datasets dérivés, construction / exploration / déploiement de modèles XGBoost |
| **User** | `run_user.py` → `user.app.main()` | **5056** | Wizard directeur + simulateur multi-concepts (SIMPLY / LIBERTY / CONNECTED) : revenus ROD + coûts séparés → marge → recommandation |

Fonctionnalités admin (chaîne complète) :

1. Éditer les données hôtels Accor (Excel sous `data/`) en mode table paginée.
2. Assembler **All Data** (jointure multi-sources, grille hotel × année × mois).
3. Préparer **model_data** (dataset ML avec rôles id / descriptive / target).
4. Entraîner des modèles **XGBoost** dans `models/design/`.
5. Explorer arbres, importances, performances cumulées.
6. Déployer un unique modèle actif dans `models/deploy/`.

Le dossier `../archive/` (pipelines historiques, sources brutes, API FastAPI legacy) n’est **pas** requis au runtime, sauf utilitaires ponctuels (extraction coûts, import CSV ventes si raw manquant).

---

## 2. Architecture (run_admin vs run_user, ports, Flask apps)

### 2.1 Vue d’ensemble

```
accord/
├── run_admin.py           # CLI admin → app.main()  → :5055
├── run_user.py            # CLI user  → user.app.main() → :5056
├── app.py                 # Flask admin (pages + API datasets / models)
├── schemas.py             # Schémas onglets / colonnes Excel
├── store.py               # Cache thread-safe, pagination, CRUD Excel
├── join_data.py           # All Data
├── sales_prep.py          # raw → sales mensuel
├── geo_common.py          # Hôtels / années / mois terminés
├── geo_weather.py         # Meteostat
├── geo_proximity.py       # Overpass OSM
├── geo_holidays.py        # Fériés FR + vacances zones A/B/C
├── model_data.py          # model_data.xlsx + méta
├── model_train.py         # Build design + deploy
├── model_explore.py       # Arbres / importance / perfs
├── concept_pilote.py      # Agrégats annuels hôtel
├── extract_couts.py       # One-shot grilles coûts → couts.xlsx
├── sync_data_files.py     # Alignement Excel ↔ schémas UI
├── user/                  # Simulateur directeur (POO)
│   ├── app.py
│   ├── models.py
│   ├── reference.py
│   ├── rules/             # revenue · costs · recommendation · coeffs
│   └── services/          # catalog, geocode, enrich, orchestrator…
├── data/                  # Excel métier + JSON référence
├── models/
│   ├── design/<nom>/      # model.pkl + config.json
│   ├── deploy/            # model.pkl + model.json (unique)
│   └── last_trained.json
├── templates/             # index.html admin + user/index.html
└── static/                # css/js admin + user/
```

### 2.2 Deux applications Flask

| | Admin (`app.py`) | User (`user/app.py`) |
|--|------------------|----------------------|
| Templates | `templates/` | `templates/user/` |
| Static | `static/` | `static/user/` (`/static/user`) |
| Port défaut | 5055 | 5056 |
| Host défaut | 127.0.0.1 | 127.0.0.1 |
| Options CLI | `--host`, `--port`, `--debug` | idem |

### 2.3 Couches

- **Présentation** : HTML + JS (sidebar, tables dirty/Ctrl+S, Model Build/Explore, wizard multi-étapes user).
- **API HTTP** : Flask, JSON `JSON_AS_ASCII=False` (accents hôtels).
- **Persistance** : fichiers Excel `data/*.xlsx` (source de vérité éditable) + `rod_reference.json` + pickles modèles.
- **Métier data** : modules `sales_prep`, `geo_*`, `join_data`, `model_*`, `concept_pilote`.
- **Métier simulation** : `user/rules/*` + `user/services/orchestrator.py` (indépendant de XGBoost aujourd’hui).

### 2.4 Dépendances (`requirements.txt`)

- Web : Flask ≥ 3
- Data : pandas, openpyxl, numpy
- Géo (optionnel au rebuild) : requests, meteostat
- ML : scikit-learn, xgboost

---

## 3. Inventaire des fichiers `.py` importants

### 3.1 Racine `accord/`

| Fichier | Rôle |
|---------|------|
| **`run_admin.py`** | Point d’entrée CLI admin. Délègue à `app.main()` sans logique métier. |
| **`run_user.py`** | Point d’entrée CLI user. Délègue à `user.app.main()` (wizard + simulateur ROD). |
| **`app.py`** | Serveur Flask admin : page unique, CRUD datasets, rebuild (sales/weather/proximity/holidays/all_data/model_data/concept_pilote), API Model Build / Explore / Deploy. |
| **`schemas.py`** | Déclare `DatasetSchema` et le registre `DATASETS` (ordre sidebar = ordre d’insertion). Colonnes éditables, clés, booléens, arrays, readonly. |
| **`store.py`** | Cache mémoire thread-safe (`RLock`), pagination/filtre `q`, coercion types, projection schéma, write Excel. Cas spéciaux all_data (fill nulls) et model_data (roles + `_is_eval`). |
| **`join_data.py`** | Construit `all_data.xlsx` : grille parfaite hotel×année×mois, merges left anti-doublons (`_merge_new`), fill weather/proximity optionnels, `fill_numeric_nulls` (numériques → 0). |
| **`sales_prep.py`** | Pipeline ventes brutes → mensuel : matching boutique→`hotel_code`, TYPE/GAMME → f_b/n_f_b + sous-cat, agrégats + mix %, split holidays via listes de jours. |
| **`geo_common.py`** | Utilitaires partagés rebuilds : charge hotels/sales, années de ventes, mois terminés uniquement (mois courant exclu). |
| **`geo_weather.py`** | `WeatherFromGeo` (Meteostat 2.x, fallback 1.x) : stations proches, agrégats mensuels mean/min/max, imputation mois N←N-1. Rebuild → `hotel_weather_data.xlsx`. |
| **`geo_proximity.py`** | `ProximityFromGeo` (Overpass) : commerces 100–500 m par catégorie OSM, plage 1–5 km. Load-or-build `hotel_proximity_data.xlsx`. |
| **`geo_holidays.py`** | Fériés légaux FR (Pâques Meeus), vacances scolaires zones A/B/C (repères), union exclusive holidays. Zones **binaires** `zone_scolaire_a/b/c` (pas de colonne texte A/B/C en schéma UI). |
| **`model_data.py`** | Filtre hôtels avec ventes, drop constantes / arrays, rôles id_detail / descriptive / target, split dernière année = eval, écrit `model_data.xlsx` + `model_data_meta.json`. |
| **`model_train.py`** | XGB multi-output (`MultiOutputRegressor`), hyperparams UI, save design/, deploy/, `last_trained.json`. Score ranking = R² `montant_ventes` en éval. |
| **`model_explore.py`** | Parse dump arbres XGBoost, profondeur, features distinctes, perfs **cumulées** (boosting), importance, JSON pour SVG UI. |
| **`concept_pilote.py`** | Agrégats **annuels** hotel×année : clients (chambres×TO×guests marque), CA mensuel moyen, mix produits distincts F&B/N-F&B (raw prioritaire). API user : moyennes marque étape 1. |
| **`extract_couts.py`** | One-shot : lit le xlsx simulateur ROD sous `archive/sources/raw/`, extrait valeurs calculées (openpyxl `data_only`) → `data/couts.xlsx` (feuilles resume, technos, annexes, agencement, revenus…). |
| **`sync_data_files.py`** | Maintenance hors UI : réécrit les Excel éditables pour coller aux `editable_columns`, rebuild all_data hors-ligne (sans fill réseau par défaut). |

### 3.2 Package `user/`

| Fichier | Rôle |
|---------|------|
| **`user/__init__.py`** | Doc package v1.0.0 ; annonce le swap IA futur sur les seuls revenus. |
| **`user/app.py`** | Flask user : meta, brands, hotels, context, geocode, enrich, simulate. Port 5056. |
| **`user/models.py`** | Dataclasses / structures : `HotelIdentity`, `HotelOperating`, services, profil clients, corner, `SimulationRequest`, résultats revenus/coûts/concept/full. |
| **`user/reference.py`** | Charge `data/rod_reference.json` (constantes pilotes Excel par concept). |
| **`user/rules/coeffs.py`** | Coefficients Règle 3 F&B / N-F&B, baselines, mapping marques, besoins LIBERTY lifestyle, libellés UI. |
| **`user/rules/revenue.py`** | Moteur **revenus** déterministe : impact TO, R1 clients, R2 mix, R3 catégories, R4 m_lin, marge produit. Sans coûts. |
| **`user/rules/costs.py`** | Moteur **coûts** indépendant : techno / annexes / agencement (lignes `cost_lines` ou agrégats fallback). |
| **`user/rules/recommendation.py`** | Règles d’admissibilité (taille <50 → SIMPLY only ; N-F&B lifestyle → LIBERTY) puis meilleure marge nette. |
| **`user/rules/__init__.py`** | Export `RevenueRules`, `CostRules`, `RecommendationRules`. |
| **`user/services/catalog.py`** | Lecture seule `hotel_brand_data` / `hotel_data` / stats model_data pour préremplir le wizard. |
| **`user/services/geocode.py`** | Nominatim multi-stratégies (structuré, libre, hotel_name), throttle ~1 req/s, normalisation CP. |
| **`user/services/enrich.py`** | Enrichissement one-shot : géocode → proximity Overpass → weather Meteostat → holidays (pour un hôtel saisi). |
| **`user/services/hotel_context.py`** | Agrège hotel_data + model_data → indicateurs d’entrée ROD (chambres, TO, guests, mix, m_lin, client_needs, CA historique). |
| **`user/services/simulator.py`** | Un concept : revenus + coûts → marge nette, ROI. Source `ROD_RULES`. |
| **`user/services/orchestrator.py`** | Pipeline complet : hydrate admin → enrich → simule 3 concepts → reco. Point d’entrée `POST /api/simulate`. |
| **`user/services/__init__.py`** | Export `SimulationOrchestrator`. |

### 3.3 Front (non-Python, pour contexte)

| Chemin | Rôle |
|--------|------|
| `templates/index.html` + `static/js/app.js` + `static/css/app.css` | Shell admin (thème sombre navy/or). |
| `templates/user/index.html` + `static/user/js/user.js` + `css/user.css` | Wizard directeur multi-étapes. |

---

## 4. Datasets Excel sous `accord/data/`

| Fichier | Grain | Source / provenance | Rebuild ? |
|---------|-------|---------------------|-----------|
| **`hotel_brand_data.xlsx`** | 1 ligne / marque | Saisie admin (effectifs `Nb_*` chambres, restos, bars) | Non (éditable) |
| **`hotel_data.xlsx`** | 1 ligne / hôtel | Saisie admin (identité, équipements, profil clients, corner, contrat) | Non (éditable) |
| **`hotel_sales_raw_data.xlsx`** | 1 ligne / ticket produit | Import / saisie ; bootstrap possible depuis `archive/.../001.queryVentes.csv` via `ensure_raw_sales_from_archive` | Non (éditable) ; base du rebuild sales |
| **`hotel_sales_data.xlsx`** | hôtel × année × mois | **Dérivé** : `sales_prep.rebuild_hotel_sales_data` depuis raw + holidays | **Oui** — `POST /api/datasets/sales/rebuild` (readonly UI) |
| **`hotel_holidays_data.xlsx`** | hôtel × année × mois | **Dérivé** : fériés FR + vacances scolaires ; zones binaires | **Oui** — `POST /api/datasets/holidays/rebuild` |
| **`hotel_weather_data.xlsx`** | hôtel × année × mois | **Dérivé** : Meteostat via lat/lon (mois terminés) | **Oui** — weather/rebuild ; éditable pour correction manuelle |
| **`hotel_proximity_data.xlsx`** | 1 ligne / hôtel | **Dérivé** : Overpass commerces + plage | **Oui** — proximity/rebuild |
| **`all_data.xlsx`** | hôtel × année × mois (grille complète) | **Dérivé** : jointure multi-sources | **Oui** — all_data/rebuild |
| **`model_data.xlsx`** | sous-ensemble all_data (hôtels avec ventes) | **Dérivé** : filtres + rôles ML | **Oui** — model_data/rebuild (readonly) |
| **`model_data_meta.json`** | méta colonnes / train-eval | Écrit avec model_data | Avec rebuild model_data |
| **`concept_pilote.xlsx`** | hôtel × année | **Dérivé** : hotel_data + sales (+ raw pour mix produits) | **Oui** — concept_pilote/rebuild (readonly) |
| **`couts.xlsx`** | grilles multi-feuilles | **Dérivé one-shot** : extract_couts depuis archive Excel simulateur | `python extract_couts.py` (hors UI) |
| **`rod_reference.json`** | constantes pilotes | Extrait Excel simulateur ROD (concepts SIMPLY/LIBERTY/CONNECTED, impact TO, cost_lines) | Manuel / extraction amont |

### Notes de grain

- **Mensuel** : sales, holidays, weather, all_data, model_data — clé `(hotel_code, annee, mois)`.
- **Hôtel** : hotel_data, proximity.
- **Marque** : brand.
- **Ticket** : sales_raw.
- **Annuel** : concept_pilote — clé `(hotel_code, annee)`.

---

## 5. Pipeline données

```
                    archive CSV (optionnel)
                           │
                           ▼
              hotel_sales_raw_data.xlsx
                           │
              sales_prep + hotel_data (match)
              + hotel_holidays (jours)
                           │
                           ▼
               hotel_sales_data.xlsx
                     │
     ┌───────────────┼───────────────────────────────┐
     │               │                               │
     ▼               ▼                               ▼
hotel_weather    hotel_holidays               hotel_proximity
 (Meteostat)      (calendrier FR)               (Overpass)
     │               │                               │
     └───────┬───────┴───────────────┬───────────────┘
             │                       │
             │   hotel_data + brand  │
             ▼                       ▼
                    all_data.xlsx
              (grille hotel × année × mois
               left joins + nulls num → 0)
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
  model_data.xlsx          concept_pilote.xlsx
  (hôtels avec ventes,     (hotel × année :
   rôles id/desc/cible,     clients, CA moyen,
   dernière année = eval)   mix produits)
         │
         ▼
  models/design/<nom>/
         │ Deploy
         ▼
  models/deploy/model.*
```

### 5.1 Étapes détaillées

1. **Raw sales → sales** (`sales_prep.py`)
   - Normalisation colonnes (français / slugs).
   - Matching flou `nom_boutique` → `hotel_code` via `hotel_name`.
   - TYPE → `f_b` / `n_f_b` ; GAMME → sous-cat (sans_alcool, food_salee, etc.).
   - Agrégation mensuelle : `nombre_ventes`, `montant_ventes`, `nombre_paniers`, `nombre_produits`, mix cat/sous-cat en %.
   - `attach_holiday_sales` : croise tickets avec listes `jours_holidays` pour split holidays / hors holidays.

2. **Holidays / weather / proximity** (rebuilds indépendants, mois **terminés** uniquement pour weather/holidays)
   - Hôtels = `hotel_data` ; années = présentes dans sales.
   - Holidays : fériés + weekend + vacances ; `nb_jours_holidays` = union exclusive ; zones `zone_scolaire_a|b|c` en 0/1.
   - Weather : mean/min/max pour temp, humidité, précipitations, etc.
   - Proximity : comptages commerces par rayon + flags plage.

3. **all_data** (`join_data.build_joined_dataframe`)
   - Grille complète : chaque hôtel × chaque année collectée × 12 mois.
   - Left join sales, holidays, weather (clés mensuelles) ; proximity (clé hôtel) ; fiche hotel ; brand sur `hotel_brand`.
   - Fill optionnel météo/proximité si trous (`fill_weather` / `fill_proximity`, souvent false en sync offline).
   - **`fill_numeric_nulls`** : NaN numériques → 0 ; textes nuls → `""` ; listes jours → `[]`.

4. **model_data** (`model_data.build_model_dataframe`)
   - Uniquement hôtels avec au moins une vente > 0.
   - Drop arrays de jours, colonnes constantes.
   - Rôles : id_detail (jaune), descriptive (features), target (vert, dont `montant_ventes` = cible principale).
   - Mix **nombre de ventes** cat/sous-cat = descriptive ; autres pct (montant, paniers…) = target.
   - Dernière année = évaluation (`_is_eval=1`, gras UI).

5. **concept_pilote** (`concept_pilote.rebuild_concept_pilote`)
   - Pour chaque hôtel × année de ventes : clients_jour/mois depuis chambres × TO × guests marque ; CA mensuel moyen ; n produits distincts F&B / N-F&B (raw prioritaire).
   - Consommé par l’UI user (moyennes marque étape 1, hors année la plus récente).

6. **Modèle** : train sur descriptive → multi-target ; design → deploy.

---

## 6. Schémas / onglets UI admin (ordre sidebar)

Ordre **réel** = insertion dans `schemas.DATASETS` (alimente `GET /api/datasets` et la sidebar) :

| # | id API | Label UI | Fichier | Éditable |
|---|--------|----------|---------|----------|
| 1 | `brand` | Hotel Brand Data | `hotel_brand_data.xlsx` | Oui |
| 2 | `hotel` | Hotel Data | `hotel_data.xlsx` | Oui |
| 3 | `holidays` | Hotel Holidays Data | `hotel_holidays_data.xlsx` | Oui |
| 4 | `sales_raw` | Hotel Sales Raw Data | `hotel_sales_raw_data.xlsx` | Oui |
| 5 | `sales` | Hotel Sales Data | `hotel_sales_data.xlsx` | **Readonly** (rebuild depuis raw) |
| 6 | `weather` | Hotel Weather Data | `hotel_weather_data.xlsx` | Oui (+ rebuild) |
| 7 | `proximity` | Hotel Proximity Data | `hotel_proximity_data.xlsx` | Oui (+ rebuild) |
| 8 | `all_data` | All Data | `all_data.xlsx` | Oui (toutes colonnes ; rebuild jointure) |
| 9 | `model_data` | Model Data | `model_data.xlsx` | **Readonly** |
| 10 | `concept_pilote` | Concept Pilote | `concept_pilote.xlsx` | **Readonly** |

Puis hors registre datasets (JS admin) :

- **Model Build**
- **Model Explore**

> **Écart doc** : le commentaire dans `schemas.py` annonce « Concept pilote → Model Data », mais le dict place **model_data avant concept_pilote**. Le README admin ne liste pas encore `sales_raw` ni `concept_pilote` dans le tableau des onglets.

### Rebuilds exposés par l’API admin

| Route | Action |
|-------|--------|
| `POST /api/datasets/sales/rebuild` | raw → sales (+ holidays split) |
| `POST /api/datasets/weather/rebuild` | Meteostat |
| `POST /api/datasets/proximity/rebuild` | Overpass |
| `POST /api/datasets/holidays/rebuild` | calendrier |
| `POST /api/datasets/all_data/rebuild` | jointure (body : fill_weather, fill_proximity) |
| `POST /api/datasets/model_data/rebuild` | all_data → model_data |
| `POST /api/datasets/concept_pilote/rebuild` | agrégats annuels |
| `POST /api/datasets/<id>/reload` | invalide cache, relit Excel |

### Model API

| Route | Rôle |
|-------|------|
| `GET /api/model/config` | hyperparams + stats model_data |
| `GET /api/model/list` | design triés + last/top |
| `POST /api/model/build` | train + save design |
| `POST /api/model/deploy` | design → deploy |
| `GET /api/model/<id>/explore|trees|tree|importance` | exploration |

---

## 7. Module `user/` — revenus vs coûts, orchestrateur, géocode

### 7.1 Principe de séparation ROD

Les moteurs **revenus** et **coûts** sont **volontairement découplés** :

- `user/rules/revenue.py` — CA HT, ventes, marge produit (règles Excel SIMULATEUR).
- `user/rules/costs.py` — techno / annexes / agencement (stable si swap IA).
- `user/services/simulator.py` — agrège : marge nette = marge produit − coûts ; ROI capex.

Objectif documenté : une future étape **IA** remplace uniquement les revenus ; les coûts et la reco restent.

### 7.2 Parcours wizard / API

1. **Identité** : code Accor, marque, adresse, lat/lon (ou géocode).
2. **Exploitation** : chambres, TO, guests/chambre → clients/jour = n×TO×guests ; clients/mois = × 30.5.
3. **Services** lobby / F&B / non-F&B.
4. **Profil clients** : loisirs/affaires, national/international, besoins catégories (Règle 3).
5. **Corner** : m_lin, mix F&B, offre existante.
6. **Enrichissement** (optionnel light) : géocode + holidays (+ weather/proximity si non light).
7. **Simulation** multi-concepts + recommandation.

### 7.3 Orchestrateur (`SimulationOrchestrator`)

Séquence `simulate_all` :

1. `prepare_request` : si `hotel_code`, hydrate depuis `HotelContextBuilder` (hotel_data + model_data) ; garde-fous (80 ch, 70 % TO, guests 1.7).
2. `FeatureEnricher.enrich` (light = skip Overpass/Meteostat).
3. `RecommendationRules.allowed_concepts` (filtres taille / N-F&B).
4. Pour chaque concept ∈ {SIMPLY, LIBERTY, CONNECTED} : `build_store` (m_lin, mix) + `RodSimulator.simulate`.
5. `recommend` : meilleure **marge nette annuelle** parmi les concepts autorisés.

### 7.4 Règles revenus (chaîne Excel)

1. Base CA pilote F&B / N-F&B depuis `rod_reference.json`.
2. **Impact TO** (ht par point de TO).
3. **Règle 1** : scale clients_hôtel / clients_pilote.
4. **Règle 2** : écart de mix par pas de 10 %.
5. **Règle 3** : delta cumul coeffs besoins clients vs baseline.
6. **Règle 4** : écart mètres linéaires vs pivot concept.
7. Marge produit : CA − CA/coef (coefs pilote).

### 7.5 Règles coûts

- Lignes `cost_lines.techno` / `annexes` : monthly_unit × qty, ou capex amorti.
- Agencement : capex_per_m × m_lin / amort_months.
- Fallback agrégats `techno_monthly` / `annexes_monthly` si lignes absentes.

### 7.6 Recommandation

| Règle | Effet |
|-------|--------|
| #1 taille | `< 50` chambres → **SIMPLY seul** |
| #2 N-F&B lifestyle | au moins un besoin cosmétiques/kids/apparel/accessoires/souvenirs → ouvre **LIBERTY** |
| SIMPLY + IBB | IBB &lt; 200 ch peut garder SIMPLY dans le panier |
| Choix final | max marge nette parmi autorisés |

### 7.7 Géocode (`Geocoder`)

- Endpoint Nominatim OSM.
- Stratégies successives : adresse structurée → texte libre « rue, CP, ville, France » → `q` / `hotel_name`.
- Normalisation CP 4 chiffres → 5 (`06200`).
- Throttle ≥ 1.1 s ; réponse 200 même en échec métier (`ok: false`) pour l’UI.

### 7.8 Lien admin → user

- Marques / hôtels lus depuis les mêmes Excel admin.
- `concept_pilote` alimente les moyennes marque étape 1 (exclut l’année la plus récente).
- `model_data` fournit mix historique, client_needs (seuil 1 %), CA de contrôle — **pas** le CA projeté (qui reste pilote `rod_reference`).

**Important** : le simulateur user **n’utilise pas** encore `models/deploy/` (XGBoost). Source affichée : `ROD_RULES`.

---

## 8. Models XGBoost — design / deploy

### 8.1 Organisation fichiers

```
models/
├── design/
│   ├── xgb_sales/     # model.pkl + config.json
│   ├── xgb_sales_1/
│   └── xgb_sales_2/   # (exemple de variantes entraînées)
├── deploy/
│   ├── model.pkl      # unique modèle « prod »
│   └── model.json     # méta (features, targets, metrics, eval_year…)
└── last_trained.json  # pointeur dernier build UI
```

État observé (2026-07) :

- Deploy pointe vers une config issue de **xgb_sales_2** (eval_year 2026, ~240 lignes, 180 train / 60 eval).
- `last_trained.json` référence **xgb_sales_1**.

### 8.2 Build (`model_train.py`)

- Source **fixe** : `model_data`.
- Features = colonnes **descriptive** (méta).
- Targets = colonnes **target** (volumes + pct non-mix).
- Split temporel : `_is_eval=0` train / `1` éval (dernière année).
- Un `XGBRegressor` par cible via `MultiOutputRegressor`.
- Hyperparams exposés : `n_estimators`, `max_depth`, `learning_rate`, `subsample`, `colsample_bytree`, `min_child_weight`, `reg_alpha`, `reg_lambda`, `gamma`, `random_state` (+ defaults `objective=reg:squarederror`, `tree_method=hist`).
- **Build & Save** → `models/design/<slug>/` (écrase même nom) + maj `last_trained.json`.
- Métriques : RMSE, MAE, R² par cible et moyennes.

### 8.3 Explore (`model_explore.py`)

- Liste design triée par R² sur **`montant_ventes`** (éval), puis mean_r2.
- Bannière last_trained / top model.
- Table d’arbres : profondeur, n features distinctes, R²/RMSE **cumulés** après k arbres (pas perf d’un arbre isolé — correctif de boosting).
- Dump XGBoost parsé en arbre JSON pour visualisation SVG.
- Feature importance sur la cible principale.

### 8.4 Deploy

- Copie le dossier design sélectionné vers `models/deploy/model.pkl` + `model.json`.
- Un seul modèle déployé à la fois.
- Consommateur runtime prévu : future IA revenus / API prédiction — **pas encore branché sur le wizard user**.

---

## 9. Points clés de conception

| Thème | Règle / choix |
|-------|----------------|
| **Identité hôtel** | Toujours **`hotel_code`** Accor (pas slug/nom seul). Matching sales raw via nom boutique → code. |
| **Source de vérité** | Excel sous `data/` éditables ; `all_data` / `model_data` / `sales` / `concept_pilote` = **dérivés** (boutons Reconstruire). |
| **Format tabulaire** | Tables paginées, inputs cellule, dirty map, Ctrl+S ; arrays de dates en JSON dans Excel. |
| **Nulls numériques → 0** | `fill_numeric_nulls` en fin de jointure All Data (et re-fill à la lecture Excel). Mesures sans ventes = 0, pas NaN ML. |
| **Textes / listes** | Non forcés en 0 : codes, adresses, `jours_*` → `""` ou `[]`. |
| **Anti-doublons merge** | `_merge_new` n’ajoute que les colonnes absentes (pas de suffixes `_x/_y`). |
| **Grille parfaite** | All Data : hotel_data × années × 12 mois même sans ventes. |
| **Mois en cours** | Exclu des rebuilds weather/holidays (`geo_common.months_for_year`). |
| **Zone scolaire** | **Binaires** `zone_scolaire_a`, `_b`, `_c` dans le schéma UI ; colonne texte A/B/C **retirée** du schéma (interne geo_holidays peut encore dériver une lettre pour calcul). |
| **Mix ML** | Seuls les `% en nombre de ventes` cat/sous-cat = features ; pct montant/paniers/produits = **cibles**. |
| **Cible ranking** | `montant_ventes`. |
| **Split temporel** | Dernière année = holdout (ex. 2026). |
| **Revenus vs coûts user** | Modules séparés pour swap IA partiel. |
| **CA projeté vs historique** | Projection = pilotes `rod_reference` ; CA model_data = contrôle / contexte. |
| **Self-contained** | Runtime sans archive sauf bootstrap raw / extract_couts. |
| **Thread-safety store** | `RLock` sur cache + écritures concurrentes Flask. |
| **Self-contained geo** | Meteostat / Overpass / Nominatim : appels réseau optionnels, non bloquants (warnings). |

---

## 10. Limitations / travaux en cours

1. **IA revenus non branchée**  
   Le modèle XGBoost deploy n’alimente pas le simulateur user. Les docstrings annoncent un remplacement futur de `RevenueRules` uniquement.

2. **Écart README / schémas**  
   README sidebar incomplet (pas sales_raw, concept_pilote) ; ordre commenté concept_pilote ≠ ordre `DATASETS` réel.

3. **Dépendance archive ponctuelle**  
   - `extract_couts.py` nécessite le xlsx sous `archive/sources/raw/`.  
   - `ensure_raw_sales_from_archive` importe le CSV si raw manquant.  
   - `sync_data_files` peut retomber sur SalesPrep archive pour sales.

4. **Vacances scolaires approximatives**  
   Périodes zones A/B/C encodées pour années récentes (repères MEN) ; années hors couverture → compteurs 0 / incomplete.

5. **Overpass / Meteostat / Nominatim**  
   Lents, rate-limités, offline-unfriendly. Rebuild all_data désactive souvent fill réseau ; mode user `light=1` skip proximity/weather.

6. **Matching boutique**  
   Flou nom boutique → hôtel : risque d’unmatched ou faux positifs ; `drop_unmatched=True` par défaut au rebuild sales.

7. **Model multi-output**  
   Nombreuses cibles (volumes + nombreux pct) : entraînement lourd ; colonnes constantes droppées dynamiquement → features varient selon les données.

8. **concept_pilote vs model_data**  
   Concept pilote non intégré dans le pipeline ML (à côté pour UI user / reco métier) ; ordre sidebar après model_data.

9. **couts.xlsx vs rod_reference.json**  
   Deux artefacts de coûts : grilles Excel d’audit (`couts.xlsx`) vs JSON runtime (`rod_reference.json`). Le user lit le JSON, pas couts.xlsx.

10. **Pas de tests unitaires sous `accord/`**  
    Les tests historiques restent dans `archive/tests/` ; l’app active n’a pas de suite de tests dédiée visible dans le dossier.

11. **Deploy vs last_trained**  
    Peuvent diverger (deploy = xgb_sales_2, last_trained = xgb_sales_1) : pas de contrainte de cohérence auto.

12. **Formule Excel extract_couts**  
    `data_only=True` nécessite un cache de formules déjà calculé (ouverture Excel/LibreOffice préalable).

---

## Annexe A — API user (rappel)

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/api/health` | Sonde + concepts chargés |
| GET | `/api/meta` | Concepts, besoins clients, défauts |
| GET | `/api/brands` | Marques admin |
| GET | `/api/hotels` | Liste hôtels |
| GET | `/api/hotels/<code>` | Fiche |
| GET | `/api/hotels/<code>/context` | Contexte wizard + payload simulateur |
| GET | `/api/concept_pilote/brand/<brand>` | Moyennes exploitation marque (étape 1) |
| POST | `/api/geocode` | Adresse → lat/lon |
| POST | `/api/enrich` | Features géo one-shot |
| POST | `/api/simulate` | Simulation complète (`?light=1` recommandé UI) |

---

## Annexe B — Flux de données résumé (une ligne)

`sales_raw` → `sales` (+ holidays)  ∪  `weather` ∪ `proximity` ∪ `hotel` ∪ `brand` → **`all_data`** → **`model_data`** → **XGB design/deploy** ; parallèle **`concept_pilote`** + **`rod_reference`** → **simulateur user ROD**.

---

*Fin de la synthèse `accord/`.*
