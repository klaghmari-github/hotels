# Synthèse archive/ — code historique rod_ia, sources brutes, docs, références

**Date d’exploration** : 2026-07-25  
**Workspace** : `/media/laghmari/ssd-data/dev/hotels`  
**Périmètre** : dossier `archive/` (lecture seule) ; comparaison avec `accord/` pour le portage.

---

## 1. Rôle de `archive/` vs `accord/`

| Dimension | `archive/` | `accord/` |
|-----------|------------|-----------|
| **Statut** | Application historique **ROD-IA** complète (simulateur + ML + admin + API) | Application **nouvelle**, self-contained (« Data & Model Studio » + wizard user) |
| **Runtime** | Peut encore démarrer (`run_server.py` :5000, `run_admin.py` :5001, `run_api.py` :5002) mais n’est **plus le produit cible** | Runtime actif : `run_admin.py` :5055, `run_user.py` :5056 |
| **Rôle monorepo** | **Legacy / inspiration / sources de vérité brutes** | **Produit courant** |
| **Dépendance croisée** | Contient les Excel/CSV métier originaux | Ne dépend pas de `archive/` au runtime ; lit `archive/` **ponctuellement** (import ventes, extraction coûts) |

### Sources de vérité (hiérarchie historique, encore valide pour l’audit métier)

1. **Excel ROD** dans `archive/sources/raw/` — règles revenus, coûts, marges, reco concept  
2. **Docs** (`archive/docs/`, `README.md`) — consignes produit et architecture  
3. **`001.queryVentes.csv`** — ventes réelles (train IA &lt; 2026, holdout 2026)  
4. Constantes extraites → `data/reference/rod_reference.json` (intermédiaire traçable)

### Comment lire `archive/` aujourd’hui

| Usage | Contenu utile |
|-------|----------------|
| **Inspirational / UI cible** | Screenshots `sources/raw/docs/ecran_sim/` (onboarding ROD officiel Accor) ; parcours 5 étapes du wizard |
| **Legacy exécutable** | Package `rod_ia/` + `init.sh` + tests pytest |
| **Sources de vérité métier** | Excel simulateurs/paramètres/récap + CSV ventes (immuables) |
| **Références dérivées** | `data/reference/*`, `data/processed/*`, artefacts ML |
| **Pont vers accord** | `scripts/run_sales_and_sync_accord.py`, `accord/extract_couts.py`, `accord/sales_prep.ensure_raw_sales_from_archive()` |

Citation `accord/README.md` :

> Le dossier `../archive/` (pipelines prepare historiques, sources brutes, etc.) n’est **pas** requis au runtime, sauf scripts utilitaires d’extraction ponctuelle (ex. coûts).

---

## 2. Structure `rod_ia/`

Application Python structurée **domain-driven** (config / domain / pipelines / api / web).

```
archive/rod_ia/
├── config/settings.py          # Chemins, POI 0.1–0.5 km, Nominatim/Overpass, evaluation_year
├── domain/
│   ├── models/                 # identity, hotel, store, simulation, enrichment, prediction_api
│   ├── repositories/           # identity_registry, reference_repository, feature_store_repository
│   ├── rules/                  # revenue, cost, financing, recommendation, coeffs, traceability
│   └── services/               # ~29 services (extraction, ML, simulation, enrich…)
├── pipelines/
│   ├── run_init.py             # Orchestrateur ./init.sh
│   ├── build_ml_dataset.py
│   └── train_model.py
├── api/                        # Flask factories + routes
│   ├── app_factory.py          # modes user / admin
│   ├── api_factory.py          # API REST autonome
│   ├── dependencies.py         # AppContainer DI
│   └── routes/                 # simulate, prediction, enrich, exploration, train, …
├── web/                        # HTML/JS/CSS simulateur + admin + exploration + interpretation
├── artifacts/                  # model.joblib, neural_*, feature/target cols, meta
└── feature_store/hotels/{id}/  # geo, recap, sales_targets, simulations history
```

### Domain rules (`domain/rules/`)

