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
  store.py              Lecture, cache, pagination et sauvegarde Excel
  join_data.py          Construction de all_data (jointure)
  model_data.py         Construction de model_data (jeu ML)
  model_train.py        Entrainement XGBoost vers models/design
  model_explore.py      Analyse arbres, importances, performances
  sales_prep.py         Agregation sales_raw vers hotel_sales_data
  geo_common.py         Utilitaires partages (hotels, annees, mois)
  geo_weather.py        Meteo mensuelle (Meteostat) et rebuild weather
  geo_proximity.py      Proximite commerces / plage (Overpass)
  geo_holidays.py       Calendrier feries, weekends, vacances scolaires
  parallel_weather.py   Rebuild meteo France en plusieurs process
  parallel_proximity.py Rebuild proximite France en plusieurs process
  parallel_holidays.py  Rebuild holidays France en plusieurs process
  concept_pilote.py     Indicateurs annuels hotel (clients, CA, mix)
  sync_hotel_data.py    Fusion scrape Accor dans hotel_data
  sync_brand_data.py    Enrichissement hotel_brand_data depuis marques
  sync_data_files.py    Alignement des Excel sur les schemas UI
  clean_source_fills.py Retire d anciennes moyennes injectees dans les sources
  impute_model.py       Imputation des trous uniquement pour model_data
  extract_couts.py      Extraction des grilles de couts ROD vers couts.xlsx
  requirements.txt      Dependances Python
  README.md             Cette documentation

  data/                 Fichiers Excel metier et artefacts regenerables
  models/               Modeles design et modele deploye
  scrape_accor/         Scripts de scrape du catalogue Accor
  static/               CSS, JS et images de l interface
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

| Chemin | Role |
|--------|------|
| `templates/index.html` | Page unique de l admin (sidebar + tables + modeles) |
| `templates/user/index.html` | Page wizard du simulateur user |
| `static/css/app.css` | Styles admin |
| `static/js/app.js` | Logique front admin (onglets, tables, API) |
| `static/img/` | Logo Accor et assets |
| `static/user/css`, `static/user/js` | Styles et logique du wizard user |

### user/

Application Flask separee pour le directeur d hotel.

| Chemin | Role |
|--------|------|
| `app.py` | Routes API du wizard |
| `models.py` | Structures de requete et de resultat |
| `reference.py` | Lecture de `rod_reference.json` |
| `rules/revenue.py` | Calcul des revenus (concepts, clients, mix) |
| `rules/costs.py` | Calcul des couts |
| `rules/recommendation.py` | Choix de concept (SIMPLY, LIBERTY, CONNECTED) |
| `services/geocode.py` | Geocodage adresse / page Accor |
| `services/enrich.py` | Enrichissement meteo, proximite, holidays |
| `services/orchestrator.py` | Enchainement du parcours de simulation |
| `services/catalog.py`, `hotel_context.py`, `simulator.py` | Catalogue, contexte hotel, simulation |

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
- Construit une grille hotel x annees de ventes x 12 mois.
- Joint a gauche : sales, holidays, weather, proximity (par code hotel), brand (par marque).
- Options optionnelles de comblement reseau meteo / proximite au rebuild (desactivees par defaut dans le sync batch).
- Module : `join_data.build_joined_dataframe`, appele via `store.rebuild_joined_data`.

### Detail Model Data

- Derive de all_data.
- Ne conserve que les hotels ayant des ventes strictement positives.
- Supprime les colonnes constantes.
- Classe les colonnes en trois roles : id_detail (or dans l UI), descriptive, target (vert).
- La derniere annee sert d evaluation (lignes en gras) ; le reste sert d entrainement.
- Cible principale de scoring : `montant_ventes`.
- Module : `model_data.rebuild_model_data`.

---

## Interface graphique admin (run_admin.py)

Fichiers front : `templates/index.html`, `static/js/app.js`, `static/css/app.css`.
Backend : `app.py` (routes), `store.py` (Excel).

### Sidebar

- En haut, logo Accor fixe (ne scrolle pas).
- Zone scrollable unique avec trois libelles : All, Pilotes, Modeles.
- Zone All : brand, hotel, proximity, holidays, weather (ordre fixe dans le JS).
- Zone Pilotes : les autres datasets renvoyes par `GET /api/datasets`.
- Zone Modeles : boutons Model Build et Model Explore (pas des Excel).

