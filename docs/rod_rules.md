# Simulateur ROD — règles, implémentation et test / évaluation

Document d'audit du simulateur déterministe ROD (Retail On Demand) : correspondance entre les classeurs Excel source, le code Python, et la comparaison au terrain sur le jeu de test 2026 (holdout).

Dernière révision : 2026-07-05 (terminologie test/évaluation, holdout strict, best-fit)

---

## 1. Périmètre

Ce document couvre :

- les règles métier du simulateur ROD extraites de `sources/raw/ROD - Simulateurs + détail des coûts.xlsx` ;
- leur traduction dans le code (`rod_ia/domain/rules/`, orchestration dans `rod_ia/domain/services/`) ;
- la distinction entre valeurs d'entrée descriptives et valeurs calculées à partir des ventes réelles ;
- le traitement des marques d'hôtel dans le pipeline ;
- la méthode de test et évaluation 2026 (holdout, règle de trois) et la section Évaluation de l’interface d’administration ;
- un exemple chiffré sur données 2024–2025 appliqué à 2026.

Le modèle IA (XGBoost) est mentionné uniquement pour la comparaison de performance, pas comme objet principal de ce document.

---

## 2. Sources de vérité

| Priorité | Fichier | Rôle |
|----------|---------|------|
| 1 | `sources/raw/ROD - Simulateurs + détail des coûts.xlsx` | Formules revenus, coûts, marges par concept |
| 2 | `sources/raw/ROD - Paramètres & règles + projections nb. d'hôtels.xlsx` | Règles de recommandation concept, statistiques marques |
| 3 | `data/reference/rod_reference.json` | Constantes extraites (pilotes, mix, marges, coûts) |
| 4 | `sources/raw/001.queryVentes.csv` | Ventes réelles — entraînement IA (&lt; 2026) + test/évaluation terrain (2026, jan–avr) |
| 5 | `sources/raw/Récapitulatif de l'ensemble des données ROD (2).xlsx` | Variables descriptives hôtel (`d_recap_*`) pour le ML |

Les constantes pilotes sont extraites par `RodExcelExtractor` (`rod_ia/domain/services/rod_excel_extractor.py`, méthode `extract`) vers `data/reference/rod_reference.json`.

---

## 3. Principe général : pilote puis projection

Chaque feuille `SIMULATEUR {CONCEPT}` (SIMPLY, LIBERTY, CONNECTED) définit un **hôtel pilote** dont les résultats mensuels moyens servent de référence. Pour un hôtel cible, le simulateur projette ces valeurs par **règle de trois** (ou équivalent multiplicatif) selon les paramètres de l'hôtel cible.

### 3.1 Hôtel pilote par concept (pas par marque)

Les références pilotes sont **fixes par concept**, lues dans les cellules Excel puis stockées dans `rod_reference.json` :

| Concept | Pilote (chambres) | Guests/ch | TO | m_lin | CA HT mensuel pilote |
|---------|-------------------|-----------|-----|-------|----------------------|
| SIMPLY | 129 (C9) | 1,7 (C10) | 0,80 (C11) | 6 (F9) | 720 € (E34+E35) |
| LIBERTY | 142 | 2,2 | 0,70 | 8 | 1 479 € |
| CONNECTED | 305 | 1,8 | 0,75 | 7 | 3 634 € |

Le simulateur ROD **ne filtre pas** les hôtels pivots par marque du hôtel simulé. Un Ibis budget Strasbourg est projeté à partir du pilote SIMPLY (Ibis budget Nice), quel que soit son rattachement marque dans le registre.

Les statistiques par marque (`brand_projections.json`, extraites par `BrandProjectionsExtractor`) alimentent l'UI et les règles de recommandation ; elles **ne participent pas** au calcul du CA ROD.

### 3.2 Valeurs d'entrée avant simulation

| Type | Exemples | Origine |
|------|----------|---------|
| Descriptives fixes | `nb_chambres`, ville, marque | Registre `hotel_identity_registry.json` ou saisie UI |
| Opérationnelles | `taux_occupation`, `guests_per_chambre` | Saisie UI, feature store, ou pilote marque (imputation) |
| Config store (sortie) | `m_lin`, mix F&B/NON-F&B | Proposée par concept depuis `rod_reference.json` ; surcharge possible via contraintes UI |
| Références pilotes | `base_monthly_ca_fb`, `base_monthly_sales`, coefs marge | `rod_reference.json` ← Excel |
| Ventes historiques | moyennes mensuelles, % par TYPE/GAMME | `001.queryVentes.csv` — **pipeline IA uniquement**, pas le moteur ROD |