| Fichier | Rôle |
|---------|------|
| `revenue_rules.py` | `RodRevenueRules` — impact TO + Règles Excel 1→4 + marge produit |
| `cost_rules.py` | `RodCostRules` — techno + annexes + agencement (amort. 84 mois) |
| `financing_cost_rules.py` | Lease vs buy (panneau détail UI) — chemin séparé du moteur H168 |
| `recommendation_rules.py` | Filtre SIMPLY/LIBERTY/CONNECTED + meilleure marge nette |
| `excel_category_coeffs.py` | Coeffs Règle 3 F&B/N-F&B, brands, `LIBERTY_NFB_NEEDS` |
| `traceability.py` | `RuleTrace` (workbook, sheet, cells ↔ méthode Python) |

### Domain services (groupes)

| Groupe | Services clés |
|--------|----------------|
| **Extraction** | `rod_excel_extractor`, `rod_recap_extractor`, `sales_catalog_service` |
| **Pipeline ML** | `sales_targets_pipeline`, `feature_imputer`, `feature_selector`, `ml_dataset_builder`, `ml_column_naming` |
| **Modèle** | `model_trainer` (XGBoost), `neural_model_trainer`, `ai_predictor`, `model_evaluation_service`, `model_interpretation_service`, `model_exploration_service` |
| **Simulation** | `rod_simulator`, `ai_pnl_service`, `simulation_orchestrator`, `optimizer`, `director_input_mapper`, `concept_detail_service` |
| **Enrichissement** | `enrich_hotel` (géo, POI, météo, plage), `pivot_store_enricher`, `hotel_feature_loader` |
| **API métier** | `prediction_api_service`, `data_exploration_service`, `param_wiring` |

### Web & API

| Entrée | Port | Public |
|--------|------|--------|
| `run_server.py` | 5000 | Directeur — wizard 5 étapes, simulation ROD + IA |
| `run_admin.py` | 5001 | Technique — exploration, interprétation, perf, docs, simulateur admin |
| `run_api.py` | 5002 | REST `POST /api/v1/predict` |

Routes principales : `/api/simulate`, `/api/optimize`, `/api/enrich`, `/api/sales-catalog`, `/api/performance`, `/api/model-interpretation`, `/api/data-exploration`, `/api/model-exploration/*`, `/api/v1/predict`.

### Pipelines init (`./init.sh` → `run_init.py`)

1. Extraction Excel → `rod_reference.json` + `brand_projections.json`  
2. Catalogue ventes → `sales_catalog.json`  
3. `SalesTargetsPipeline` → `X_descriptive.csv`, `y_targets.csv`  
4. Enrichissement feature store pivots  
5. Entraînement XGBoost → `artifacts/model.joblib`  
6. Évaluation 2026 → `performance_report.json`  
7. Doc code + smoke tests  

---

## 3. Fichiers bruts dans `archive/sources/raw/`

| Fichier | Rôle métier | Format | Tabulaire ? |
|---------|-------------|--------|-------------|
| **`001.queryVentes.csv`** | Ventes ticket-level (boutique, date, TYPE, GAMME, qty, prix TTC…). **Base train IA** (&lt; 2026) et **holdout terrain** (2026 jan–avr) | CSV, en-têtes : `NOM BOUTIQUE`, `DATE`, `TYPE`, `GAMME`, `QUANTITE`, `PRIX TTC`, … | **Oui — tabulaire** (lignes transactionnelles) |
| **`ROD - Simulateurs + détail des coûts.xlsx`** | Feuilles `SIMULATEUR SIMPLY/LIBERTY/CONNECTED`, `REVENUS - IMPACT TO`, grilles coûts. **Source n°1** des constantes pilotes et du moteur P&L | Classeur Excel à formules, cellules adressées (C9, E34, H168…) | **Non — non tabulaire** (simulateur cellulaire / formules métier) |
| **`ROD - Paramètres & règles + projections nb. d'hôtels.xlsx`** | Projections nb hôtels par marque/tranche de taille ; feuille `REGLES POUR RECO DU CONCEPT` | Excel multi-feuilles (stats + règles textuelles) | **Mixte** : stats marques plutôt tabulaires ; règles reco **non tabulaires** |
| **`Récapitulatif de l'ensemble des données ROD (2).xlsx`** | Variables descriptives hôtel (saisie directeur / fiche ROD) → features `d_recap_*` | Feuille `RECAP DATA ROD` : champs en lignes, hôtels en colonnes | **Non — matrice pivotée** (non tabulaire « tidy ») |
| **`Analyse du poids des catégories de produit (2024-2025).xlsm`** | Analyse métier des poids de catégories (référence, non consommée par le pipeline actif documenté) | Excel macro (.xlsm) | **Analyse / semi-tabulaire** (référence métier) |
| **`docs/consignes.md`** | Copie des consignes produit (version 2026-07-02) | Markdown | Doc |
| **`docs/ecran_sim/*.png`** | Captures UI onboarding ROD officiel (référence UX) | PNG | Screenshots |