Un clic sur un onglet dataset appelle `selectDataset` puis charge une page via `GET /api/datasets/<id>`.

Un overlay de chargement s affiche pendant les chargements d onglet ou les rebuilds longs.

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
| sales | `POST /api/datasets/sales/rebuild` | `sales_prep.rebuild_hotel_sales_data` | Agrege sales_raw (+ holidays) vers hotel_sales_data |
| weather | `POST /api/datasets/weather/rebuild` | `geo_weather.rebuild_hotel_weather_data` | Recalcule la meteo pour le parc hotels |
| proximity | `POST /api/datasets/proximity/rebuild` | `geo_proximity.rebuild_hotel_proximity_data` | Recalcule la proximite Overpass |
| holidays | `POST /api/datasets/holidays/rebuild` | `geo_holidays.rebuild_hotel_holidays_data` | Recalcule le calendrier feries / vacances |
| all_data | `POST /api/datasets/all_data/rebuild` | `store.rebuild_joined_data` puis `join_data` | Jointure hotels avec ventes |
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

| Element | Action | Backend |
|---------|--------|---------|
| Champ Nom | Nom du dossier sous `models/design/` | envoye dans le body du build |
| Grille hyperparametres | n_estimators, max_depth, learning_rate, etc. | chargee via `GET /api/model/config` |
| Build and Save | Entraine et sauve | `POST /api/model/build` |

Comportement du build :

- Source fixe : model_data.
- Features : colonnes descriptives.
- Split temporel : annees strictement inferieures a l annee max pour le train, annee max pour l eval.
- Ecrit `models/design/<nom>/model.pkl` et `config.json` (ecrase si le nom existe).
- Met a jour `models/last_trained.json`.

### Vue Model Explore

| Element | Action | Backend |
|---------|--------|---------|
| Select modele | Change le modele explore (liste triee par perf) | `GET /api/model/list` puis endpoints explore |
| Recharger | Rafraichit liste et graphiques | `GET /api/model/list` + explore |
| Deploy | Copie le modele selectionne vers deploy | `POST /api/model/deploy` |
| Feature importance | Barres d importance | `GET /api/model/<id>/importance` |
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
| POST | `/api/model/build` | Entraine et sauve un design |
| POST | `/api/model/deploy` | Copie design vers deploy |
| GET | `/api/model/<id>` | Config d un modele |
| GET | `/api/model/<id>/explore` | Vue d ensemble |
| GET | `/api/model/<id>/trees` | Table des arbres |
| GET | `/api/model/<id>/tree` | Structure d un arbre |
| GET | `/api/model/<id>/importance` | Feature importance |

---

## Modules Python (resume)

| Module | Role |
|--------|------|
| `schemas.py` | DatasetSchema et registre DATASETS (colonnes, cles, readonly, ordre sidebar logique) |
| `store.py` | Cache, pagination, coercion de types, projection schema, rebuild all_data |
| `join_data.py` | Grille et jointures all_data (filtre hotels avec ventes) |
| `sales_prep.py` | Agregation tickets bruts et split holidays |
| `geo_weather.py` | Meteostat multi-stations, rebuild weather |
| `geo_proximity.py` | Overpass, rebuild proximity |
| `geo_holidays.py` | Calendrier scolaire et feries FR |
| `parallel_*.py` | Variantes paralleles France (shards + merge) |
| `model_data.py` | Filtre, roles de colonnes, split annee eval |
| `model_train.py` | XGBoost multi-sortie, design et deploy |
| `model_explore.py` | Dump arbres XGBoost, metriques cumulees |
| `concept_pilote.py` | Indicateurs annuels pilotes |
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

Wizard multi-etapes pour un directeur d hotel :

1. Identite hotel (code, marque, adresse).
2. Services et equipements.
3. Clients et mix.
4. Corner (metres lineaires, offre).
5. Enrichissement automatique (geocode, meteo, proximite, holidays) via les services user.
6. Calcul revenus (rules/revenue), couts (rules/costs), recommandation de concept.

Le moteur revenus et le moteur couts sont separes pour pouvoir faire evoluer l un sans l autre.

API user : voir `user/app.py` (endpoints concept_pilote, simulation, catalogue).

---

## Contexte

Projet interne d analyse et de simulation retail / corner pour hotels Accor (ROD).
L archive historique sous `../archive/` conserve les pipelines de preparation de donnees d origine.
