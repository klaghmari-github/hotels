# Accor Data and Model Studio

Application web autonome pour preparer les donnees hotels Accor, construire une table de jointure, entrainer des modeles XGBoost et simuler un corner retail pour un directeur d hotel.

Le dossier `accord/` est l application active. Le dossier `../archive/` conserve d anciens pipelines et sources brutes. Il n est pas requis au demarrage, sauf pour des extractions ponctuelles (par exemple les grilles de couts).

---

## Demarrage

```bash
cd accord
pip install -r requirements.txt

# Interface admin (donnees, jointures, modeles)
python run_admin.py
# http://127.0.0.1:5055

# Interface user (wizard directeur / simulateur ROD)
python run_user.py
# http://127.0.0.1:5056
```

Options communes :

| Option | Defaut | Role |
|--------|--------|------|
| `--host` | 127.0.0.1 | Adresse d ecoute |
| `--port` | 5055 admin, 5056 user | Port HTTP |
| `--debug` | desactive | Mode debug Flask |

Deux entrees distinctes :

| Commande | Role |
|----------|------|
| `run_admin.py` | Edition des Excel, rebuild des jeux derives, Model Build et Explore, deploiement |
| `run_user.py` | Wizard directeur, enrichissement geo, revenus ROD, couts, recommandation de concept |

---

## Arborescence des dossiers

```
accord/
  run_admin.py          Lance l interface admin (appelle app.main)
  run_user.py           Lance l interface user (appelle user.app.main)
  app.py                Routes Flask admin (page HTML + API)
  schemas.py            Definition des onglets et des colonnes Excel
  data_io.py            Lecture Excel + normalisations partagees (DATA_DIR, FR)
  store.py              DatasetStore (cache, pagination, CRUD) + facades
  join_data.py          AllDataBuilder : construction de all_data
  model_data.py         Construction de model_data (jeu ML)
  model_train.py        XGBoost, BuildProgress, GridSearchPlanner, design/deploy
  model_explore.py      Analyse arbres, importances, performances
  sales_prep.py         SalesPrepPipeline + HotelBoutiqueMatcher
  geo_common.py         Utilitaires geo (hotels, annees, mois termines)
  geo_weather.py        Meteo mensuelle (Meteostat) et rebuild weather
  geo_proximity.py      Proximite commerces / plage (Overpass)
  geo_holidays.py       Calendrier feries, weekends, vacances scolaires
  parallel_common.py    Chunks FR, load hotels, merge shards (partage)
  parallel_weather.py   Rebuild meteo France multi-process
  parallel_proximity.py Rebuild proximite France multi-process
  parallel_holidays.py  Rebuild holidays France multi-process
  concept_pilote.py     Indicateurs annuels hotel (clients, CA, mix)
  sync_hotel_data.py    Fusion scrape Accor dans hotel_data
  sync_brand_data.py    Enrichissement hotel_brand_data depuis marques
  sync_data_files.py    Alignement des Excel sur les schemas UI
  clean_source_fills.py Retire d anciennes moyennes injectees dans les sources
  impute_model.py       Imputation des trous uniquement pour model_data
  extract_couts.py      Extraction des grilles de couts ROD vers couts.xlsx
  requirements.txt      Dependances Python
  README.md             Cette documentation (a tenir synchro avec le code)

  data/                 Fichiers Excel metier et artefacts regenerables
  models/               Modeles design, build_progress, modele deploye
  scrape_accor/         Scripts de scrape du catalogue Accor
  static/               Front admin + user + modules partages
  templates/            Pages HTML admin et user
  user/                 Application simulateur directeur (Flask + regles)
```

### data/

Source de verite editable pour l admin. Chaque onglet de la sidebar correspond en general a un fichier Excel ici.

| Contenu | Role |
|---------|------|
| `hotel_brand_data.xlsx` | Marques Accor (nom, logo, categories, effectifs) |
| `hotel_data.xlsx` | Parc hotels (identite, adresse, GPS, equipements, profils) |
| `hotel_proximity_data.xlsx` | Indicateurs de proximite (France) |
| `hotel_holidays_data.xlsx` | Jours feries, weekends, vacances (France) |
| `hotel_weather_data.xlsx` | Meteo mensuelle (France) |
| `hotel_sales_raw_data.xlsx` | Tickets de vente bruts |
| `hotel_sales_data.xlsx` | Ventes mensuelles agregees (pilotes) |
| `all_data.xlsx` | Jointure hotels avec ventes x annee x mois |
| `model_data.xlsx` | Jeu d apprentissage derive d all_data |
| `model_data_meta.json` | Roles de colonnes (id, descriptive, cible) pour le ML |
| `concept_pilote.xlsx` | Indicateurs annuels par hotel pilote |
| `couts.xlsx` | Grilles de couts ROD (plusieurs feuilles) |
| `rod_reference.json` | Constantes metier pour le simulateur user |
| `marques/` | Logos par categorie et scrapes hotels |
| `proximity_shards/` | Tranches intermediaires du calcul proximite FR |
| `proximity_state/` | Progression et resumes du calcul proximite |
| `holidays_shards/` | Tranches intermediaires du calcul holidays FR |
| `holidays_state/` | Progression et resumes du calcul holidays |
| `weather_shards/` | Tranches intermediaires du calcul meteo FR |
| `weather_state/` | Progression, resumes et liste des manquants meteo |

