# Catalogue des modules Python

Package installable : `src/accor/` (layout src, voir `pyproject.toml`).

Imports : `from accor.store import get_frame`, `from accor.user.app import app`, …

---

## Racine package

| Module | Rôle |
|--------|------|
| `__init__.py` | version, réexport chemins |
| `data_io.py` | chemins PROJECT_ROOT/DATA_DIR/…, read_excel, codes hôtel, filtre FR |
| `schemas.py` | `DatasetSchema` + `DATASETS` (onglets admin) |
| `store.py` | cache DataFrame, pagination, CRUD Excel, rebuild join wrapper |
| `app.py` | Flask admin, toutes les routes `/api/*` admin |
| `join_data.py` | construit `all_data.xlsx` |
| `sales_prep.py` | raw tickets → ventes mensuelles |
| `model_data.py` | all_data → model_data (rôles, eval, impute) |
| `impute_model.py` | imputation ML par catégorie marque |
| `brand_category.py` | catégories, pilotes, voisins de gamme |
| `model_train.py` | XGBoost multi-output, design, deploy, batch UI + progress |
| `model_explore.py` | arbres, importance (structure modèle) |
| `model_eval.py` | **éval ML** année incomplete (somme/12) |
| `rod_admin.py` | **Simulateur ROD admin** : trace ventes, coûts/marge, éval sim vs réel |
| `concept_pilote.py` | indicateurs annuels hôtel × année |
| `geo_common.py` | hotels/sales/années/mois pour rebuilds geo |
| `geo_weather.py` | Meteostat → hotel_weather_data |
| `geo_proximity.py` | Overpass → hotel_proximity_data |
| `geo_holidays.py` | fériés + vacances → hotel_holidays_data |

---

## scrape_accor/

| Module | Rôle |
|--------|------|
| `__init__.py` | package scrape unitaire |
| `hotels.py` | `fetch_hotel`, `parse_hotel_html`, écriture xlsx plage (legacy) |
| `http_util.py` | fetch HTTP avec UA / erreurs |
| `README.md` | usage prod |

---

## user/

| Module | Rôle |
|--------|------|
| `__init__.py` | package simu |
| `app.py` | Flask user :5056 |
| `models.py` | dataclasses `SimulationRequest`, `HotelOperating`, résultats… |
| `reference.py` | `RodReference` lit `rod_reference.json` |
| `validate_rod.py` | checks non-régression (entry point `accor-validate-rod`) |

### user/rules/

| Module | Rôle |
|--------|------|
| `coeffs.py` | coefs règle 3, labels besoins, mapping marques, besoins LIBERTY |
| `revenue.py` | `RevenueRules` — chaîne TO → R1–R4 → marge produit |
| `costs.py` | `CostRules` — lignes capex/opex par concept |
| `recommendation.py` | concepts autorisés + meilleure marge nette |

### user/services/

| Module | Rôle |
|--------|------|
| `catalog.py` | `AdminCatalog` — brands, search hotels, defaults model |
| `geocode.py` | BAN → Accor → Nominatim |
| `enrich.py` | coords + proximity + weather + holidays pour 1 hôtel |
| `hotel_context.py` | agrège admin → indicateurs d’entrée simu |
| `hotel_fetch.py` | scrape + upsert hotel_data si code inconnu |
| `simulator.py` | `RodSimulator` : revenus + coûts pour 1 concept |
| `orchestrator.py` | multi-concepts + reco (`POST /api/simulate`) |

---

## Points d’entrée CLI

| Entry (`pyproject.toml`) | Cible |
|--------------------------|--------|
| `accor-admin` | `accor.app:main` |
| `accor-user` | `accor.user.app:main` |
| `accor-validate-rod` | `accor.user.validate_rod:main` |

Wrappers racine : `run_admin.py`, `run_user.py`.

---

## Dépendances externes (rappel)

- Flask — HTTP
- pandas / openpyxl — Excel
- scikit-learn / xgboost — modèles
- requests — Overpass / HTTP divers
- meteostat — météo (optionnel à l’import : graceful si absent)