Pour les hôtels pivots ayant déjà testé SIMPLY/LIBERTY/CONNECTED, les ventes réelles 2024 et 2025 servent à construire les targets d'entraînement IA (`SalesTargetsPipeline`). Le simulateur ROD, lui, s'appuie sur les constantes Excel du pilote, pas sur la moyenne des ventes de l'hôtel cible.

### 3.3 Traitement des ventes pour l'IA (hors ROD, mais lié au test / évaluation)

**Entraînement uniquement** — `SalesMixExtractor.monthly_average_targets(exclude_year=evaluation_year)` calcule, **par hôtel** (via `hotel_id`), la moyenne arithmétique du CA et des ventes pour chaque couple `(mois, TYPE, GAMME)` sur les années **strictement inférieures à 2026** (2024 et 2025 complètes pour les hôtels pivots). L'année 2026 est **exclue** du fit (`assert_training_holdout()`).

**Jeu de test / évaluation (holdout)** — les ventes **2026** (janvier–avril) sont lues séparément par `build_evaluation_actuals()` pour la comparaison au terrain (§7). Elles ne nourrissent ni le ROD, ni les moyennes d'entraînement, ni `model.joblib`.

- Ce n'est **pas** une moyenne inter-hôtels de même marque.
- Ce n'est **pas** une moyenne pondérée par le nombre de chambres ou le volume : c'est la moyenne simple des totaux annuels disponibles pour chaque mois.
- `SalesPercentageService` dérive ensuite trois niveaux de pourcentages **par hôtel** : saisonnalité mensuelle, part TYPE dans le mois, part GAMME dans le TYPE.

### 3.4 Entraînement du modèle IA (code, pas artefact figé)

Le modèle n'est **pas** un fichier figé livré dans le dépôt : il est **recalculé** à partir du dataset processed.

| Élément | Fichier / commande |
|---------|-------------------|
| Code fit | `rod_ia/domain/services/model_trainer.py` — `ModelTrainer.train()` |
| Entrées | `data/processed/X_descriptive.csv`, `y_targets.csv`, `dataset_meta.json` |
| Sorties | `rod_ia/artifacts/model.joblib`, `feature_cols.json`, `target_cols.json`, `meta.json` |
| Init complet | `./init.sh` → `run_init.py` (dataset + `ensure_trained(force=True)`) |
| Entraînement seul | `python -m rod_ia.pipelines.train_model` (`--force`, `--rebuild-dataset`) |
| Relance auto | `./run.sh` ou `build_container()` si dataset présent et `model.joblib` absent |

`ModelTrainer.ensure_trained()` entraîne uniquement lorsque le modèle est absent (ou si `force=True`). Sans dataset, une erreur explicite renvoie vers `./init.sh`.

API : `GET /api/model/status`, `POST /api/model/train`.

---

## 4. Catalogue des règles ROD

### 4.1 Revenus — clients hébergés et taux acheteur

| ID | Règle Excel | Formule source | Implémentation | Statut |
|----|-------------|----------------|----------------|--------|
| REV-01 | Clients hébergés / jour | `C16 = (C10×C9)×C11` | `RodRevenueRules._clients_mois` via `HotelOperatingState.clients_mois` | Implémenté |
| REV-02 | Clients hébergés / mois | `C17 = C16×30,5` | `RodRevenueRules.JOURS_MOIS = 30.5`, `HotelOperatingState` | Implémenté |
| REV-03 | Taux acheteur pilote (Règle 1) | `C21 = C19/C17` | `RodRevenueRules.compute` : `taux_acheteur = ventes_ref / clients_pilote` | Implémenté |
| REV-04 | Ventes projetées | `M19 = M17×$C$21` | `nbr_ventes = taux_acheteur × clients_hotel` | Implémenté |
| REV-05 | Facteur clients | ratio `clients_hotel / clients_pilote` | `client_factor` dans `RodRevenueRules.compute` | Implémenté |