Attention : `all_data.xlsx` peut depasser 100 Mo. Il est ignore par git (fichier local regenerable).

### data/marques/

| Sous-dossier ou fichier | Role |
|-------------------------|------|
| `marques.xlsx` | Table des marques (source pour brand data) |
| `economy/`, `midscale/`, `premium/`, `luxury/`, etc. | Logos PNG par categorie de marque |
| `hotels/` | Exports de scrape (par pays, par plage de codes, fichiers all / matched / missing) |
| `hotels_state/` | Fichiers JSON de progression des scrapes paralleles |

### models/

| Chemin | Role |
|--------|------|
| `design/<nom>/model.pkl` | Modele XGBoost entraine |
| `design/<nom>/config.json` | Hyperparametres, perfs, meta |
| `deploy/model.pkl` | Modele unique de production |
| `deploy/model.json` | Config du modele deploye |
| `last_trained.json` | Pointeur vers le dernier entrainement |
| `build_progress.json` | Etat du batch Model Build (polling UI) |

### scrape_accor/

Scripts pour recuperer le catalogue hotels Accor (marques, destinations, codes, pages hotel). Voir aussi `scrape_accor/README.md` s il est present.

| Fichier | Role |
|---------|------|
| `brands.py`, `run_brands.py` | Scrape des marques |
| `destination_france.py`, `destination_country.py` | Destinations et listes par pays |
| `hotels.py`, `worker.py` | Detail d un hotel |
| `parallel_codes.py`, `world_scrape.py` | Traitement parallele multi-pays |
| `http_util.py` | Requetes HTTP partagees |
| `countries_config.py` | Configuration des pays |

### static/ et templates/

Les deux interfaces chargent des **ES modules** (`type="module"`).  
Le user Flask sert tout `static/` (pas seulement `static/user/`) pour que les modules partages soient accessibles.

```
static/
  shared/
    css/tokens.css          Fonts, or Accor, rayons (tokens communs)
    js/
      dom.js                $, $$, escapeHtml, debounce, fieldStr/Num
      api.js                ApiClient (GET/POST/PUT/DELETE JSON)
      toast.js              ToastHost (admin multi ou user single)
      format.js             Format.euro / pct / toRate / fixed
      loading.js            LoadingOverlay (compteur d appels imbriques)
  js/
    admin/
      app.js                AdminApp (point d entree)
      state.js              AdminState (dirty, page, explore)
      constants.js          PINNED_TOP_IDS, REBUILD_MAP, icones
      nav-controller.js     Sidebar All / Pilotes / Modeles
      table-renderer.js     Table editable + logos + roles model_data
      dataset-controller.js Fetch page, save, rebuild, reload
      model-build-panel.js  Grid search + progress + ranking
      model-explore-panel.js Liste modeles, metriques, arbres
      tree-svg.js           Layout + SVG arbres XGBoost
    app.js                  Stub legacy (redirige vers admin/app.js)
  css/app.css               Theme sombre admin
  img/                      Logo Accor
  user/
    css/user.css            Theme clair wizard
    js/
      modules/
        app.js              UserApp (point d entree)
        stepper.js          Wizard 5 etapes
        autocomplete.js     Suggestions hotel_data
        hotel-context.js    BrandSelect, HotelContextLoader
        services-catalog.js SERVICES + ServiceToggles
        rule1-panel.js      Clients derives + CA regle 1
        simulation-panel.js POST /api/simulate + rendu
        geocode-panel.js    Localisation adresse / code Accor
      user.js               Stub legacy (redirige vers modules/app.js)
templates/
  index.html                Admin (charge /static/js/admin/app.js)
  user/index.html           User (charge /static/user/js/modules/app.js)
```