**Note README** : un fichier `2026.02.Fevrier-ExportAccor.xlsx` est mentionné comme non consommé par le pipeline actif — **absent** de l’arborescence actuelle de `sources/raw/`.

### Traitement des formats non tabulaires

- **Simulateurs** → `RodExcelExtractor` lit des cellules nommées → `rod_reference.json`  
- **Récap** → `RodRecapExtractor` transpose en wide par `hotel_id` → `rod_recap.{wide,long,schema}`  
- **Paramètres** → `BrandProjectionsExtractor` → `brand_projections.json`  
- **CSV ventes** → pipelines `SalesMixExtractor` / `SalesTargetsPipeline` / (historique) `SalesPrep`

---

## 4. `docs/` — contenu métier

### 4.1 `rod_rules.md` (document d’audit le plus dense)

- Mapping Excel ↔ Python pour **REV-01…REV-19**, **COST-01…05**, **RECO-01…04**, **ORCH-01…05**, **IMP-01…07**  
- Principe **pilote concept puis projection** (pas de filtrage marque pour le CA ROD)  
- Formule consolidée (clients 30,5 j, impact TO, R1–R4, marge, coûts)  
- Méthode **test/évaluation 2026** : holdout strict, 4 mois, règle de 3, best-fit concept  
- Résultats panel (5 hôtels) : écart moyen |ROD| ~55 %, |IA| ~50 %  
- Exemples chiffrés Strasbourg SIMPLY, LIBERTY 200 ch, CONNECTED Tour Eiffel  

### 4.2 `consignes.md`

- Hiérarchie des sources de vérité  
- Points d’entrée (`run_server`, `run_admin`, `run_api`, `init`, `test`, `export`, **`run_prepare`**)  
- Principes : config store = **sortie**, 3 concepts, ROD mois moyen ×12, IA profil 12 mois  
- Thèmes : simulation, récap ML, modèle, API REST, enrichissement géo, mix produits  
- Backlog (fusion POI dans X, hiérarchie cibles ML, extension pivots…)  
- Restrictions : pas de `old/`, pas de sommes brutes de ventes, pas de config store en entrée  

### 4.3 `exploration_interface.md`

- Page admin `/exploration` (port 5001)  
- Onglet **Données** : 7 étapes (CSV → saisie → ROD/marques → météo/POI → X nettoyé → targets → %)  
- Onglet **Modèle** : visualisation arbres XGBoost (120 arbres × 24 sorties), prédiction interactive  
- Routes HTTP associées  

### 4.4 `api_rest.md`

- `POST /api/v1/predict` : structure d’entrée (identity, operating, general, services, client_profile, corner, constraints, store)  
- Réponse : 3 concepts + recommandation + contexte enrichi  

### 4.5 Autres docs

- `README.md` (racine archive) : architecture complète, mermaid, hyperparamètres XGBoost  
- `consignes.txt` : **spécification historique SalesPrep / prepare** (étapes 1.a–7, RodPrep…AllPrep)  
- `sources/raw/docs/consignes.md` : version antérieure des consignes (2026-07-02)

---

## 5. `data/reference/`