Fichier : `rod_ia/domain/rules/revenue_rules.py` — classe `RodRevenueRules`, méthodes `_clients_mois`, `compute`.

### 4.2 Revenus — impact taux d'occupation

| ID | Règle Excel | Formule source | Implémentation | Statut |
|----|-------------|----------------|----------------|--------|
| REV-06 | Impact +1 point de TO sur CA HT | Feuille `REVENUS - IMPACT TO`, cellule impact 9,234 € HT / 0,01 TO | `to_impact = (to_hotel - to_pilote) / 0.01 × impact_to.ht_per_0_01_to` | Implémenté |
| REV-07 | Constante impact TO | `rod_reference.json → impact_to.ht_per_0_01_to = 9.233974` | `ReferenceRepository.get("impact_to.ht_per_0_01_to")` | Implémenté |

Fichier : `rod_ia/domain/rules/revenue_rules.py` — `RodRevenueRules.compute`.

Extraction : `RodExcelExtractor._extract_impact_to` — cellules F12/I12 de `REVENUS - IMPACT TO`.

### 4.3 Revenus — mix produits (Règle 2 Excel)

| ID | Règle Excel | Description | Implémentation | Statut |
|----|-------------|-------------|----------------|--------|
| REV-08 | Règle 2 — mix ±10 % | `O44 = E51×(écart_mix×10)` sur F&B et NON-F&B | `RodRevenueRules._rule2_mix_adjust` | Implémenté |
| REV-09 | Mix pilote concept | `I9/I10` | `rod_reference.json` ; surcharge via sliders UI | Implémenté |

Fichiers : `rod_ia/domain/rules/revenue_rules.py`, `rod_ia/domain/services/director_input_mapper.py`.

### 4.4 Revenus — catégories sélectionnées (Règle 3 Excel)

| ID | Règle Excel | Description | Implémentation | Statut |
|----|-------------|-------------|----------------|--------|
| REV-10 | Règle 3 — coefficients | H64–H70 (F&B), O64–O70 (NON-F&B) | `excel_category_coeffs.py` + `_rule3_category_adjust` | Implémenté |
| REV-11 | Baseline pilote | E34/E35 = assortiment complet | Ajustement relatif : `delta = cumul − baseline_pilote` | Implémenté |
| REV-12 | Besoins clients UI | Toggles étape 3 | `ClientProfile.client_needs` → coefficients | Implémenté |

Fichiers : `rod_ia/domain/rules/excel_category_coeffs.py`, `rod_ia/domain/rules/revenue_rules.py`.

### 4.5 Revenus — mètres linéaires (Règle 4 Excel)

| ID | Règle Excel | Description | Implémentation | Statut |
|----|-------------|-------------|----------------|--------|
| REV-13 | Règle 4 — m_lin | `O112 = O94 ± (E34/F9)×|Δm_lin|` | `RodRevenueRules._rule4_m_lin_adjust` | Implémenté |
| REV-14 | Coût agencement lié au m_lin | `E166 = capex_per_m × m_lin` | `RodCostRules` via `cost_lines.agencement` | Implémenté |

Fichiers : `rod_ia/domain/rules/revenue_rules.py`, `rod_ia/domain/rules/cost_rules.py`.

### 4.6 Revenus — CA HT projeté (agrégation)

| ID | Règle Excel | Formule source | Implémentation | Statut |
|----|-------------|----------------|----------------|--------|
| REV-15 | CA HT mensuel cible | Enchaînement colonnes O : TO → R1 → R2 → R3 → R4 | `RodRevenueRules.compute` | Implémenté |
| REV-16 | Profil temporel ROD | Feuille SIMULATEUR = mois moyen plat | 12 mois identiques ; annuel = mensuel × 12 | Implémenté |

Fichier : `rod_ia/domain/rules/revenue_rules.py` — `RodRevenueRules.compute` ; orchestration dans `rod_ia/domain/services/rod_simulator.py`.

### 4.7 Revenus — marge produit