| Chemin | Role |
|--------|------|
| `templates/index.html` | Shell admin : sidebar + table + Model Build/Explore |
| `templates/user/index.html` | Shell wizard 5 etapes + footer navigation |
| `static/shared/` | Core JS/CSS reutilise par admin et user |
| `static/js/admin/` | Front admin OOP |
| `static/user/js/modules/` | Front user OOP |
| `static/css/app.css`, `static/user/css/user.css` | Themes |

### user/

Application Flask separee pour le directeur d hotel.  
`static_folder` = `accord/static` (url `/static`) pour servir `user/` et `shared/`.

| Chemin | Role |
|--------|------|
| `app.py` | Routes API du wizard + page HTML |
| `models.py` | Structures de requete et de resultat |
| `reference.py` | Lecture de `rod_reference.json` |
| `rules/revenue.py` | Calcul des revenus (concepts, clients, mix) |
| `rules/costs.py` | Calcul des couts |
| `rules/recommendation.py` | Choix de concept (SIMPLY, LIBERTY, CONNECTED) |
| `services/geocode.py` | Geocodage adresse / page Accor |
| `services/enrich.py` | Enrichissement meteo, proximite, holidays |
| `services/orchestrator.py` | Enchainement du parcours de simulation |
| `services/catalog.py` | Catalogue marques / hotels (lecture Excel admin) |
| `services/hotel_context.py` | Profil hotel pour presaisie wizard |
| `services/simulator.py` | Assemblage simulation |

---

## Patterns de fichiers

Convention generale : un onglet admin egal un fichier Excel sous `data/`, declare dans `schemas.DATASETS`.

| Pattern | Signification |
|---------|----------------|
| `hotel_*_data.xlsx` | Jeu edite ou reconstruit pour un domaine (brand, hotel, sales, weather, etc.) |
| `*_raw_data.xlsx` | Donnees brutes avant agregation |
| `all_data.xlsx` | Jointure multi-sources (derive) |
| `model_data.xlsx` | Jeu ML (derive, lecture seule dans l UI) |
| `*_shards/*_fr_shardNN.xlsx` | Tranche parallele pour un rebuild France (00 a 11) |
| `*_state/*_progress.json` | Progression d un process shard |
| `*_state/*_summary.json` | Resume de fin de shard |
| `*_state/*_merge_summary.json` | Resume de fusion vers le fichier principal |
| `models/design/<nom>/` | Un essai d entrainement nomme |
| `models/deploy/model.*` | Modele actif unique |
| `data/marques/hotels/*_destination_*.xlsx` | Scrape par pays (all, matched, missing) |
| `data/marques/hotels/hotels_all.xlsx` | Catalogue scrapes consolide |

---

## Flux de donnees

1. Sources editees ou reconstruites : brand, hotel, proximity, holidays, weather, sales raw, sales.
2. Bouton Reconstruire sur All Data : jointure des hotels qui ont des ventes dans `hotel_sales_data`, avec holidays, weather, brand, proximity.
3. Bouton Reconstruire sur Model Data : filtre et preparation ML a partir de all_data (imputation des trous).
4. Model Build : entrainement XGBoost sur model_data, sauvegarde dans `models/design/<nom>/`.
5. Model Explore Deploy : copie du modele choisi vers `models/deploy/`.

Regles sur les valeurs manquantes :

| Fichier | Traitement des trous |
|---------|----------------------|
| Sources (hotel_data, brand, sales, etc.) | Laisses vides pour saisie ulterieure |
| all_data | Laisses vides apres jointure |
| model_data | Imputes (moyenne marque puis globale pour certaines variables, 0 pour comptes et counts) |

---

## Onglets et fichiers de donnees

La sidebar admin a trois zones : All, Pilotes, Modeles.

### Zone All (parc global)

| Onglet | Fichier | Description UI | Rebuild |
|--------|---------|----------------|---------|
| Hotel Brand Data | `hotel_brand_data.xlsx` | Toutes les marques Accor | Non (edition + sync_brand_data) |
| Hotel Data | `hotel_data.xlsx` | Tous les hotels Accor | Non (edition + sync_hotel_data) |
| Hotel Proximity Data (FR) | `hotel_proximity_data.xlsx` | Commerces de proximite de tous les hotels Accor (FR) | Oui (Overpass) |
| Hotel Holidays Data | `hotel_holidays_data.xlsx` | Jours feries et vacances (FR) | Oui (calendrier) |
| Hotel Weather Data | `hotel_weather_data.xlsx` | Meteo (FR) | Oui (Meteostat) |

### Zone Pilotes

