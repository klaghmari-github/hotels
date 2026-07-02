# ROD-IA — Simulateur retail Accor

Application web comparant le **simulateur ROD Excel** (mois moyen pilote × 12) à une **prédiction IA** (profil mensuel entraîné sur l'historique), avec évaluation sur l'année en cours (2026).

## Séparation init / run

| Script | Rôle |
|--------|------|
| **`./init.sh`** | **Construit** tout : extraction Excel, références ROD, marques/nb hôtels, targets IA (moyennes mensuelles + %), feature store pivots, entraînement XGBoost, évaluation ROD vs IA, doc web |
| **`./run.sh`** | **Consomme** uniquement : lance le serveur Flask avec les artefacts déjà produits |
| **`./test.sh`** | **Tests unitaires** pytest (séparé de init — peut être long) |

```bash
./init.sh          # une fois (ou après mise à jour données/code)
./run.sh           # http://127.0.0.1:5000
./test.sh          # tests unitaires (optionnel)
```

Documentation code générée : http://127.0.0.1:5000/docs

**Journal des consignes** : [`docs/v1.md`](docs/v1.md) — historique des demandes, réponses et roadmap IA.

## Architecture

```text
rod_ia/
  config/              Settings (chemins, POI 0.1–0.5 km)
  domain/
    models/            HotelIdentity, SimulationResult, PerformanceReport…
    rules/             Revenus / coûts / recommandation (traçables Excel)
    repositories/      Registre identité, feature store, références
    services/
      sales_targets_pipeline.py   # Targets IA OOP (train < 2026, val 2026)
      model_trainer.py            # Entraînement XGBoost (init.sh)
      model_evaluation_service.py # ROD vs IA sur pivots
      rod_excel_extractor.py      # Extraction SIMULATEUR * depuis Excel
      pivot_store_enricher.py     # Feature store pivots
      simulation_orchestrator.py  # 3 concepts SIMPLY/LIBERTY/CONNECTED
  pipelines/
    run_init.py          # Orchestrateur pipeline init
    build_ml_dataset.py  # CLI dataset (délègue à SalesTargetsPipeline)
  api/                   # Flask + routes /simulate /performance /brands
  web/                   # UI + docs/ (généré)
data/
  reference/             # rod_reference.json, brand_projections.json, registre
  processed/             # X_descriptive.csv, y_targets.csv, performance_report.json
sources/raw/             # Excel ROD, CSV ventes (immuable)
```

## Principes métier

1. **Excel ROD** = source de vérité simulateur (feuille SIMULATEUR * = **mois moyen**, annuel = × 12)
2. **Config store** = **sortie** (proposée par concept), pas une entrée utilisateur
3. **Jointures** uniquement via `hotel_id` (`data/reference/hotel_identity_registry.json`)
4. **IA train** : moyenne mensuelle historique (années &lt; 2026) par mois / TYPE / GAMME + répartitions % (3 niveaux)
5. **IA validation** : CA réel 2026 **sur les mois présents** ; prédictions ramenées à la même période ; réel annualisé par règle de 3 (×12/n mois)
6. **ROD par hôtel** : scaling Excel Règle 1 — clients/mois = chambres × TO × guests × 30.5
7. **ML** : colonnes `d_*` (features) / `t_*` (targets), dont `t_m{mm}_ca_total` globaux
8. **Récap ROD** : variables `d_recap_*` extraites de `Récapitulatif … ROD (2).xlsx`, imputées puis sélectionnées

## Récap ROD dans le dataset ML

Source : `sources/raw/Récapitulatif de l'ensemble des données ROD (2).xlsx` (feuille `RECAP DATA ROD`).

| Étape | Service | Sortie |
|-------|---------|--------|
| Extraction | `RodRecapExtractor` | `data/reference/rod_recap.*` (wide/long/schema) |
| Imputation | `FeatureImputer` | `data/processed/imputation_report.json` |
| Sélection | `FeatureSelector` | `data/processed/feature_selection_report.json` |

**Stratégies d'imputation** (trous du récap, hôtels hors fichier inclus) :

| Type | Stratégie | Justification |
|------|-----------|---------------|
| Booléen (BAR, SPA, corner…) | `0` | Absence = équipement / option non présent |
| TO | Pilote marque (`BRAND_TO_DEFAULT`) | Aligné Excel ROD quand TO non renseigné |
| Guests/chambre | Pilote marque (`BRAND_GUESTS_DEFAULT`) | Valeurs pilotes Accor |
| Nb chambres | Registre identité | `hotel_identity_registry.json` |
| Panier moyen | CA train / ventes train | Historique ventes &lt; 2026 |
| Taux acheteur | Ventes / clients hébergés | Règle Excel C21 |
| Autres numériques | Médiane globale hôtels renseignés | Proxy conservateur |
| Catégorielles (texte) | Exclues de X | Non encodées — pas de fuite d'identité |

Variables dérivées ajoutées : `d_clients_mois`, `d_taux_acheteur`, `d_taux_occupation`, `d_guests_per_chambre`.

**Sélection** : retrait des `d_*` à variance nulle (même valeur toutes lignes) et des doublons exacts.

## Pipeline init détaillé (`./init.sh`)

1. `RodExcelExtractor` → `data/reference/rod_reference.json` (cellules SIMULATEUR *)
2. `BrandProjectionsExtractor` → `data/reference/brand_projections.json` (NB CH 1, règles reco)
3. `RodRecapExtractor` + `SalesTargetsPipeline.build_training_dataset()` → `data/processed/` (train &lt; 2026, `d_recap_*` imputées)
4. `PivotStoreEnricher` → `rod_ia/feature_store/hotels/{hotel_id}/` (targets + refs ROD)
5. `ModelTrainer.train()` → `rod_ia/artifacts/model.joblib`
6. `ModelEvaluationService.evaluate()` → `data/processed/performance_report.json`
7. `scripts/generate_code_docs.py` → `rod_ia/web/docs/index.html`

## Classe IA documentée

`SalesTargetsPipeline` (`rod_ia/domain/services/sales_targets_pipeline.py`) :

- `build_training_monthly_avg()` — moyennes train (exclude validation_year)
- `build_validation_actuals()` — réels année validation
- `build_training_dataset()` — dataset ML `d_*` / `t_*`
- `persist_hotel_targets()` — feature store par pivot

Ne pas utiliser les brouillons `old/` — tout passe par cette pipeline.

## API

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/health` | Santé |
| POST | `/api/simulate` | 3 concepts ROD + IA + recommandation |
| POST | `/api/enrich` | POI + météo → feature store |
| GET | `/api/performance` | Évaluation ROD vs IA (année validation) |
| GET | `/api/brands` | Statistiques marques / nb hôtels (Excel) |
| GET | `/api/sales-catalog` | Catégories TYPE / sous-catégories GAMME (CSV ventes) |
| GET | `/docs` | Documentation code web |

## Affichage CA (cohérence UI)

| Source | Mois moyen | Annuel |
|--------|------------|--------|
| ROD | `ca_mensuel_moyen` (plat sur graphique) | `ca_mensuel_moyen × 12` |
| IA | `ca_annuel / 12` ou profil 12 mois | `Σ monthly.ca` |

Le graphique compare toujours des **montants mensuels** ; les KPI détaillent mois moyen **et** annuel.

## Tests

```bash
./test.sh
# ou ciblé :
./test.sh tests/test_simulation.py
```

## Documentation projet

- Architecture : `docs/analyse_architecture_cible_rod_ia.md`
- Audit : `docs/documentation_fonctionnelle_audit_ROD_v2.md`
- Code web : `./init.sh` puis http://127.0.0.1:5000/docs