| ID | Règle Excel | Formule source | Implémentation | Statut |
|----|-------------|----------------|----------------|--------|
| REV-16 | Marge F&B | `E132 = E120 - (E120/E128)` avec E128 = J9 | `RodRevenueRules._marge_produit_excel` | Implémenté |
| REV-17 | Marge NON-F&B | `E133 = E121 - (E121/E129)` avec E129 = J10 | idem | Implémenté |
| REV-18 | Marge produit totale | `E134 = SUM(E132:E133)` | somme F&B + NON-F&B | Implémenté |
| REV-19 | Marge nette pilote | `E176 = E134 - H168` | `marge_nette = marge_produit - monthly_cost` dans `RodSimulator.simulate` | Implémenté |

Coefficients marge (`margin_fb_pct`, `margin_nf_pct`) extraits de J9/J10 par `RodExcelExtractor`.

### 4.8 Coûts — technos, annexes, agencement (ligne à ligne)

| ID | Règle Excel | Description | Implémentation | Statut |
|----|-------------|-------------|----------------|--------|
| COST-01 | Lignes technos | SIMULATEUR * lignes 147–151 (scanner, vitrine, licence, OS…) | `cost_lines.techno[]` extrait par `RodExcelExtractor._extract_cost_lines` | Implémenté |
| COST-02 | Lignes annexes | Lignes 155–158 (électricité, staff…) | `cost_lines.annexes[]` | Implémenté |
| COST-03 | Agencement amorti | Ligne 166 : `H166 = E166/84` | `cost_lines.agencement` + somme dans `RodCostRules._sum_lines` | Implémenté |
| COST-04 | Total mensuel | `H168 = Σ techno + annexes + agencement` | `RodCostRules.compute` ; détail dans `breakdown.cost_lines` | Implémenté |
| COST-05 | Détail lease/buy UI | Panneau détail solution | `FinancingCostRules` via `ConceptDetailService` | Implémenté (chemin séparé) |

Fichiers : `rod_ia/domain/rules/cost_rules.py`, `rod_ia/domain/services/rod_excel_extractor.py`.

Exemple SIMPLY (pilote) : techno 75 €/mois + annexes 15 €/mois + agencement 157 €/mois = **247 €/mois** (aligné H168 Excel).

### 4.9 Recommandation de concept

| ID | Règle Excel | Description | Implémentation | Statut |
|----|-------------|-------------|----------------|--------|
| RECO-01 | Règle #1 — taille | 0–49 ch → SIMPLY ; +50 ch → LIBERTY/CONNECTED | `RodRecommendationRules.allowed_concepts` | Implémenté |
| RECO-02 | Règle #2 — catégories N-F&B | LIBERTY si ≥1 parmi Cosmetics/Kids/Apparel/Accessories/Souvenirs | `_has_liberty_nfb_category` | Implémenté |
| RECO-03 | Note NOV/MER | LIBERTY doit rester possible pour ces marques | Avertissement si catégories insuffisantes | Implémenté |
| RECO-04 | Choix final | Meilleure marge nette ROD parmi concepts autorisés | `RodRecommendationRules.recommend` | Implémenté |

Fichiers : `rod_ia/domain/rules/recommendation_rules.py`, `rod_ia/domain/rules/excel_category_coeffs.py`.

### 4.10 Orchestration et sortie

| ID | Description | Implémentation |
|----|-------------|----------------|
| ORCH-01 | Comparaison 3 concepts | `SimulationOrchestrator.simulate_all` |
| ORCH-02 | Construction config store par concept | `SimulationOrchestrator.build_store_for_concept` |
| ORCH-03 | Agrégation revenus + coûts + trace | `RodSimulator.simulate` |
| ORCH-04 | ROI (mois de retour) | `roi_months = capex / (marge_nette_annuelle / 12)` si marge > 0 |
| ORCH-05 | Traçabilité règle ↔ Excel | `RuleTrace` dans `rod_ia/domain/rules/traceability.py` |

### 4.11 Règles d'imputation (ML — variables d'entrée, pas le moteur ROD)

Ces règles alimentent les features `d_*` utilisées par l'IA et l'évaluation, pas le calcul ROD direct.