| Onglet | Fichier | Description | Rebuild |
|--------|---------|-------------|---------|
| Hotel Sales Raw Data | `hotel_sales_raw_data.xlsx` | Tickets bruts | Non (saisie / import) |
| Hotel Sales Data | `hotel_sales_data.xlsx` | Ventes mensuelles + mix | Oui (depuis raw) |
| All Data | `all_data.xlsx` | Jointure hotels avec ventes | Oui |
| Concept Pilote | `concept_pilote.xlsx` | Indicateurs annuels | Oui |
| Model Data | `model_data.xlsx` | Dataset ML (lecture seule) | Oui |

### Zone Modeles

| Entree | Role |
|--------|------|
| Model Build | Configurer et entrainer un modele XGBoost |
| Model Explore | Comparer les modeles design, visualiser les arbres, deployer |

### Detail All Data

- Ne garde que les hotels presents dans `hotel_sales_data` (au moins une ligne de vente).
- Base (spine) = mois de vente reels, pas un produit cartesien de tout le parc.
- Joint a gauche : sales (deja dans la base), holidays, weather, hotel, proximity, brand.
- Options optionnelles de comblement reseau meteo / proximite au rebuild (desactivees par defaut dans le bouton UI).
- Classes : `join_data.AllDataBuilder` ; facade `build_joined_dataframe` ; UI via `store.rebuild_joined_data`.

### Detail Model Data

- Derive de all_data.
- Ne conserve que les hotels ayant des ventes strictement positives.
- Supprime les colonnes constantes.
- Classe les colonnes en trois roles : id_detail (or dans l UI, y compris `logo_path`), descriptive, target (vert).
- La derniere annee sert d evaluation (lignes en gras) ; le reste sert d entrainement.
- Cible principale de scoring : `montant_ventes`.
- Module : `model_data.rebuild_model_data`.

---

## Architecture backend (classes)

Refactor orientee objet sans casser les facades publiques consommees par `app.py` et les scripts.

| Module | Classe / element | Role |
|--------|------------------|------|
| `data_io.py` | fonctions pures | `read_excel`, `filter_france_hotels`, `normalize_hotel_code_*`, `DATA_DIR` |
| `store.py` | `DatasetStore` | Cache RLock, page_payload, CRUD, rebuild join |
| `store.py` | facades | `get_frame`, `page_payload`, `update_rows`, `add_row`, `delete_rows`, `reload_dataset`, `rebuild_joined_data`, `_cache` |
| `sales_prep.py` | `HotelBoutiqueMatcher` | NOM BOUTIQUE → hotel_code |
| `sales_prep.py` | `SalesPrepPipeline` | load → prepare → aggregate → holidays → write |
| `sales_prep.py` | `rebuild_hotel_sales_data` | Facade stable pour l API admin |
| `join_data.py` | `AllDataBuilder` | Spine ventes + left joins |
| `join_data.py` | `build_joined_dataframe` / `save_joined_excel` | Facades scripts + store |
| `model_train.py` | `BuildProgress` | Etat batch + `models/build_progress.json` pour le poll UI |
| `model_train.py` | `GridSearchPlanner` | 1 job manuel + combinaisons grid (dedup) |
| `parallel_common.py` | `chunk_list`, `load_france_hotels`, merge | Partage weather / holidays / proximity |
| `geo_common.py` | re-export `filter_france_hotels` | Annees ventes, mois termines, filtres |

Regle de maintenance : si une route Flask ou un script importe un symbole public, le garder en facade meme si la logique vit dans une classe.

---

## Architecture front (ES modules)

### Shared (`static/shared/js/`)

| Fichier | Export principal | Role |
|---------|------------------|------|
| `dom.js` | `$`, `$$`, `escapeHtml`, `debounce`, `fieldStr/Num/Checked` | DOM et champs formulaire |
| `api.js` | `ApiClient`, `api` | HTTP JSON, leve Error si HTTP non 2xx |
| `toast.js` | `ToastHost`, `toast` | Notifications (host multi admin ou `#toast` user) |
| `format.js` | `Format` | euro, pct, toRate, fixed, locale |
| `loading.js` | `LoadingOverlay`, `loading` | Overlay admin avec profondeur d appels |

### Admin (`static/js/admin/`)