| Fichier / dossier | Producteur | Rôle |
|-------------------|------------|------|
| **`rod_reference.json`** | `RodExcelExtractor` | **Cœur métier** : pilotes par concept (chambres, TO, guests, m_lin, CA F&B/N-F&B, ventes, cost_lines, impact_to). Copié aussi dans `accord/data/` |
| `rod_reference_demo.json` | Fallback | Utilisé si extraction absente ; merge `fixed_capex` |
| `rod_reference_extracted.json` | `scripts/extract_excel_rules.py` | Audit Excel ↔ JSON (13 cellules clés) |
| **`brand_projections.json`** | `BrandProjectionsExtractor` | Effectifs hôtels par marque × bandes de taille (IBIS BUDGET 342, IBIS 362, …) |
| **`hotel_identity_registry.json`** | Manuel / init | **Clé de jointure** `hotel_id` : alias ventes/ROD, lat/lon, flags `has_sales`/`has_rod`, nb_chambres (~8+ hôtels pivots) |
| `sales_catalog.json` | `SalesCatalogService` | TYPES F&B / NON-F&B et GAMMES (ALCOOL, SOS, PAP…) pour sliders UI |
| `rod_recap.wide/long/schema` (+ sous-dossiers test) | `RodRecapExtractor` | Features récap brutes + schéma colonnes `d_recap_*` |
| `recomputed_sales_reference.json` | `recompute_sales_references.py` | Références ventes recalculées (audit) |

### Extrait pilotes (`rod_reference.json`)

| Concept | Chambres | Guests/ch | TO | m_lin | CA HT mensuel | Coût mensuel ~ |
|---------|----------|-----------|-----|-------|---------------|----------------|
| SIMPLY | 129 | 1,7 | 0,80 | 6 | 720 € | 247 € |
| LIBERTY | 142 | 2,2 | 0,70 | 8 | 1 479 € | 586 € |
| CONNECTED | 305 | 1,8 | 0,75 | 7 | 3 634 € | (lignes frigos+) |

`impact_to.ht_per_0_01_to` ≈ **9,234 €**.

### `data/processed/` (datasets ML)

- `X_descriptive.csv` (199 features `d_*`, 6 hôtels train)  
- `y_targets.csv` (328 targets dont 24 globales mensuelles utilisées par le modèle)  
- `performance_report.json`, `imputation_report.json`, `feature_selection_report.json`, etc.

---

## 6. Screenshots `ecran_sim` et UI archive

### 6.1 Captures `sources/raw/docs/ecran_sim/` (UI officielle Accor ROD)

Référence UX **produit métier** (marque « A ROD », onboarding 5 étapes), pas l’UI Flask archive elle-même. Hôtel exemple : **Ibis Alès Centre Ville**, user Julie Marin H0338.

| Fichier (horodatage 2026-07-02) | Contenu écran |
|--------------------------------|---------------|
| `15-52-56.png` | **Étape 1 — Informations générales** : marque, chambres, adultes/enfants, TO annuel, panier, rénovations, PMS, proximité commerces 100/500 m |
| `15-53-07.png` | **Étape 2 — Services & équipements** : F&B (bar, resto, minibar), NON-F&B (réunions, sport, spa, piscine), équipement lobby |
| `15-53-17.png` | **Étape 3 — Profil clients** : loisirs/affaires, national/international ; besoins assortiment F&B / NON-F&B (toggles) |
| `15-54-36.png` | **Étape 4 — Boutique/corner** : toggle « corner déjà existant ? » |
| `15-54-43.png` | **Étape 5 — Simulation** : sliders chambres/TO/m_lin, mix F&B 80 % / N-F&B 20 %, toggles catégories, bouton SIMULER |
| `15-54-56.png` | **Résultats** : reco LIBERTY (89 € marge nette), alternatives SIMPLY 488 € / CONNECTED 1 063 € |
| `16-53-44.png` | **Détail SIMPLY** : lease/buy, agencement classique/premium/sur-mesure €/m², qty scanner/vitrine |
| `17-03-05.png` | **Détail LIBERTY** : caisse 250 €/mois, vitrine 13 €/mois, amortissement 48 mois |

Ces écrans alimentent directement le mapping UI → `DirectorInputMapper` / règles R3 (besoins clients) et `FinancingCostRules` (lease/buy).

### 6.2 UI applicative archive (`rod_ia/web/`)

| Fichier | Rôle |
|---------|------|
| `index.html` + `script.js` | Simulateur user (parcours 5 étapes aligné sur ecran_sim) |
| `admin.html`, `admin-simulator.html` | Admin + simulateur technique + perf |
| `exploration.html/js` | Exploration dataset & arbres |
| `interpretation.html/js` | Importances XGBoost + règles |
| `style.css` | Styles |

