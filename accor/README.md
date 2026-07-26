# Accor ROD

Deux applications Flask qui partagent le même package Python `accor` et les
mêmes fichiers sous `data/` / `models/` :

| App | Port | Rôle |
|-----|------|------|
| **Admin** — Data & Model Studio | 5055 | éditer les Excel, (re)construire les tables dérivées, entraîner / explorer / évaluer / déployer le modèle |
| **User** — simulateur directeur | 5056 | parcours ROD : hôtel → concept (SIMPLY / LIBERTY / CONNECTED) → CA, coûts, reco |

Le code vit dans `src/accor/` (package installable). Les données et le front
restent à la racine du projet (`data/`, `models/`, `static/`, `templates/`).

L’archive plus complète (pipelines bulk historiques) est à côté :
`../accor_1_0_0/`. Ici on est en mode **prod** : données déjà construites,
rebuilds lourds peu exposés dans l’UI, scrape hôtel **à la demande** quand un
code n’est pas encore en base.

---

## Table des matières

1. [Prérequis et installation](#1-prérequis-et-installation)
2. [Lancer les apps](#2-lancer-les-apps)
3. [Arborescence](#3-arborescence)
4. [Chemins runtime](#4-chemins-runtime)
5. [Données (`data/`)](#5-données-data)
6. [Pipeline des tables](#6-pipeline-des-tables)
7. [Modèles (`models/`)](#7-modèles-models)
8. [Interface admin](#8-interface-admin)
9. [API admin](#9-api-admin)
10. [Interface user (simulateur)](#10-interface-user-simulateur)
11. [API user](#11-api-user)
12. [Règles ROD (revenus, coûts, reco)](#12-règles-rod-revenus-coûts-reco)
13. [Imputation et catégories de marque](#13-imputation-et-catégories-de-marque)
14. [Scrape Accor](#14-scrape-accor)
15. [Front (JS / CSS)](#15-front-js--css)
16. [Tests et validations](#16-tests-et-validations)
17. [Commandes utiles](#17-commandes-utiles)
18. [Dépannage](#18-dépannage)
19. [Où trouver quoi dans le code](#19-où-trouver-quoi-dans-le-code)

---

## 1. Prérequis et installation

- Python **3.10+**
- Accès lecture/écriture sur `data/` et `models/`
- Connexion réseau seulement si tu scrapes un hôtel ou si tu relances météo /
  proximité (Overpass / Meteostat)

```bash
cd accor

python3 -m venv .venv
source .venv/bin/activate

pip install -U pip setuptools wheel
pip install -e .

# contrôle rapide
python -c "import accor; print(accor.__version__, accor.DATA_DIR)"
accor-validate-rod
```

`pip install -e .` installe le package en mode éditable : toute modification
sous `src/accor/` est prise en compte sans réinstaller (redémarrer Flask
suffit pour le serveur).

Dépendances principales (voir `pyproject.toml` / `requirements.txt`) :
Flask, pandas, openpyxl, numpy, scikit-learn, xgboost, requests, meteostat.

---

## 2. Lancer les apps

```bash
source .venv/bin/activate

# Admin → http://127.0.0.1:5055
python run_admin.py
# ou
accor-admin

# User → http://127.0.0.1:5056
python run_user.py
# ou
accor-user
```

Options courantes :

```bash
python run_admin.py --host 0.0.0.0 --port 5055 --debug
python run_user.py  --host 0.0.0.0 --port 5056
```

Les deux apps peuvent tourner en même temps. Elles lisent les mêmes Excel ;
en écriture, évite de rebuild admin pendant qu’un directeur simule (cache
mémoire côté store).

---

## 3. Arborescence

```
accor/
  pyproject.toml          # package + entry points
  requirements.txt
  run_admin.py            # thin wrapper → accor.app:main
  run_user.py             # thin wrapper → accor.user.app:main
  README.md

  data/                   # Excel + JSON de référence (runtime)
    hotel_data.xlsx
    hotel_brand_data.xlsx
    hotel_sales_raw_data.xlsx
    hotel_sales_data.xlsx
    hotel_weather_data.xlsx
    hotel_proximity_data.xlsx
    hotel_holidays_data.xlsx
    all_data.xlsx
    model_data.xlsx
    model_data_meta.json
    concept_pilote.xlsx
    couts.xlsx
    rod_reference.json
    marques/              # logos PNG par catégorie + marques.xlsx

  models/
    design/<id>/          # model.pkl + config.json (essais d’entraînement)
    deploy/               # modèle servi par le simulateur
    last_trained.json

  static/
    css/app.css           # admin
    js/admin/             # modules ES admin
    shared/js/            # api, dom, toast, format, loading
    user/                 # css + modules ES user
    img/

  templates/
    index.html            # admin SPA
    user/index.html       # wizard directeur

  src/accor/              # PACKAGE Python
    __init__.py           # version + chemins réexportés
    data_io.py            # chemins, lecture Excel, normalisations
    schemas.py            # définition des onglets admin
    store.py              # cache DataFrame + CRUD paginé
    join_data.py          # all_data
    sales_prep.py         # raw → ventes mensuelles
    model_data.py         # all_data → model_data
    impute_model.py       # trous pour le ML uniquement
    brand_category.py     # catégories marque + moyennes pilotes
    model_train.py        # XGBoost multi-output
    model_explore.py      # arbres, importance, perfs
    model_eval.py         # eval année incomplete (moyenne /12)
    model_explore.py
    concept_pilote.py
    geo_common.py
    geo_weather.py
    geo_proximity.py
    geo_holidays.py
    app.py                # Flask admin
    scrape_accor/         # scrape fiche hôtel unitaire
    user/                 # simulateur
      app.py
      models.py
      reference.py
      validate_rod.py
      rules/              # revenue, costs, recommendation, coeffs
      services/           # catalog, geocode, enrich, hotel_*, simulator, orchestrator
```

---

## 4. Chemins runtime

Tout part de `src/accor/data_io.py` :

| Constante | Résolution |
|-----------|------------|
| `PACKAGE_DIR` | `src/accor/` |
| `PROJECT_ROOT` | dossier projet (`…/hotels/accor`) = `PACKAGE_DIR.parent.parent` |
| `DATA_DIR` | `PROJECT_ROOT/data` |
| `MODELS_DIR` | `PROJECT_ROOT/models` |
| `STATIC_DIR` | `PROJECT_ROOT/static` |
| `TEMPLATES_DIR` | `PROJECT_ROOT/templates` |

Peu importe d’où tu lances Python (`cd` ailleurs, IDE, entry point) : les
chemins restent ancrés sur le package, pas sur le cwd.

```python
from accor import DATA_DIR, MODELS_DIR, __version__
from accor.data_io import read_excel, normalize_hotel_code_value
```

---

## 5. Données (`data/`)

### Fichiers sources (saisissables / alimentés en amont)

| Fichier | Grain | Contenu |
|---------|-------|---------|
| `hotel_brand_data.xlsx` | marque | stats réseau, dummies `cat_*`, logos |
| `hotel_data.xlsx` | hôtel | fiche (adresse, GPS, chambres, TO, équipements, corner…) |
| `hotel_sales_raw_data.xlsx` | ligne de ticket | export caisse / boutique |
| `hotel_weather_data.xlsx` | hôtel × an × mois | agrégats météo |
| `hotel_proximity_data.xlsx` | hôtel | commerces OSM par rayon, plage |
| `hotel_holidays_data.xlsx` | hôtel × an × mois | fériés, vacances scolaires, weekends |
| `couts.xlsx` | ref | barèmes coûts (complété par `rod_reference.json`) |
| `rod_reference.json` | ref | concepts, lignes de coûts, coefs Excel pour le simu |
| `marques/` | assets | PNG + éventuellement `marques.xlsx` |

### Fichiers dérivés

| Fichier | Produit par | Grain |
|---------|-------------|-------|
| `hotel_sales_data.xlsx` | `sales_prep` | hôtel × an × mois (+ mix %) |
| `all_data.xlsx` | `join_data` | même grain, jointures large |
| `model_data.xlsx` + `_meta.json` | `model_data` | filtré, rôles colonnes, imputé ML |
| `concept_pilote.xlsx` | `concept_pilote` | hôtel × année (indicateurs pilotes) |

### Onglets admin ↔ schéma

Chaque onglet est déclaré dans `schemas.DATASETS` (`id`, fichier, feuille,
colonnes éditables, `readonly`, etc.). Persistance via `store.py`.

Onglets typiques : brand, hotel, proximity, holidays, weather, sales_raw,
sales, all_data, model_data, concept_pilote.

`all_data` et `model_data` exposent toutes les colonnes du fichier ;
`model_data` est en lecture seule dans l’UI (rebuild seulement).

---

## 6. Pipeline des tables

Ordre logique (même si en prod la plupart des fichiers sont déjà là) :

```
hotel_sales_raw_data
        │  sales_prep
        ▼
hotel_sales_data  ──┬── holidays / weather / proximity (geo_*)
                    │
hotel_data ─────────┤
hotel_brand_data ───┤  join_data
                    ▼
               all_data
                    │  model_data (+ impute_model)
                    ▼
               model_data  ──► model_train ──► models/design
                    │                              │
                    │                              ▼ deploy
                    │                         models/deploy
                    └── concept_pilote (indicateurs annuels)
```

### Jointure `all_data` (`join_data.py`)

- Table de gauche = **ventes mensuelles** : une ligne par
  `(hotel_code, annee, mois)` où il y a eu de l’activité.
- Left joins : holidays, weather (même clé mois), hotel + proximity (code
  hôtel), brand (marque).
- Les nulls sont **conservés** ici. On n’impute pas encore.

### `model_data` (`model_data.py`)

1. Part de `all_data`.
2. Jette les hôtels sans aucune vente positive.
3. Classe les colonnes : **id_detail** / **descriptive** / **target**.
4. Dernière année calendaire → `_is_eval = 1` (hold-out temporel).
5. Imputation **uniquement** pour le ML (`impute_model`).
6. Cible principale de ranking : `montant_ventes`.

Mix « saisi directeur » côté features : pourcentages en **nombre de ventes**
(pas tous les pct montant). Le reste des pct ventes part en cibles.

### Ventes (`sales_prep.py`)

Raw → lignes nettoyées (`prepare_lines`) → agrégats mensuels + mix
catégories / sous-catégories → attache éventuelle holidays → Excel.

### Concept pilote (`concept_pilote.py`)

Grain `hotel_code × annee` : chambres, TO, clients/jour-mois, CA mensuel
moyen, mix produits distincts F&B / non-F&B. Sert de référence au simu et
à l’UI user (marque).

---

## 7. Modèles (`models/`)

### Entraînement (`model_train.py`)

- Features = colonnes descriptives (meta `model_data`).
- Targets = multi-output (volumes + pct cibles).
- Split temporel : `_is_eval == 0` train, `== 1` eval.
- Un `XGBRegressor` par cible via `MultiOutputRegressor`.
- Sortie : `models/design/<slug>/model.pkl` + `config.json`.
- Batch UI : jobs manuels + grille d’hyperparams (`GridSearchPlanner`),
  progression lue par le front (`BuildProgress`).

### Deploy

Copie le modèle choisi vers `models/deploy/` (`model.pkl` + `model.json`).
C’est celui que le parcours user / enrichissement peut consommer.

### Explore (`model_explore.py`)

- Vue d’ensemble, importances, perfs train/eval.
- Table des arbres : métriques **cumulées** après k arbres (en boosting un
  arbre seul n’est pas une prédiction de la cible).
- Dump arbre JSON pour le SVG côté admin.

### Evaluation année incomplete (`model_eval.py`)

Cas métier : l’année d’eval (souvent **2026**) n’a que quelques mois.

Pour chaque hôtel :

```
somme_reelle  = Σ y_true  sur les mois présents
somme_predite = Σ y_pred  sur les mêmes mois
moyenne_mensuelle = somme / 12
```

On divise **toujours par 12**, pas par le nombre de mois disponibles : le
référentiel reste « revenu mensuel moyen = annuel / 12 ».

Ensuite MAE, RMSE, R², MAPE, biais sur ces moyennes hôtel, plus le détail
mois à mois. Cible au choix (défaut = cible principale).

API : `GET /api/model/eval/meta`, `POST /api/model/eval`.

---

## 8. Interface admin

Page unique : `templates/index.html` + modules sous `static/js/admin/`.

### Barre latérale

- Datasets (brand, hotel, sales, all_data, model_data, …) — table paginée,
  recherche, édition cellulaire si non `readonly`.
- **Model Build** — lancer un entraînement / grille, suivre la progression.
- **Model Explore** — perfs, importance, arbres.
- **Evaluation** — perf sur l’année incomplete, cible sélectionnable.

### Comportement table

- Pagination + filtre texte.
- Dirty state : cases modifiées, sauvegarde batch (`PUT …/rows`).
- Lignes `_is_eval` en évidence sur model_data.
- Logos marque via `/api/marques/logos/…`.
- Boutons rebuild : selon l’onglet (sales, weather, all_data, model_data,
  concept…). En prod, certains rebuilds bulk sont masqués ou déconseillés
  si les Excel sont figés.

### Evaluation (détail UI)

Paramètres : modèle design, variable cible, année.  
Métriques sur moyenne mensuelle / hôtel, totaux Σ, tables hôtel et mois.

---

## 9. API admin

Base : `http://127.0.0.1:5055`

### Santé / pages

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/` | SPA admin |
| GET | `/api/health` | ping |
| GET | `/api/marques/logos/<path>` | PNG marque |

### Datasets

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/api/datasets` | liste des schémas |
| GET | `/api/datasets/<id>` | page (query: page, page_size, q) |
| PUT | `/api/datasets/<id>/rows` | maj cellules dirty |
| POST | `/api/datasets/<id>/rows` | ajout ligne |
| DELETE | `/api/datasets/<id>/rows` | suppression |
| POST | `/api/datasets/<id>/reload` | relecture Excel |

### Rebuilds

| Méthode | Chemin |
|---------|--------|
| POST | `/api/datasets/all_data/rebuild` |
| POST | `/api/datasets/model_data/rebuild` |
| POST | `/api/datasets/sales/rebuild` |
| POST | `/api/datasets/weather/rebuild` |
| POST | `/api/datasets/proximity/rebuild` |
| POST | `/api/datasets/holidays/rebuild` |
| POST | `/api/datasets/concept_pilote/rebuild` |

### Modèles

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/api/model/config` | config build |
| GET | `/api/model/list` | modèles design |
| POST | `/api/model/build` | lance un batch |
| GET | `/api/model/build/progress` | avancement |
| POST | `/api/model/build/count` | estime le nb de jobs grille |
| POST | `/api/model/deploy` | body: model_id |
| GET | `/api/model/eval/meta` | cibles, modèles, année défaut |
| GET/POST | `/api/model/eval` | lance l’évaluation |
| GET | `/api/model/<id>` | détail config |
| GET | `/api/model/<id>/explore` | overview |
| GET | `/api/model/<id>/tree` | un arbre (query) |
| GET | `/api/model/<id>/trees` | table arbres |
| GET | `/api/model/<id>/tree-metrics` | perfs cumulées |
| GET | `/api/model/<id>/importance` | importances |

**Attention** : les routes `/api/model/eval*` sont enregistrées **avant**
`/api/model/<model_id>` pour que `eval` ne soit pas pris pour un id.

Exemple eval :

```bash
curl -s -X POST http://127.0.0.1:5055/api/model/eval \
  -H 'Content-Type: application/json' \
  -d '{"target":"montant_ventes","year":2026}'
```

---

## 10. Interface user (simulateur)

Wizard directeur : `templates/user/index.html` + `static/user/js/modules/`.

Parcours typique :

1. Recherche / saisie code hôtel (si absent de `hotel_data` → scrape
   unitaire possible via `hotel_fetch`).
2. Contexte : fiche, concept pilote marque, géocode si besoin.
3. Profil clients / besoins, mètres linéaires, options store.
4. Simulation multi-concepts → tableaux CA, coûts, marge.
5. Recommandation (règles taille / lifestyle / meilleure marge nette).

Front OOP : `UserApp`, panels (stepper, hotel-context, simulation, …),
helpers partagés (`shared/js`).

---

## 11. API user

Base : `http://127.0.0.1:5056`

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/` | wizard |
| GET | `/api/health` | ping |
| GET | `/api/meta` | labels, besoins clients, meta UI |
| GET | `/api/brands` | marques connues |
| GET | `/api/concept_pilote/brand/<marque>` | indicateurs pilotes |
| GET | `/api/hotels` | liste courte |
| GET | `/api/hotels/search` | recherche (q) |
| GET | `/api/hotels/<code>` | fiche |
| GET | `/api/hotels/<code>/context` | contexte simu (peut scraper) |
| POST | `/api/geocode` | adresse → lat/lon |
| POST | `/api/enrich` | features manquantes |
| POST | `/api/rule1` | preview règle clients |
| POST | `/api/simulate` | simulation complète multi-concepts |

Le corps de `/api/simulate` suit `user.models.SimulationRequest` (identité,
exploitation, profil client, store, options).

---

## 12. Règles ROD (revenus, coûts, reco)

Package `accor.user.rules` — volontairement découpé pour pouvoir un jour
remplacer le moteur de **revenus** sans toucher aux **coûts**.

### Revenus (`revenue.py`)

Enchaînement calqué sur l’Excel simulateur :

1. Impact TO sur le CA F&B / non-F&B  
2. **Règle 1** — ratio clients hôtel / clients pilote  
3. **Règle 2** — mix  
4. **Règle 3** — coefficients par catégorie (F&B / N-F&B)  
5. **Règle 4** — mètres linéaires  
6. Marge produit (coefs type Excel)

### Coûts (`costs.py`)

Lignes techno / annexes / agencement depuis `rod_reference.json`
(`concepts.{C}.cost_lines`). Capex + opex mensuel ligne à ligne.
Les tarifs unitaires CONNECTED (ex. frigo) ne doivent pas être double-comptés
avec une quantité déjà portée ailleurs.

### Recommandation (`recommendation.py`)

- Taille : &lt; 50 chambres → plutôt SIMPLY ; ≥ 50 → LIBERTY / CONNECTED  
- Certaines catégories N-F&B « lifestyle » ouvrent le chemin LIBERTY  
- Parmi les concepts autorisés : meilleure marge nette  

### Orchestration (`services/orchestrator.py`)

`SimulationOrchestrator` : hydrate le contexte hôtel → enrichit → simule
chaque concept via `RodSimulator` → applique la reco.

Référence chargée une fois : `user.reference.RodReference` lit
`data/rod_reference.json`.

---

## 13. Imputation et catégories de marque

### Où on impute

**Uniquement** dans `model_data` (et chemins prediction qui s’en servent).
Les sources (`hotel_data`, sales, all_data) gardent les trous visibles.

### Logique (`impute_model` + `brand_category`)

Catégories : `economy`, `midscale`, `premium`, `luxury`,
`lifestyle_by_ennismore`, `partner_brands`.

Pour une moyenne numérique manquante :

1. Moyenne des **hôtels pilotes** (présents dans les ventes) de la **même**
   catégorie de marque.
2. Sinon moyenne des pilotes des catégories **directement** inférieure et
   supérieure (échelle economy → luxury ; lifestyle / partner ont des
   voisins dédiés).
3. Sinon moyenne tous pilotes, puis globale, puis 0.

Comptages, flags, montants de vente manquants → **0** (pas de moyenne).

---

## 14. Scrape Accor

En prod le package ne garde que le scrape **unitaire** utile au user :

- `scrape_accor.hotels` — fiche `/hotel/{code}/index.fr.shtml`
- `scrape_accor.http_util` — fetch HTTP
- `user.services.hotel_fetch` — normalise le code, scrape, upsert
  `hotel_data.xlsx`, invalide les caches

Les orchestrateurs bulk (plages d’IDs, world scrape, etc.) sont dans
l’archive `accor_1_0_0` si besoin de reconstituer un parc massif.

Respect du site : pauses entre requêtes, User-Agent identifiable, pas de
rafale inutile depuis le parcours directeur (un hôtel à la fois).

---

## 15. Front (JS / CSS)

### Principes

- Modules ES (`type="module"`), pas de bundler.
- Couche **shared** : `api.js` (fetch JSON + erreurs), `dom.js`, `toast.js`,
  `format.js`, `loading.js`.
- Admin et user ont chacun leur `App` + panels.

### Admin (`static/js/admin/`)

| Fichier | Rôle |
|---------|------|
| `app.js` | `AdminApp`, wiring global |
| `state.js` | datasets, page, dirty, panel courant |
| `nav-controller.js` | sidebar + bascule des vues |
| `table-renderer.js` | rendu table + édition |
| `dataset-controller.js` | fetch page, save, rebuild |
| `model-build-panel.js` | entraînement |
| `model-explore-panel.js` | exploration |
| `model-eval-panel.js` | évaluation 2026 / cible |
| `tree-svg.js` | dessin arbre XGB |
| `constants.js` | icônes, datasets pinés |

Debug navigateur : `window.AccorAdmin`.

### User (`static/user/js/modules/`)

`app.js`, `stepper.js`, `hotel-context.js`, `simulation-panel.js`,
`geocode-panel.js`, `services-catalog.js`, `rule1-panel.js`,
`autocomplete.js`…

### CSS

- Tokens partagés : `static/shared/css/tokens.css`
- Admin : `static/css/app.css`
- User : `static/user/css/user.css`

---

## 16. Tests et validations

Pas de suite pytest imposée en prod (optionnel : `pip install -e ".[dev]"`).

Validation métier ROD :

```bash
accor-validate-rod
# équivalent
python -m accor.user.validate_rod
```

Vérifie les enchaînements revenus / coûts / reco sur des cas de référence
(pas de régression « frigo compté deux fois », facteurs règle 1, etc.).

Smoke modèle eval :

```bash
python -c "
from accor.model_eval import eval_meta, evaluate_model
print(eval_meta()['ok'], evaluate_model(None, year=2026).get('n_hotels'))
"
```

---

## 17. Commandes utiles

| Commande | Rôle |
|----------|------|
| `pip install -e .` | (re)installe le package en dev |
| `accor-admin` | Flask admin :5055 |
| `accor-user` | Flask user :5056 |
| `accor-validate-rod` | checks règles ROD |
| `python run_admin.py --debug` | admin + reloader |
| `python -c "from accor.store import get_frame; …"` | scripts one-shot |

Rebuilds Python directs (hors UI) :

```python
from accor.sales_prep import rebuild_hotel_sales_data
from accor.join_data import build_joined_dataframe, write_joined_excel
from accor.model_data import rebuild_model_data
from accor.concept_pilote import rebuild_concept_pilote
```

---

## 18. Dépannage

**`ModuleNotFoundError: accor`**  
→ activer le venv et `pip install -e .` depuis la racine projet.

**Excel verrouillé / Permission denied**  
→ fermer le fichier dans Excel / LibreOffice avant un rebuild.

**Modèle introuvable en eval**  
→ au moins un dossier sous `models/design/` avec `model.pkl`.  
Sinon lancer Model Build une fois.

**Warnings sklearn / xgboost version au unpickle**  
→ modèles entraînés avec une version antérieure. Souvent OK en lecture ;
pour du propre, ré-entraîner et redéployer.

**Hôtel inconnu côté user**  
→ le flux peut scraper all.accor.com puis écrire `hotel_data`. Si le réseau
bloque, ajouter la fiche à la main dans l’admin.

**Eval « aucune ligne »**  
→ pas de lignes `annee == year` avec la cible renseignée dans model_data.
Vérifier `model_data_meta.json` (`eval_year`, `n_eval`).

**Port déjà pris**  
→ `python run_admin.py --port 5057` (idem user).

---

## 19. Où trouver quoi dans le code

| Besoin | Module |
|--------|--------|
| Chemins data/models | `data_io.py`, `accor.__init__` |
| Nouvel onglet admin | `schemas.py` + Excel dans `data/` |
| CRUD / cache Excel | `store.py` |
| Jointure all_data | `join_data.py` |
| Features ML | `model_data.py`, `impute_model.py` |
| Train / deploy | `model_train.py` |
| Arbres UI | `model_explore.py` |
| Perf année incomplete | `model_eval.py` |
| Routes admin | `app.py` |
| Routes user | `user/app.py` |
| CA / règles | `user/rules/revenue.py` |
| Coûts | `user/rules/costs.py` |
| Reco concept | `user/rules/recommendation.py` |
| Simulate | `user/services/orchestrator.py`, `simulator.py` |
| Scrape 1 hôtel | `scrape_accor/hotels.py`, `user/services/hotel_fetch.py` |
| Catégories marque | `brand_category.py` |

Les docstrings en tête de module détaillent les règles métier locales
(imputation, split eval, métrique /12, etc.). En cas d’écart doc / code,
le code fait foi — corriger la doc au passage.

---

## Licence

Propriétaire (voir `pyproject.toml`). Usage interne projet ROD.
)