| Fichier | Classe | Role |
|---------|--------|------|
| `app.js` | `AdminApp` | Boot, wire events, expose `window.AccorAdmin` |
| `state.js` | `AdminState` | page, dirty Map, selected Set, explore |
| `nav-controller.js` | `NavController` | Rendu sidebar, bascule table / build / explore |
| `table-renderer.js` | `TableRenderer` | En-tetes, cellules, logos, stats model_data |
| `dataset-controller.js` | `DatasetController` | selectDataset, fetchPage, save, rebuild |
| `model-build-panel.js` | `ModelBuildPanel` | Config, grid, poll progress, ranking |
| `model-explore-panel.js` | `ModelExplorePanel` | Liste, metriques, importance, deploy |
| `tree-svg.js` | `TreeSvgRenderer` | Layout + SVG arbre |
| `constants.js` | constantes | PINNED_TOP_IDS, REBUILD_MAP, HEAVY_LOAD_SUB |

Debug navigateur admin : `window.AccorAdmin` (instance de `AdminApp`).

### User (`static/user/js/modules/`)

| Fichier | Classe | Role |
|---------|--------|------|
| `app.js` | `UserApp` | Boot, wire, charge brands/hotels/meta |
| `stepper.js` | `Stepper` | Navigation etapes 1–5 |
| `autocomplete.js` | `HotelAutocomplete` | Search `/api/hotels/search` |
| `hotel-context.js` | `BrandSelect`, `HotelContextLoader` | Presaisie hotel + moyennes marque |
| `services-catalog.js` | `ServiceToggles`, `SERVICES` | Toggles equipements |
| `rule1-panel.js` | `Rule1Panel` | Clients/jour-mois + `POST /api/rule1` |
| `simulation-panel.js` | `SimulationPanel` | `POST /api/simulate?light=1` + rendu |
| `geocode-panel.js` | `GeocodePanel` | `POST /api/geocode` |

Debug navigateur user : `window.RODUser` (instance de `UserApp`).

---

## Interface graphique admin (run_admin.py)

Fichiers front : `templates/index.html`, `static/js/admin/app.js` (ES modules),
`static/shared/js/*`, `static/css/app.css`, `static/shared/css/tokens.css`.
Backend : `app.py` (routes), `store.DatasetStore` (Excel).

### Sidebar

- En haut, logo Accor fixe (ne scrolle pas).
- Zone scrollable unique avec trois libelles : All, Pilotes, Modeles.
- Zone All : brand, hotel, proximity, holidays, weather (ordre `PINNED_TOP_IDS` dans `constants.js`).
- Zone Pilotes : les autres datasets renvoyes par `GET /api/datasets`.
- Zone Modeles : boutons Model Build et Model Explore (pas des Excel).

Un clic sur un onglet dataset appelle `DatasetController.selectDataset` puis
`GET /api/datasets/<id>`.

Un overlay de chargement (`LoadingOverlay`) s affiche pendant les chargements
d onglet ou les rebuilds longs.

### Vue table (datasets)

Barre du haut :

| Element | Action | Appel backend |
|---------|--------|---------------|
| Champ Filtrer | Filtre texte serveur (recherche) | `GET /api/datasets/<id>?q=...` |
| Recharger | Relit le fichier Excel sans recalculer | `POST /api/datasets/<id>/reload` |
| Reconstruire | Recalcule un fichier derive (visible seulement sur certains onglets) | Voir tableau rebuild ci-dessous |
| Ligne | Ajoute une ligne vide | `POST /api/datasets/<id>/rows` |
| Enregistrer | Sauve les cellules modifiees (actif si dirty) | `PUT /api/datasets/<id>/rows` |
| Ctrl+S | Raccourci Enregistrer | meme PUT |

Pagination :

| Element | Action |
|---------|--------|
| Lignes / page | Change la taille de page et relance le GET page |
| Premiere / Precedente / Suivante / Derniere | Navigation de page |
| Supprimer selection | Supprime les lignes cochees via `DELETE /api/datasets/<id>/rows` |

Table :

- Chaque cellule editable est un champ. Modifier met a jour une map locale `dirty` (index de ligne + colonnes).
- Les colonnes cles (key_columns du schema) sont mises en avant.
- Les colonnes image (logo_path) affichent une vignette via `/api/marques/logos/...`.
- Sur Model Data, les en-tetes sont colores selon le role (id / descriptive / target) et les lignes d evaluation sont en gras. Des stats s affichent sous la table.

Onglets en lecture seule (pas d ajout, sauvegarde, suppression) : sales, model_data, concept_pilote (et tout schema avec `readonly=True`).

### Bouton Reconstruire par onglet