Différence clé : l’UI archive **ajoute** comparaison **ROD vs IA** (profil 12 mois) et pages techniques absentes de l’onboarding Accor.

---

## 7. Règles ROD — synthèse (code + docs)

### 7.1 Revenus (R1–R4 + impact TO)

**Clients hébergés / mois** :

```
clients = nb_chambres × TO × guests_per_chambre × 30.5
```

Enchaînement Excel (colonnes O du SIMULATEUR), implémenté dans `RodRevenueRules.compute` :

1. **Impact TO** : `(TO_hôtel − TO_pilote) / 0.01 × 9,234 €` réparti F&B / N-F&B  
2. **Règle 1** : scale CA par `clients_hôtel / clients_pilote` ; ventes = taux acheteur pilote × clients hôtel  
3. **Règle 2** : ajustement mix ±10 % d’écart au mix pilote (`MIX_STEP = 0.10`)  
4. **Règle 3** : bonus/malus selon cumul coeffs catégories cochées vs baseline « tout coché » (FB ≈ 0,48 ; NFB ≈ 0,34)  
5. **Règle 4** : ± `(CA_ref / m_lin_pilote) × |Δ m_lin|`  
6. **Marge produit** : `CA − CA/coef` (coefs J9/J10, ex. F&B 2,6 / N-F&B 1,45 SIMPLY)  

Profil temporel ROD : **mois moyen plat** → annuel = mensuel × 12.

### 7.2 Coûts

- **Techno** (scanner/caisse/frigos, licence, OS…)  
- **Annexes** (élec, staff…)  
- **Agencement** : capex/m × m_lin, amorti **84 mois** (H166 = E166/84)  
- Total mensuel ≈ **H168** Excel  
- **Financement alternatif** (`FinancingCostRules`) : lease 36 mois, agencement €/m² classique 12 / premium 14 / sur-mesure 26 — panneau détail UI, hors moteur H168 par défaut  

### 7.3 Recommandation SIMPLY / LIBERTY / CONNECTED

| Règle | Logique |
|-------|---------|
| **#1 taille** | &lt; 50 ch → **SIMPLY** seul ; ≥ 50 → LIBERTY et/ou CONNECTED |
| **Exception IBB** | Ibis Budget &lt; 200 ch : SIMPLY aussi proposé |
| **#2 catégories** | LIBERTY si ≥ 1 besoin parmi cosmétiques / kids / apparel / accessories / souvenirs |
| **Note NOV/MER** | Avertissement si Novotel/Mercure sans catégories N-F&B lifestyle |
| **Choix final** | Parmi concepts **autorisés**, celui à la **meilleure marge nette ROD** |

Les 3 concepts sont **toujours simulés** pour comparaison ; la reco filtre le sous-ensemble admissible.

### 7.4 Orchestration

`SimulationOrchestrator` : pour chaque concept → `build_store_for_concept` (m_lin, mix) → `RodSimulator` + `AIPnlService` → `recommend`.

---

## 8. Tests présents

Répertoire : `archive/tests/` — lanceur `./test.sh` (pytest).

| Fichier | Couverture |
|---------|------------|
| `test_revenue_rules.py` | R1 pivot, R2 mix, R3 catégories, R4 m_lin |
| `test_recommendation_rules.py` | SIMPLY &lt;50, LIBERTY/CONNECTED, IBB mid-size, blocage N-F&B |
| `test_simulation.py` | Orchestration 3 concepts, pipeline |
| `test_financing_cost_rules.py` | Lease/buy |
| `test_director_inputs.py` | Mapping besoins → excluded gammes, m_lin |
| `test_operating_state.py` | clients_mois, TO % |
| `test_identity_registry.py` | Résolution noms ventes/ROD |
| `test_sales_catalog.py` / `test_sales_percentages.py` | Catalogue & % |
| `test_enrich_hotel.py` / `test_beach_distance.py` | POI, cache, plage |
| `test_model_trainer.py` / `test_model_evaluation.py` / `test_neural_model_trainer.py` | ML XGB + neural + eval 2026 |
| `test_exploration_api.py` / `test_prediction_api.py` | HTTP admin + REST |
| `test_recap_features.py` | Features récap / RodPrep |
| `test_ml_column_naming.py` | Convention `d_*` / `t_*` |
| `test_run_export.py` | ZIP audit |
| **`test_prepare_package.py`** | Package `prepare` (imports, chemins, pipeline mock) |
| **`test_sales_prep.py`** | SalesPrep agrégations |
| **`test_meteo_prep.py`** / **`test_proximity_prep.py`** / **`test_holidays_prep.py`** | Étapes prepare géo/calendrier |
| `test_join_no_dup.py` | Jointures sans duplication colonnes |

