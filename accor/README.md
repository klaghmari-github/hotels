# Accor ROD — package production (`accor/`)

Application web prete pour la prod : **donnees propres deja construites** + interfaces admin / user.

L historique complet (rebuilds massifs France, shards, scrapes bulk) est archive dans
`../accor_1_0_0/`. Ce dossier ne garde que l essentiel pour faire tourner le produit.

---

## Demarrage

```bash
cd accor
pip install -r requirements.txt

python run_admin.py   # http://127.0.0.1:5055
python run_user.py    # http://127.0.0.1:5056

# Verifie regles ROD (revenus R1–R4, couts, reco)
python -m user.validate_rod
```

### Imputation prediction (categorie de marque)

Quand une feature numerique manque pour le modele (`impute_model`) :

1. moyenne des **hotels pilotes** (ventes) de la **meme categorie** de marque  
   (`economy` / `midscale` / `premium` / `luxury` / …) ;
2. sinon moyenne des pilotes des categories **directement inferieure et superieure**  
   (ex. luxury sans pilote → premium ; economy → midscale ; lifestyle → midscale+premium) ;
3. sinon moyenne de tous les pilotes, puis moyenne globale.

Pilotes = codes presents dans `hotel_sales_data.xlsx`.  
Module : `brand_category.py` + `impute_model.py`.  
Colonne audit : `brand_category` (id_detail, pas une feature).

Meme logique pour `nb_chambres` / TO manquants dans le wizard user (`hotel_context`).

### Simulateur ROD (run_user) — chaine de calcul

1. **Clients** : `nb_chambres × TO × guests × 30.5`
2. **Impact TO** puis **R1** (scaling clients vs pilote concept)
3. **R2 mix** F&B / non-F&B (si mix corner saisi ; sinon mix pilote du concept)
4. **R3 categories** (besoins clients vs baseline Excel)
5. **R4 m_lin** (ecart vs pivot concept)
6. **Marge produit** : `CA − CA/coef` par canal
7. **Couts** techno + annexes + agencement × m_lin
8. **Reco** : filtres taille/marque/N-F&B lifestyle, puis meilleure marge nette

Les cartes etape 1 (rule1) n affichent que impact TO + R1 ; l etape 5 applique R2–R4 + couts.

---

## Ce qui est en prod

| Domaine | Contenu |
|---------|---------|
| Donnees Excel | brand, hotel, proximity, holidays, weather, sales raw/agregees, all_data, model_data, concept_pilote, couts, rod_reference, logos marques |
| Admin UI | Consultation / edition des tables, Model Build, Model Explore |
| User UI | Wizard 5 etapes + simulation ROD |
| Ventes | Raw + pipeline `sales_prep` (transformation) |
| ML | model_data, model_train, model_explore, models/design + deploy |
| Scrape hotel | **A la demande** si le code n existe pas dans hotel_data |
| Enrichissement simu | geo_* pour un point (meteo / proximite / holidays) si besoin |

## Ce qui est retire (ou masque)

| Element | Statut |
|---------|--------|
| Rebuilds massifs France (`parallel_*`) | Absents (reste dans accor_1_0_0) |
| Sync bulk marque / hotel / alignement | Absents |
| Scrape catalogue pays / world / workers | Absents |
| Shards / state weather-holidays-proximity | Non copies |
| Boutons **Reconstruire** dans l admin | **Masques** (API et modules Python conserves) |

Pour reafficher un rebuild avance : renseigner `REBUILD_TABS` dans
`static/js/admin/constants.js` (ids `sales`, `weather`, …).

---

## Scrape hotel a la demande

URL Accor : `https://all.accor.com/hotel/{code}/index.fr.shtml`

Flux user :

1. Saisie d un code hotel (autocomplete ou champ libre).
2. `GET /api/hotels/<code>/context`
3. Si present dans `hotel_data` → profil local.
4. Sinon `user.services.hotel_fetch.fetch_and_upsert_hotel` :
   - `scrape_accor.hotels.fetch_hotel`
   - map vers colonnes hotel_data
   - upsert Excel + invalidation cache
5. UI : toast « Hotel recupere depuis Accor ».

Module : `user/services/hotel_fetch.py`  
Scrape : `scrape_accor/hotels.py` + `http_util.py`

---

## Arborescence essentielle

```
accor/
  run_admin.py / run_user.py
  app.py, store.py, schemas.py, data_io.py
  sales_prep.py          # raw → sales (garde)
  join_data.py           # all_data (rebuild API masquee)
  model_data.py / model_train.py / model_explore.py
  concept_pilote.py
  geo_*.py               # enrichissement ponctuel simu
  impute_model.py        # utilise par model_data
  scrape_accor/hotels.py # fiche unitaire
  user/                  # wizard + regles + hotel_fetch
  static/                # front OOP admin + user
  data/                  # Excel propres (sans shards)
  models/                # design + deploy
```

---

## API utiles

### Admin (port 5055)

- Datasets : `GET/PUT/POST/DELETE /api/datasets/...`
- Rebuilds (conserves, non exposes UI) : `POST /api/datasets/<id>/rebuild`
- Modeles : `/api/model/*`

### User (port 5056)

| Route | Role |
|-------|------|
| `GET /api/hotels/search` | Autocomplete |
| `GET /api/hotels/<code>/context` | Profil (+ scrape si absent) |
| `POST /api/simulate` | Simulation ROD |
| `POST /api/geocode` | Lat/lon |
| `POST /api/rule1` | CA regle 1 |
| `GET /api/concept_pilote/brand/<marque>` | Moyennes marque |

---

## Front

- Admin : `static/js/admin/app.js` (ES modules)
- User : `static/user/js/modules/app.js`
- Shared : `static/shared/js/*`

Bouton rebuild : `id="btn-rebuild"` reste en `hidden` ; `REBUILD_TABS = empty`.

---

## Archive

| Dossier | Role |
|---------|------|
| `accor/` | **Prod** (ce package) |
| `accor_1_0_0/` | Version complete avec pipelines de construction de donnees |
| `archive/` | Anciens pipelines / sources brutes |

Ne pas reintroduire les rebuilds massifs dans ce package sans besoin operationnel.