| Onglet | Route | Module appele | Effet |
|--------|-------|---------------|-------|
| sales | `POST /api/datasets/sales/rebuild` | `SalesPrepPipeline` via `rebuild_hotel_sales_data` | Agrege sales_raw (+ holidays) vers hotel_sales_data |
| weather | `POST /api/datasets/weather/rebuild` | `geo_weather.rebuild_hotel_weather_data` | Recalcule la meteo pour le parc hotels |
| proximity | `POST /api/datasets/proximity/rebuild` | `geo_proximity.rebuild_hotel_proximity_data` | Recalcule la proximite Overpass |
| holidays | `POST /api/datasets/holidays/rebuild` | `geo_holidays.rebuild_hotel_holidays_data` | Recalcule le calendrier feries / vacances |
| all_data | `POST /api/datasets/all_data/rebuild` | `DatasetStore.rebuild_joined_data` → `AllDataBuilder` | Jointure hotels avec ventes |
| model_data | `POST /api/datasets/model_data/rebuild` | `model_data.rebuild_model_data` | Derive le jeu ML |
| concept_pilote | `POST /api/datasets/concept_pilote/rebuild` | `concept_pilote.rebuild_concept_pilote` | Indicateurs annuels |

Apres un rebuild reussi, le front recharge la page courante du dataset.

Pour les rebuilds massifs France (tous les hotels FR), preferer en ligne de commande les modules paralleles (plus rapides et reprises possibles) :

```bash
python -m parallel_proximity --workers 12
python -m parallel_holidays --workers 12
python -m parallel_weather --workers 12 --pause 0.25
```

### Vue Model Build

Classe front : `ModelBuildPanel`. Backend : `model_train` (`GridSearchPlanner`, `BuildProgress`).

| Element | Action | Backend |
|---------|--------|---------|
| Champ Nom | Nom du dossier sous `models/design/` | body `model_name` |
| Params manuels | n_estimators, max_depth, learning_rate, etc. | `GET /api/model/config` puis body `xgb_params` |
| Grid search | Listes de valeurs par hyperparam (optionnel) | body `grid_search` |
| Cible principale | Ex. montant_ventes | body `main_target` |
| Metrique de rang | r2 / rmse / mae | body `rank_metric` |
| Build and Save | Lance un batch async (manuel + grid) | `POST /api/model/build` (`async: true`) |
| Barre de progression | Poll pendant le batch | `GET /api/model/build/progress` |
| Tableau resultats | Modeles tries (meilleur en premier) | contenu du progress (`results`) |

Comportement du build :

- Source fixe : model_data.
- Features : colonnes descriptives (pas les id_detail comme logo_path).
- Split temporel : `_is_eval=0` train, `_is_eval=1` eval (derniere annee).
- Chaque job ecrit `models/design/<nom>/model.pkl` + `config.json`.
- Le job manuel utilise le nom saisi ; les jobs grid utilisent des suffixes.
- Met a jour `models/last_trained.json` et `models/build_progress.json`.
- Le front poll toutes les ~800 ms jusqu a `done` ou `error`.

### Vue Model Explore

Classe front : `ModelExplorePanel` + `TreeSvgRenderer`.

| Element | Action | Backend |
|---------|--------|---------|
| Select modele | Change le modele explore (liste triee par perf) | `GET /api/model/list` puis explore |
| Recharger | Rafraichit liste et graphiques | `GET /api/model/list` + explore |
| Deploy | Copie le modele selectionne vers deploy | `POST /api/model/deploy` |
| Feature importance | Barres d importance | inclus dans `GET /api/model/<id>/explore` |
| Table des arbres | Profondeur, features, R2/RMSE cumules | `GET /api/model/<id>/trees` |
| Slider arbre | Affiche un arbre en SVG | `GET /api/model/<id>/tree?tree=k` |

Notes :

- La perf par arbre est cumulative (boosting) : apres k arbres, pas la prediction d un arbre isole.
- Un seul modele deploye a la fois (`models/deploy/model.pkl` et `model.json`).

---

## API HTTP admin

### Sante et datasets

| Methode | Route | Role |
|---------|-------|------|
| GET | `/api/health` | Sonde |
| GET | `/api/datasets` | Liste des onglets et schemas |
| GET | `/api/datasets/<id>` | Page de lignes (page, page_size, q) |
| PUT | `/api/datasets/<id>/rows` | Mise a jour de lignes (champ _index) |
| POST | `/api/datasets/<id>/rows` | Ajout d une ligne |
| DELETE | `/api/datasets/<id>/rows` | Suppression (liste d indices) |
| POST | `/api/datasets/<id>/reload` | Invalide le cache et relit l Excel |
| GET | `/api/marques/logos/<path>` | Sert un logo sous data/marques |

### Rebuild derives