**Point critique** : les tests `prepare.*` importent un package Python `prepare/` déclaré dans `pyproject.toml` (`include = ["prepare*"]`, script `run-prepare`). **Dans l’état actuel du disque, le code source du package `prepare/` est absent** (seul reste `prepare/SalesPrep/Output/hotel_sales_data.xlsx`). Les tests prepare sont donc **cassés / orphelins** tant que le package n’est pas restauré.

---

## 9. Porté / réimplémenté dans `accord/` vs archive-only

### Porté / réimplémenté (avec simplification)

| Capacité archive | Équivalent accord |
|------------------|-------------------|
| Règles revenus R1–R4 + impact TO | `accord/user/rules/revenue.py` (`RevenueRules`) |
| Coeffs catégories + brands | `accord/user/rules/coeffs.py` |
| Coûts techno/annexes/agencement | `accord/user/rules/costs.py` |
| Recommandation concept | `accord/user/rules/recommendation.py` |
| Simulateur unitaire | `accord/user/services/simulator.py` (`RodSimulator`) |
| Orchestrateur 3 concepts | `accord/user/services/orchestrator.py` |
| `rod_reference.json` | `accord/data/rod_reference.json` |
| Wizard directeur 5 étapes | `accord/templates/user/` + `run_user.py` :5056 |
| Enrichissement géo / météo / proximité | `geo_weather.py`, `geo_proximity.py`, `geo_holidays.py`, `user/services/enrich.py` |
| Préparation ventes (esprit SalesPrep) | `accord/sales_prep.py` (indépendant, s’inspire de l’ancien) |
| Jointure multi-sources | `join_data.py` → `all_data.xlsx` |
| Dataset ML + XGBoost | `model_data.py`, `model_train.py`, `model_explore.py` |
| Extraction coûts one-shot depuis Excel archive | `extract_couts.py` → `data/couts.xlsx` |
| Sync / import ventes depuis archive | `sales_prep.ensure_raw_sales_from_archive()`, `sync_data_files.py` |

**Choix d’architecture accord** : revenus et coûts **découplés** volontairement (swap IA futur sur les seuls revenus).

### Archive-only (non porté ou non équivalent)

| Élément | Détail |
|---------|--------|
| **Pipeline IA P&L dual** | `AIPnlService` : prédiction XGB 24 sorties puis même P&L que ROD — absent en tant que tel dans le wizard user accord |
| **Feature store par hôtel** | `rod_ia/feature_store/hotels/{id}/` (geo, targets, history.jsonl) |
| **Modèle neural** | `neural_model_trainer.py`, artefacts keras |
| **API REST autonome** | `run_api.py` `/api/v1/predict` |
| **Admin exploration / interprétation arbres** | pages dédiées archive |
| **Traçabilité `RuleTrace`** | lien cellule Excel systématique |
| **`FinancingCostRules` lease/buy détaillé** | partiel côté UI Accor screenshots ; moteur séparé archive |
| **Package `prepare/` complet** | RodPrep, MeteoPrep, ProximityPrep, HolidaysPrep, SalesPrep, AllPrep — **code source manquant** |
| **Export audit ZIP** | `run_export.py` + snapshot `exports/rod-ia-audit-20260708-…` |
| **Registre identité JSON** | remplacé par Excel `hotel_data.xlsx` côté accord |
| **Récap ROD → features d_recap_*** | pipeline imputation/sélection spécifique archive |
| **Évaluation holdout 2026 formalisée** | `ModelEvaluationService` + `performance_report.json` |
| **Docs audit métier** | `docs/rod_rules.md`, etc. |

### Ponts runtime archive → accord