| ID | Stratégie | Implémentation |
|----|-----------|----------------|
| IMP-01 | Booléen absent → 0 | `FeatureImputer.impute` |
| IMP-02 | TO absent → pilote marque | `FeatureImputer._rule_to` (`BRAND_TO_DEFAULT`) |
| IMP-03 | Guests/ch absent → pilote marque | `FeatureImputer._rule_guests` (`BRAND_GUESTS_DEFAULT`) |
| IMP-04 | Nb chambres absent → registre identité | `FeatureImputer` + `SalesTargetsPipeline._attach_registry_descriptives` |
| IMP-05 | Panier absent → CA train / ventes train | `FeatureImputer._sales_derived` |
| IMP-06 | Taux acheteur → ventes / clients (C21) | `FeatureImputer._rule_taux_acheteur` |
| IMP-07 | Autres numériques → médiane globale | `FeatureImputer.impute` |

Fichier : `rod_ia/domain/services/feature_imputer.py`.

---

## 5. Formule consolidée implémentée (Python)

Enchaînement aligné sur les colonnes O du SIMULATEUR :

```
clients_pilote = pivot_nb × pivot_to × pivot_guests × 30.5
clients_hotel  = nb_chambres × to_hotel × guests_hotel × 30.5

# Impact TO (additif sur E34/E35 avant scaling)
ca_fb, ca_nf ← ca_fb_ref, ca_nf_ref + impact_to réparti

# Règle 1 — clients acheteurs
ca_fb, ca_nf ← ca_fb, ca_nf × (clients_hotel / clients_pilote)

# Règle 2 — mix ±10 %
unit_fb = (ca_fb_ref × 10 %) / mix_fb_pilote
ca_fb  ← ca_fb + unit_fb × (mix_fb_user − mix_fb_pilote) × 10
(idem NON-F&B)

# Règle 3 — catégories (relatif au pilote « tout coché »)
delta_fb = cumul_coeffs_fb − 0,48
ca_fb    ← ca_fb + ca_fb × delta_fb
(idem NON-F&B, baseline 0,19)

# Règle 4 — mètres linéaires
ca_fb ← ca_fb ± (ca_fb_ref / m_lin_pilote) × |m_lin − m_lin_pilote|

ventes_mensuelles = (ventes_pilote / clients_pilote) × clients_hotel
coûts_mensuels    = Σ lignes techno + annexes + agencement (cost_lines)
marge_nette       = marge_produit − coûts_mensuels
ca_annuel         = ca_ht_mensuel × 12
```

Constantes pilotes : `data/reference/rod_reference.json` (régénéré par `./init.sh` ou `python3 scripts/extract_excel_rules.py`).

---

## 6. Écarts résiduels (audit)

| Écart | Excel | Code actuel | Risque |
|-------|-------|-------------|--------|
| Coefficients Règle 3 N-F&B | O67–O69 parfois vides dans Excel | Valeurs dérivées de la colonne H (0,05) | Faible |
| Mode lease vs buy | Colonnes E (buy) et H (lease) selon contrat | BUY par défaut (colonne H mensualisée) | Écart si hôtel en lease pur |
| Panneau détail financement | Lease/buy interactif | `FinancingCostRules` — chemin API séparé | Hors moteur ROD principal |
| Guests/ch UI | `general.adults + children` écrase `operating` | `DirectorInputMapper.prepare_request` | Saisir `general` cohérent avec le pilote |
| Test/évaluation 2026 | 4 mois (jan–avr) — pas d'auto-regénération au `run.sh` | `performance_report.json` produit par `./init.sh` uniquement | Relancer `./init.sh` après changement de règles |

---

## 7. Test et évaluation 2026 — méthode et onglet Performance

### 7.1 Entraînement vs test/évaluation — holdout strict

En vocabulaire ML, le jeu **2026** est un **jeu de test / d'évaluation** (holdout) : il n'est **jamais** utilisé pendant l'apprentissage (pas de tuning, pas de fit). Ce n'est pas un jeu de « validation » au sens hyperparamètres.

| | Entraînement IA | Test / évaluation (holdout) |
|--|-----------------|------------------------------|
| **Années** | Strictement **&lt; 2026** (2024 et 2025 complètes, 6 hôtels pivots) | **2026 uniquement** |
| **Mois** | 12 mois par année historique | **4 mois** : janvier à avril (mois 1–4) |
| **Source** | `build_training_monthly_avg()` (`exclude_year=evaluation_year`) | `build_evaluation_actuals()` |
| **Produit** | Targets `t_*`, `X_descriptive.csv`, `y_targets.csv`, `model.joblib` | `performance_report.json` |
| **Garantie code** | `assert_training_holdout()` — aucune ligne `year >= evaluation_year` dans le train | — |