| Methode | Route | Role |
|---------|-------|------|
| POST | `/api/datasets/all_data/rebuild` | Jointure all_data |
| POST | `/api/datasets/model_data/rebuild` | Rebuild model_data |
| POST | `/api/datasets/sales/rebuild` | Rebuild sales depuis raw |
| POST | `/api/datasets/weather/rebuild` | Rebuild weather |
| POST | `/api/datasets/proximity/rebuild` | Rebuild proximity |
| POST | `/api/datasets/holidays/rebuild` | Rebuild holidays |
| POST | `/api/datasets/concept_pilote/rebuild` | Rebuild concept pilote |

### Modeles

| Methode | Route | Role |
|---------|-------|------|
| GET | `/api/model/config` | Hyperparams par defaut et stats model_data |
| GET | `/api/model/list` | Modeles design tries + last / top |
| POST | `/api/model/build` | Entraine batch (manuel + grid, async) vers design |
| GET | `/api/model/build/count` | Nombre de jobs prevus (manuel + grid, sans lancer) |
| GET | `/api/model/build/progress` | Progression / resultats du batch en cours |
| POST | `/api/model/deploy` | Copie design vers deploy |
| GET | `/api/model/<id>` | Config d un modele |
| GET | `/api/model/<id>/explore` | Vue d ensemble (metriques + importance) |
| GET | `/api/model/<id>/trees` | Table des arbres |
| GET | `/api/model/<id>/tree` | Structure d un arbre |
| GET | `/api/model/<id>/importance` | Feature importance (si endpoint separe) |

---

## Modules Python (resume)

| Module | Role |
|--------|------|
| `schemas.py` | DatasetSchema et registre DATASETS (colonnes, cles, readonly, descriptions UI) |
| `data_io.py` | Lecture Excel tolerante, filtres FR, normalisation codes hotel |
| `store.py` | `DatasetStore` : cache, pagination, coercion, projection schema, CRUD |
| `join_data.py` | `AllDataBuilder` : spine ventes + left joins all_data |
| `sales_prep.py` | `SalesPrepPipeline` + `HotelBoutiqueMatcher` (raw → sales) |
| `geo_common.py` | Hotels, annees de ventes, mois termines, re-export filtres FR |
| `geo_weather.py` | Meteostat multi-stations, rebuild weather |
| `geo_proximity.py` | Overpass, rebuild proximity |
| `geo_holidays.py` | Calendrier scolaire et feries FR |
| `parallel_common.py` | Chunks, load FR, merge shards Excel |
| `parallel_*.py` | Workers France weather / holidays / proximity (utilisent parallel_common) |
| `model_data.py` | Filtre, roles de colonnes (id_detail / descriptive / target), split annee eval |
| `model_train.py` | XGBoost multi-sortie, `GridSearchPlanner`, `BuildProgress`, design et deploy |
| `model_explore.py` | Dump arbres XGBoost, metriques cumulees |
| `concept_pilote.py` | Indicateurs annuels pilotes (+ moyennes marque pour le user) |
| `sync_hotel_data.py` | Scrape catalogue vers hotel_data |
| `sync_brand_data.py` | Marques vers hotel_brand_data |
| `sync_data_files.py` | Alignement Excel + rebuild all_data |
| `clean_source_fills.py` | Nettoyage d anciennes imputations sources |
| `impute_model.py` | Imputation reservee a model_data |
| `extract_couts.py` | Parse grilles simulateur ROD vers couts.xlsx |

---

## Scripts utiles

```bash
cd accord

# Aligner les Excel sur les schemas et reconstruire all_data
python sync_data_files.py

# Remplir hotel_data depuis le scrape consolide
python -m sync_hotel_data

# Enrichir hotel_brand_data depuis data/marques/marques.xlsx
python -m sync_brand_data

# Retirer d anciennes moyennes injectees dans les sources
python -m clean_source_fills

# Rebuilds France en parallele (jusqu a 12 process)
python -m parallel_holidays --workers 12
python -m parallel_weather --workers 12 --pause 0.25
python -m parallel_proximity --workers 12 --pause 0.9

# Fusion seule (apres interruption)
python -m parallel_weather --merge-only

# Reconstruire model_data en Python
python -c "from model_data import rebuild_model_data; print(rebuild_model_data())"

# Extraire les couts ROD (necessite la source sous ../archive/sources/raw/)
python extract_couts.py
```

---

## Dependances

Voir `requirements.txt` :

- Flask, pandas, openpyxl pour l app et les Excel
- requests pour le reseau (scrape, Overpass)
- meteostat pour la meteo (optionnel mais recommande)
- scikit-learn, xgboost, numpy pour le ML

---

## Conventions

