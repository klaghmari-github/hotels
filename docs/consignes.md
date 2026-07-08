# Consignes ROD-IA

Document de référence : consignes métier, état d’implémentation et évolutions prévues.

Dernière mise à jour : 2026-07-08

**Code actif** : répertoire `rod_ia/` à la racine du dépôt. Le dossier `old/` n’est pas utilisé en production.

**Documentation technique** : [`README.md`](../README.md) · [`docs/api_rest.md`](api_rest.md) · [`docs/rod_rules.md`](rod_rules.md)

---

## 1. Hiérarchie des sources de vérité

| Priorité | Source | Rôle |
|----------|--------|------|
| 1 | Excel ROD (`sources/raw/`) | Règles revenus, coûts, marges, recommandation concept |
| 2 | Ce fichier et `README.md` | Consignes produit et architecture |
| 3 | `001.queryVentes.csv` | Ventes réelles — entraînement modèle et évaluation 2026 |
| 4 | `old/`, notebooks | Audit uniquement |

Aucune constante métier n’est définie en dehors des sources ci-dessus.

---

## 2. Points d’entrée applicatifs

| Script | Port | Public | Contenu |
|--------|------|--------|---------|
| `run_server.py` | 5000 | Directeur d’hôtel | Simulateur : saisie, résultats ROD, prédictions, recommandation |
| `run_admin.py` | 5001 | Équipe technique | Exploration, interprétation, évaluation, documentation code |
| `run_api.py` | 5002 | Intégration | API REST `POST /api/v1/predict` |
| `./init.sh` | — | Installation | Extraction, dataset, entraînement, évaluation |
| `./test.sh` | — | Qualité | Tests unitaires pytest |

`./run.sh` est un raccourci vers le simulateur utilisateur (équivalent à `run_server.py`).

---

## 3. Principes métier

| Principe | Détail | Statut |
|----------|--------|--------|
| Config store = sortie | Proposée par concept (m_lin, mix F&B), pas saisie directe | Implémenté |
| 3 concepts | SIMPLY, LIBERTY, CONNECTED comparés à chaque simulation | Implémenté |
| ROD = mois moyen | Feuille SIMULATEUR * = pilote plat ; annuel = × 12 | Implémenté |
| Modèle = profil mensuel | 12 mois distincts prédits par XGBoost | Implémenté |
| ROD par hôtel | `clients/mois = chambres × TO × guests × 30.5` | Implémenté |
| Jointure `hotel_id` | Registre `hotel_identity_registry.json` | Implémenté |
| Feature store | `rod_ia/feature_store/hotels/{hotel_id}/` | Implémenté |
| Entraînement | Historique ventes &lt; 2026 | Implémenté |
| Évaluation 2026 | Mois présents uniquement ; règle de trois pour annualiser | Implémenté |
| POI proches | Rayons 0,1 à 0,5 km | Implémenté |
| Traçabilité règles | Lien Python ↔ cellule Excel (`RuleTrace`) | Partiel |

---

## 4. Consignes par thème

### 4.1 Simulation

Comparer les règles ROD Excel et le modèle de prédiction sur les trois concepts. Afficher coûts, marges et recommandation (meilleure marge nette ROD parmi les concepts autorisés).

Composants : `SimulationOrchestrator`, `RodSimulator`, `AIPnlService`.

Interface utilisateur : parcours en cinq étapes (informations hôtel → simulation de revenu). Pas d’accès à l’exploration, l’interprétation ni l’évaluation.

### 4.2 Récapitulatif ROD dans le modèle

Intégrer les variables du fichier Récapitulatif Excel. Imputer les valeurs manquantes. Exclure les variables constantes.

| Étape | Service | Sortie |
|-------|---------|--------|
| Extraction | `rod_recap_extractor.py` | `data/reference/rod_recap.*` |
| Imputation | `feature_imputer.py` | `imputation_report.json` |
| Sélection | `feature_selector.py` | `feature_selection_report.json` |
| Fusion | `sales_targets_pipeline.py` | `d_recap_*` dans `X_descriptive.csv` |

### 4.3 Modèle de prédiction

| Élément | Valeur |
|---------|--------|
| Algorithme | `MultiOutputRegressor(XGBRegressor)` |
| Features | Colonnes `d_*` |
| Cibles | 24 globales mensuelles (CA et ventes) |
| Artefacts | `rod_ia/artifacts/model.joblib` |

Page d’interprétation : `/interpretation` sur le serveur d’administration (port 5001).

### 4.4 API REST

Endpoint `POST /api/v1/predict` : reçoit les paramètres hôtel, consulte le feature store (plage, commerces, météo), applique les règles ROD et renvoie les prédictions par concept avec la recommandation. Voir [`docs/api_rest.md`](api_rest.md).

### 4.5 Enrichissement géographique

`EnrichHotelService` calcule la distance à la plage (`d_nearest_beach_m`), les commerces de proximité et la météo mensuelle. Les résultats sont mis en cache dans le feature store.

### 4.6 Mix produits

Catégories F&B / non-F&B. Sous-catégories = GAMME du fichier ventes. Sliders 0–100 %. API catalogue : `GET /api/sales-catalog`.

---

## 5. Évolutions prévues

### Features

| Action | Statut |
|--------|--------|
| Distance plage dans le feature store | Fait |
| Fusion POI/météo/plage dans `X_descriptive.csv` à l’initialisation | En cours |
| Variables ventes dérivées (panier, top gammes) | Planifié |

### Modèle

| Action | Statut |
|--------|--------|
| Hiérarchie cible : CA global puis résiduel % type/gamme | Planifié |
| Régularisation et validation leave-one-hotel-out | Planifié |
| Combinaison modèle + ROD par marque | Planifié |

### Données

| Action | Statut |
|--------|--------|
| Extension du registre hôtels pivots | Planifié |
| Validation temporelle 2025 + test 2026 | Partiel |

---

## 6. Restrictions

- Ne pas utiliser `old/` comme source métier
- Ne pas sommer les ventes historiques par mois (utiliser des moyennes)
- Ne pas encoder de catégories texte du récap dans les features
- Ne pas traiter la config store comme entrée utilisateur
- Ne pas versionner `.venv`, `sources/raw/`, `*.joblib`
- Ne pas inventer de GAMME ou TYPE hors CSV ventes

---

## 7. Références

| Document | Rôle |
|----------|------|
| [`README.md`](../README.md) | Architecture, flux, composants |
| [`docs/api_rest.md`](api_rest.md) | API REST de prédiction |
| [`docs/rod_rules.md`](rod_rules.md) | Règles simulateur ROD et évaluation |
| [`docs/exploration_interface.md`](exploration_interface.md) | Guide page Exploration |
| `rod_ia/web/docs/index.html` | Documentation code (produite par `init.sh`) |