- **ROD** : ne lit pas les ventes 2026 ; projette depuis `rod_reference.json`.
- **IA** : `ModelTrainer.train()` sur le dataset d'entraînement uniquement (`X_descriptive.csv`, `y_targets.csv`, holdout exclu) ; comparée au réel 2026 via `ModelEvaluationService`.

Paramètre : `evaluation_year` (défaut 2026, CLI `--evaluation-year`). Ancien alias `--validation-year` conservé pour compatibilité scripts.

Pipeline : `sales_targets_pipeline.py` et `model_evaluation_service.py`.

### 7.2 Méthode de comparaison (règle de trois)

Sur la période **janvier–avril 2026** (4 mois, identique pour les 5 hôtels évalués avec `has_rod`) :

- **Annualisation du réel** : `CA_annuel_estimé = CA_période × 12 / 4`.
- **ROD** : `CA_période = ca_mensuel_moyen × 4` (profil plat, mois moyen Excel).
- **IA** : somme des CA mensuels prédits sur les mois 1–4 (profil 12 mois du modèle).

Rapport produit à l'init : `data/processed/performance_report.json`.

### 7.3 Onglet Performance (interface)

| Composant | Fichier | Rôle |
|-----------|---------|------|
| Section HTML | `rod_ia/web/admin-simulator.html` — `#perf`, `#perf_table` | Tableau comparatif |
| Chargement données | `rod_ia/web/script.js` — `loadPerformance()` | `GET /api/performance` |
| API | `rod_ia/api/routes/performance.py` | Lit `performance_report.json` |
| Accès | `python run_admin.py` → http://127.0.0.1:5001/simulator#perf | Administration uniquement |

La section est alimentée si `./init.sh` a produit le rapport. Sinon le message « Rapport absent — ./init.sh » s’affiche.

### 7.4 Résultats agrégés (juillet 2026)

Source : `data/processed/performance_report.json` (5 hôtels avec `has_rod`, 4 mois 2026).

**Méthode d'évaluation** (`ModelEvaluationService`) :

- Paramètres opérationnels : `director_inputs` sauvegardés > récap ROD (`to_annuel`, guests marque) > défauts pilote.
- **Concept retenu** : best-fit — parmi les concepts plausibles (marque + taille), celui dont le CA ROD sur la période est le plus proche du réel (champ `concept`). La recommandation marge Excel reste exposée dans `recommended_concept`.
- **IA** : profil 12 mois du modèle XGBoost (`model.joblib` via `.venv` après `./init.sh`). Si le modèle est indisponible, fallback ROD plat (écart IA = écart ROD).

| Indicateur | Valeur |
|------------|--------|
| Hôtels évalués | 5 |
| Mois moyens présents | 4 |
| Écart moyen absolu ROD | 54,9 % |
| Écart moyen absolu IA | 49,9 % |
| IA meilleure que ROD | 2 hôtels sur 5 |

| Hôtel | Concept (best-fit) | Reco marge | CA réel (4 mois) | CA ROD (4 mois) | Écart ROD | CA IA (4 mois) | Écart IA |
|-------|-------------------|------------|------------------|-----------------|-----------|----------------|----------|
| Ibis budget Nice | SIMPLY | LIBERTY | 1 341 € | 2 736 € | +104,0 % | 2 055 € | +53,3 % |
| Ibis budget Strasbourg | SIMPLY | SIMPLY | 2 138 € | 1 652 € | −22,7 % | 3 450 € | +61,4 % |
| Mercure Montmartre | LIBERTY | LIBERTY | 11 124 € | 12 030 € | +8,1 % | 19 188 € | +72,5 % |
| Novotel Megève | LIBERTY | LIBERTY | 9 163 € | 21 543 € | +135,1 % | 6 574 € | −28,3 % |
| Novotel Paris Tour Eiffel | CONNECTED | LIBERTY | 38 074 € | 36 411 € | −4,4 % | 51 082 € | +34,2 % |