- Identite hotel : code Accor (`hotel_code`), avec prefixe H dans hotel_data quand c est le format stocke.
- Les fichiers sous `data/` sont la source de verite editee par l admin.
- `all_data` et `model_data` sont derives (boutons Reconstruire ou scripts).
- Les modeles d exploration vivent dans `models/design/` ; la production dans `models/deploy/`.
- Les gros fichiers regenerables (all_data volumineux, shards) ne doivent pas bloquer le push git : all_data est ignore, les shards restent locaux si besoin.
- Commentaires de code : phrases courtes, neutres, en francais ou anglais coherent avec le fichier, sans symboles decoratifs.

---

## Coûts (couts.xlsx)

Feuilles principales :

| Feuille | Contenu |
|---------|---------|
| resume | Synthese par solution (simply, liberty, connected) |
| couts_technos | Materiel, licences, frais |
| couts_annexes | Electricite et personnel |
| couts_agencement | Metres lineaires et finitions |
| revenus_mix_marges | Mix F et B / non F et B et marges |
| revenus_impact_to | Impact TO et CA pilotes |
| meta | Source et notes |

---

## Interface user (run_user.py)

Fichiers front : `templates/user/index.html`, `static/user/js/modules/app.js`,
`static/shared/js/*`, `static/user/css/user.css`.
Backend : `user/app.py` + `user/services/*` + `user/rules/*`.

Wizard multi-etapes (classe `Stepper`) :

| Etape | Contenu UI | Front | Backend principal |
|-------|------------|-------|-------------------|
| 1 Hotel | Code, nom, marque, adresse, exploitation, geocode | `HotelAutocomplete`, `HotelContextLoader`, `GeocodePanel`, `BrandSelect` | `/api/hotels/search`, `/api/hotels/<code>/context`, `/api/geocode`, `/api/concept_pilote/brand/<marque>`, `/api/rule1` |
| 2 Services | Toggles F&B, non-F&B, confort, lobby, corner | `ServiceToggles` | presaisie depuis context |
| 3 Clients | Mix loisirs/affaires, besoins | meta `client_needs_*` | `/api/meta` |
| 4 Corner | m lin., mix F&B, corner existant | champs formulaire | inclus dans payload simulate |
| 5 Simulation | Cartes concepts, detail CA, enrichissement | `SimulationPanel` | `/api/simulate?light=1` |

Comportement important :

- Des qu un code ou un nom d hotel est choisi, le front charge le profil `hotel_data` et pre-coche les equipements.
- Changer la marque charge les moyennes `concept_pilote` (hors annee la plus recente).
- Les champs chambres / TO / guests mettent a jour les clients derives et le CA regle 1 (debounce).
- La simulation appelle l orchestrateur (revenus + couts + recommandation + enrichissement leger).

Le moteur revenus et le moteur couts sont separes pour pouvoir faire evoluer l un sans l autre.

### API HTTP user

| Methode | Route | Role |
|---------|-------|------|
| GET | `/api/health` | Sonde |
| GET | `/api/meta` | Labels besoins clients, constantes UI |
| GET | `/api/brands` | Liste marques (catalogue) |
| GET | `/api/hotels` | Liste hotels legere |
| GET | `/api/hotels/search?q=` | Autocomplete |
| GET | `/api/hotels/<code>` | Fiche hotel |
| GET | `/api/hotels/<code>/context` | Profil complet pour presaisie |
| GET | `/api/concept_pilote/brand/<marque>` | Moyennes marque (+ rule1 optionnel) |
| POST | `/api/rule1` | CA regle 1 pour 3 concepts |
| POST | `/api/geocode` | Lat/lon depuis adresse ou code Accor |
| POST | `/api/enrich` | Enrichissement geo complet |
| POST | `/api/simulate` | Simulation ROD (query `light=1` pour parcours rapide) |

---

## Synchronisation code / documentation

Quand le code change, mettre a jour **dans le meme commit** :

1. Docstring du module (role, classes publiques, facades).
2. Cette `README.md` (arborescence, tableaux API, classes front, boutons UI).
3. Commentaire HTML en tete de `templates/*.html` si les scripts charges changent.

Conventions de commentaires :

- Phrases courtes, neutres, humaines (francais ou anglais coherent avec le fichier).
- Pas de symboles decoratifs ni de jargon de refactor (« WIP », « temporary hack »).
- Les facades publiques documentees ici doivent exister dans le code (`rebuild_hotel_sales_data`, `get_frame`, `build_joined_dataframe`, etc.).

---

## Contexte

Projet interne d analyse et de simulation retail / corner pour hotels Accor (ROD).
L archive historique sous `../archive/` conserve les pipelines de preparation de donnees d origine.