```
archive/sources/raw/001.queryVentes.csv
    → accord/sales_prep.ensure_raw_sales_from_archive()
    → hotel_sales_raw_data.xlsx / hotel_sales_data.xlsx

archive/sources/raw/ROD - Simulateurs….xlsx
    → accord/extract_couts.py → data/couts.xlsx

archive/scripts/run_sales_and_sync_accord.py
    → SalesPrep (si package dispo) → copie hotel_sales_data → join_data accord
```

---

## 10. Pipelines prepare historiques

### Spécification (`consignes.txt` + `docs/consignes.md`)

Chaîne prévue :

```
RodPrep → MeteoPrep → ProximityPrep → HolidaysPrep → SalesPrep → AllPrep
```

| Step | Dossier | Rôle |
|------|---------|------|
| 1 | `RodPrep` | Excel récap → hotel_lookup (code, nom, géo) |
| 2 | `MeteoPrep` | Météo mensuelle 2024–2025(+), imputation N←N−1 |
| 3 | `ProximityPrep` | Commerces + plage (rayons) |
| 4 | `HolidaysPrep` | Fériés / vacances scolaires |
| 5 | `SalesPrep` | Agrégats ventes 1.a–7 (annuel, mensuel, cat/sous-cat, weekend, holiday) + jointure ; holdout dernière année (2026) |
| 6 | `AllPrep` | Jointure sur `hotel_code` (+ année/mois) sans dupliquer les lignes sales |

Entrée CLI : `run_prepare.py` → `prepare.__main__:main` (déclaré aussi `run-prepare` dans pyproject).

### Traces restantes sur disque

| Trace | État |
|-------|------|
| `archive/prepare/SalesPrep/Output/hotel_sales_data.xlsx` | **Présent** (artefact de sortie) |
| `archive/run_prepare.py` | Stub d’import `prepare.__main__` |
| `archive/scripts/run_sales_and_sync_accord.py` | Bridge SalesPrep → accord |
| Tests `test_*_prep.py`, `test_prepare_package.py` | Présents, attendent le package |
| `pyproject.toml` include `prepare*` | Déclare le package |
| **Sources Python `prepare/rod_prep`, `sales_prep`, …** | **Absents** de l’arborescence actuelle |

### Remplacement dans accord

La logique prepare est **re-scindée** en modules plats :

- `sales_prep.py` — ventes  
- `geo_weather.py` / `geo_proximity.py` / `geo_holidays.py`  
- `join_data.py` — All Data  
- `model_data.py` — dataset ML  

→ Plus de dossiers `RodPrep/Input|Output|Src` ; données finales sous `accord/data/*.xlsx`.

---

## Annexes

### A. Arborescence top-level `archive/`

```
archive/
├── README.md, consignes.txt, pyproject.toml, requirements.txt
├── init.sh, run.sh, test.sh, zip.sh
├── run_server.py, run_admin.py, run_api.py, run_export.py, run_prepare.py
├── rod_ia/                 # application
├── sources/raw/            # Excel + CSV + ecran_sim
├── data/reference|processed/
├── docs/
├── tests/
├── scripts/
├── prepare/                # vestige Output SalesPrep seulement
└── exports/                # snapshot audit 2026-07-08
```

### B. Deux moteurs de prédiction (archive)

| Moteur | Nature | Temporalité | Source |
|--------|--------|-------------|--------|
| ROD Excel | Déterministe | Mois moyen ×12 | `rod_reference.json` |
| IA XGBoost | ML MultiOutput 24 sorties | Profil 12 mois | `artifacts/model.joblib` |

Hyperparamètres XGB : `n_estimators=120`, `max_depth=4`, `lr=0.08`, `subsample=0.9`, `colsample_bytree=0.9`.

### C. Fichiers de référence croisés

- `/media/laghmari/ssd-data/dev/hotels/archive/README.md`  
- `/media/laghmari/ssd-data/dev/hotels/archive/docs/rod_rules.md`  
- `/media/laghmari/ssd-data/dev/hotels/archive/docs/consignes.md`  
- `/media/laghmari/ssd-data/dev/hotels/archive/data/reference/rod_reference.json`  
- `/media/laghmari/ssd-data/dev/hotels/accord/README.md`  
- `/media/laghmari/ssd-data/dev/hotels/accord/user/rules/*.py`  

---

*Rapport généré par exploration lecture seule de `archive/` ; aucune modification sous `archive/`.*