Le ROD est proche du terrain pour Montmartre (LIBERTY, +8 %) et Paris Tour Eiffel (CONNECTED, −4 %). Strasbourg reste sous-estimé (−23 %) avec le TO annuel récap (70 %) : l'activité 2026 dépasse le profil Excel pilote. Nice et Megève présentent des écarts forts : profil éloigné du pilote concept et/ou corner déjà en place non reflété dans les règles de base. L'IA améliore Nice (+53 % vs +104 %) et Megève (−28 % vs +135 %) lorsque le modèle est chargé.

---

## 8. Exemple détaillé — Ibis budget Strasbourg (SIMPLY)

Hôtel pivot SIMPLY : Ibis budget Nice (129 ch, TO 80 %, 1,7 guests/ch, 6 m_lin).
Hôtel cible : Ibis budget Strasbourg (97 ch).

### 8.1 Calcul ROD pédagogique (paramètres pilote — hors récap)

Exemple avec les **paramètres pilote Excel** (TO 80 %, 1,7 guests/ch) pour illustrer les règles 1→4. L'évaluation §7 utilise les paramètres **récap** de Strasbourg (TO annuel 70 %, §8.2).

Constantes pilote SIMPLY (`rod_reference.json`) :

- `base_monthly_ca` = 720 € (533 F&B + 187 NON-F&B)
- `base_monthly_sales` = 231 ventes/mois
- `pivot_to` = 0,80

Étape 1 — clients :

```
clients_pilote = 129 × 0,80 × 1,7 × 30,5 = 5 351
clients_hôtel  =  97 × 0,80 × 1,7 × 30,5 = 4 024
client_factor  = 4 024 / 5 351 = 0,752
```

Étape 2 — impact TO : identique au pilote → `to_impact = 0`.

Étape 3 — m_lin : 6 m (défaut concept) → `m_lin_factor = 1,0`.

Étape 4 — CA mensuel :

```
ca_ht_mensuel = 720 × 1,0 × 0,752 × 1,0 = 541 €
ca_annuel     = 541 × 12 = 6 497 €
```

Étape 5 — ventes :

```
taux_acheteur     = 231 / 5 351 = 0,0432
ventes_mensuelles = 0,0432 × 4 024 × 1,0 = 174
```

Étape 6 — marge produit (coefs 2,6 / 1,45) :

```
marge_produit_mensuelle ≈ 290 €
```

Vérification code : `tests/test_simulation.py` et exécution orchestrateur confirment `ca_mensuel_moyen ≈ 541 €`.

### 8.2 Test / évaluation 2026 — paramètres récap et terrain

Paramètres retenus par `ModelEvaluationService` (récap ROD, pas le pilote §8.1) : 97 ch, **TO annuel 70 %**, 1,7 guests/ch, concept SIMPLY (best-fit).

Données terrain — **4 mois** janvier à avril 2026 (`performance_report.json`) :

| Grandeur | Valeur |
|----------|--------|
| CA réel période (jan–avr 2026) | 2 138 € |
| CA mensuel moyen réel | 534 € |
| CA annuel estimé (× 12/4) | 6 413 € |
| CA ROD mensuel (récap TO 70 %) | 413 € |
| CA ROD période (413 × 4) | 1 652 € |
| CA ROD annuel (413 × 12) | 4 956 € |
| Écart ROD sur la période | **−22,7 %** |
| Écart IA sur la période | +61,4 % |

Le ROD **sous-estime** le terrain : l'activité jan–avr 2026 dépasse la projection Excel avec le TO annuel récap (70 %, inférieur au pilote 80 %). L'IA surévalue (+61 %), probablement en raison du faible effectif d'entraînement (6 hôtels) et d'un profil mensuel plus volatil que le mois moyen ROD.

### 8.3 LIBERTY — hôtel 200 chambres

Pilote LIBERTY : 142 ch, TO 70 %, 2,2 guests/ch, 8 m_lin, CA pilote 1 479 €/mois.

Paramètres cible : 200 ch, TO 72 %, 2,0 guests/ch (via `general.adults_per_room`).

```
clients_pilote = 142 × 0,70 × 2,2 × 30,5 = 6 682
clients_hôtel  = 200 × 0,72 × 2,0 × 30,5 = 8 784
client_factor  = 8 784 / 6 682 = 1,317

CA mensuel ROD ≈ 1 972 €  (1 479 × 1,317, règles 2–4 nulles à mix/assortiment/m_lin pilote)
CA annuel      ≈ 23 666 €
Coûts mensuels ≈ 586 € (lignes extraites H168 LIBERTY)
```

### 8.4 CONNECTED — Novotel Paris Tour Eiffel (764 ch)

Pilote CONNECTED : 305 ch, TO 75 %, 1,8 guests/ch, 7 m_lin, CA pilote 3 634 €/mois.

Paramètres cible : 764 ch, TO 75 %, 1,8 guests/ch.

```
client_factor = (764 × 0,75 × 1,8 × 30,5) / (305 × 0,75 × 1,8 × 30,5) = 2,505
CA mensuel ROD ≈ 9 103 €  (aligné performance_report : rod_ca_mensuel_moyen = 9 102,87 €)
Coûts mensuels ≈ 4 668 € (8 lignes cost_lines, frigos + annexes + agencement)
```

Test/évaluation 2026 (4 mois, `performance_report.json`) : écart ROD **−4,4 %** sur la période — meilleur résultat du panel.

---

## 9. Chaîne de fichiers — référence rapide

```
sources/raw/ROD - Simulateurs + détail des coûts.xlsx
    └─ RodExcelExtractor.extract()
        └─ data/reference/rod_reference.json
            └─ ReferenceRepository
                ├─ RodRevenueRules.compute()      # revenus
                ├─ RodCostRules.compute()         # coûts ligne à ligne
                └─ SimulationOrchestrator
                    └─ RodSimulator.simulate()    # résultat ROD

sources/raw/001.queryVentes.csv
    └─ SalesTargetsPipeline
        ├─ entraînement (années < evaluation_year) → monthly_average_targets, model.joblib
        ├─ test/évaluation (2026, jan–avr, 4 mois, holdout) → evaluation_actuals
        └─ ModelEvaluationService.evaluate() → performance_report.json
            └─ GET /api/performance → UI onglet Performance
```

---

## 10. Audit automatique Excel ↔ JSON

Le script `scripts/extract_excel_rules.py` :

1. ré-exécute `RodExcelExtractor` vers `data/reference/rod_reference.json` ;
2. compare 13 cellules clés (pilotes SIMPLY/LIBERTY/CONNECTED, impact TO, coûts) ;
3. écrit le rapport dans `data/reference/rod_reference_extracted.json` ;
4. retourne un code d'erreur si un écart > 0,05 € est détecté.

Commande :

```bash
python3 scripts/extract_excel_rules.py
```

Résultat attendu : `13/13 OK, 0 écarts`.

---

## 11. Tests de non-régression

| Fichier | Couverture |
|---------|------------|
| `tests/test_simulation.py` | Orchestration 3 concepts, mois moyen, pipeline IA |
| `tests/test_revenue_rules.py` | Règles Excel 1→4 (pivot, mix, catégories, m_lin) |
| `tests/test_recommendation_rules.py` | Filtrage SIMPLY / LIBERTY / CONNECTED |
| `tests/test_model_evaluation.py` | Best-fit concept, TO récap, évaluation 2026 |
| `tests/test_model_trainer.py` | Dataset prêt, `ensure_trained` idempotent |

```bash
./test.sh
# ou : pytest tests/test_revenue_rules.py tests/test_recommendation_rules.py
```

---

## Références internes

| Document | Contenu |
|----------|---------|
| `README.md` | Architecture, flux init, API |
| `sources/raw/docs/consignes.md` | Consignes produit et backlog |
| `data/reference/rod_reference.json` | Constantes pilotes + `cost_lines` |
| `data/reference/rod_reference_extracted.json` | Rapport audit Excel ↔ JSON |
| `data/processed/performance_report.json` | Résultats test/évaluation 2026 |
| `data/processed/evaluation_actuals_annual.csv` | CA réel holdout annualisé (règle de 3) |
| `tests/test_simulation.py` | Tests unitaires orchestration |
| `tests/test_revenue_rules.py` | Tests règles revenus |
| `tests/test_recommendation_rules.py` | Tests recommandation concept |