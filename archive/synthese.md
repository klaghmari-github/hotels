# Synthèse monorepo **hotels**

Document consolidé à partir de quatre synthèses d’agents parallèles :

| Agent | Fichier | Focus |
|-------|---------|--------|
| 1 | [`synthese_agents/01_accord.md`](synthese_agents/01_accord.md) | Application active `accord/` |
| 2 | [`synthese_agents/02_archive.md`](synthese_agents/02_archive.md) | Legacy `archive/`, `rod_ia`, docs |
| 3 | [`synthese_agents/03_excel_formules.md`](synthese_agents/03_excel_formules.md) | Excel bruts, formules, datasets tabulares |
| 4 | [`synthese_agents/04_objectifs_consignes.md`](synthese_agents/04_objectifs_consignes.md) | Objectifs métier, consignes, décisions produit |

**Date de consolidation** : 2026-07-25  
**Public** : décideur technique / reprise de projet

---

## 1. En une page

### 1.1 Objectif métier

**ROD — Retail On Demand (Accor)** aide à dimensionner un **corner / boutique** en hôtel :

1. Estimer le **CA** (mensuel / annuel)  
2. Estimer les **coûts** (techno, annexes, agencement)  
3. Calculer la **marge nette**  
4. **Recommander un concept** parmi **SIMPLY**, **LIBERTY**, **CONNECTED**

Deux moteurs coexistent (et doivent rester **comparables**) :

| Moteur | Nature | Aujourd’hui dans `accord/` |
|--------|--------|----------------------------|
| **Règles ROD** | Déterministe, pilotes Excel | **Actif** côté `run_user` (`user/rules/*`) |
| **IA (XGBoost)** | Appris sur historique ventes | **Actif** côté `run_admin` (Model Studio) ; **pas encore branché** au wizard user |

### 1.2 Architecture monorepo

```
hotels/
├── accord/                 # PRODUIT ACTIF (self-contained)
│   ├── run_admin.py        # Data & Model Studio   → :5055
│   ├── run_user.py         # Wizard directeur ROD  → :5056
│   ├── data/*.xlsx         # Sources de vérité tabulaires
│   └── user/               # Simulateur (revenus ∥ coûts)
├── archive/                # LEGACY + SOURCES BRUTES + docs
│   ├── sources/raw/        # Excel formules, CSV ventes
│   ├── rod_ia/             # Ancienne app complète (simu + IA + API)
│   ├── docs/               # rod_rules, consignes, API…
│   └── data/reference/     # rod_reference, brand_projections…
└── synthese.md             # Ce document
```

| | **`accord/`** | **`archive/`** |
|--|---------------|----------------|
| Statut | Application **courante** | Inspiration, audit, sources Excel/CSV |
| Runtime | 5055 admin / 5056 user | 5000/5001/5002 encore démarrables, non cible |
| Données | Excel **tabulaires** sous `accord/data/` | Excel **non normalisés** + CSV tickets |
| Dépendance | Archive **non requise** au runtime (sauf extract one-shot / import CSV) | Indépendante |

### 1.3 Principe de données (décision fondatrice)

| Type d’info | Stratégie | Pourquoi |
|-------------|-----------|----------|
| **Hôtels, marques, calendriers, météo, proximité, coûts, constantes pilotes** | Transformés **une fois** en format **tabulaire** (ou JSON) dans `accord/data/`, puis édités / rebuild à la demande | On ne recevra plus les classeurs Excel « métier » non normalisés pour les hôtels pilotes |
| **Ventes** | **Raw conservé** + pipeline **automatisé** (`sales_prep`) → agrégat mensuel | Réceptions **régulières** de tickets au format brut |

---

## 2. Objectifs et consignes (produit)

### 2.1 Chaîne de valeur cible

```
Admin prépare les données et le modèle
        │
        ▼
User (directeur) saisit l’hôtel en 5 étapes
        │
        ▼
Enrichissement (géocode, météo, proximité, holidays)
        │
        ├─► Moteur REVENUS  (aujourd’hui règles ROD ; demain IA)
        └─► Moteur COÛTS    (stable, réutilisable)
        │
        ▼
Marge nette + recommandation de concept
```

### 2.2 Consignes transverses (issues des docs + échanges)

- **Fidélité Excel** : pas de constante métier inventée ; traçabilité règle ↔ cellule quand pertinent.  
- **Identité** = `hotel_code` Accor (pas seulement le nom boutique).  
- **Grain de jointure** = `hotel_code` × `année` × `mois` (sauf concept_pilote : annuel).  
- **Anti-fuite ML** : séparation stricte features descriptives / cibles ventes.  
- **Holdout** : dernière année (ex. **2026**) exclue de l’apprentissage et des moyennes marque étape 1.  
- **Nulls numériques** après jointure → **0**.  
- **Store config** (m_lin, mix, concept) = **sortie** du moteur, pas entrée forcée du wizard.  
- **UI user** : langage directeur (pas de jargon fichier Excel / cellules).  
- **Revenus ∥ coûts** : demain l’IA ne remplace **que** les revenus.

### 2.3 Wizard user (5 étapes)

| # | Étape | Contenu actuel |
|---|--------|----------------|
| 1 | Hôtel | Identité, adresse, géocode, chambres / TO / guests ; **moyennes marque** via `concept_pilote` (hors année max) |
| 2 | Services | F&B / non-F&B / lobby |
| 3 | Clients | Profil + besoins catégories (Règle 3) |
| 4 | Corner | Corner existant, m_lin, mix |
| 5 | Simulation | 3 concepts, CA, coûts, marge, reco |

---

## 3. `archive/` — d’où l’on part

### 3.1 Rôle

- **Sources de vérité brutes** (Excel ROD, CSV ventes).  
- **Ancienne application complète** `rod_ia/` (simulateur + ML + feature store + admin + API).  
- **Documentation d’audit** (`docs/rod_rules.md`, consignes, API REST, exploration).  
- **Référence UX** : captures `sources/raw/docs/ecran_sim/` (onboarding Accor 5 étapes).

### 3.2 Excel bruts non tabulaires (exemples)

| Fichier | Problème de format | Usage historique |
|---------|-------------------|------------------|
| `ROD - Simulateurs + détail des coûts.xlsx` | Formules, blocs, cellules adressées (C9, E34, H168…) | Pilotes CA/coûts/marges |
| `ROD - Paramètres & règles + projections nb. d'hôtels.xlsx` | Stats + règles textuelles | Brand projections + reco concept |
| `Récapitulatif de l'ensemble des données ROD (2).xlsx` | **Wide** : une colonne = un hôtel, champs en lignes | Fiches descriptives hôtels |
| `001.queryVentes.csv` | Tabulaire tickets (déjà propre) | Ventes train / holdout |

Extraction archive typique :

- `RodExcelExtractor` → `rod_reference.json`  
- `RodRecapExtractor` → `rod_recap.*`  
- `BrandProjectionsExtractor` → `brand_projections.json`  

### 3.3 Règles ROD (cœur métier)

**Principe** : hôtel **pilote par concept** (pas par marque) → projection sur l’hôtel cible.

| Famille | Idées clés |
|---------|------------|
| **Clients** | `clients/jour = chambres × TO × guests` ; `clients/mois = × 30,5` |
| **Règle 1** | Scaling CA par ratio `clients_hôtel / clients_pilote` |
| **Impact TO** | ~9,23 € HT par point de TO d’écart au pilote |
| **Règle 2** | Ajustement mix F&B / N-F&B par pas de 10 % |
| **Règle 3** | Bonus/malus catégories (besoins clients) |
| **Règle 4** | Ajustement mètres linéaires |
| **Coûts** | Σ techno + annexes + agencement amorti (souvent 84 mois) |
| **Reco** | Taille &lt; 50 ch → SIMPLY ; lifestyle N-F&B → LIBERTY ; sinon CONNECTED ; choix = meilleure marge nette |

Pilotes (`rod_reference.json`) :

| Concept | Chambres | TO | Guests | m_lin | CA HT mensuel ~ |
|---------|----------|-----|--------|-------|-----------------|
| SIMPLY | 129 | 0,80 | 1,7 | 6 | 720 € |
| LIBERTY | 142 | 0,70 | 2,2 | 8 | 1 479 € |
| CONNECTED | 305 | 0,75 | 1,8 | 7 | 3 634 € |

### 3.4 Portage archive → accord

| Porté / réimplémenté dans `accord/` | Reste surtout dans `archive/` |
|-------------------------------------|-------------------------------|
| Règles revenus, coûts, reco (`user/rules/`) | Feature store multi-hôtels, dual IA+ROD UI |
| `rod_reference.json` (copie data) | API REST `/api/v1/predict` |
| Wizard 5 étapes (UX inspirée ecran_sim) | Exploration / interprétation arbres admin historique |
| Pipeline ventes sous `sales_prep.py` | Package `prepare/` multi-modules (largement archivé/supprimé du runtime) |
| extract_couts, import CSV ventes | Neural model, performance_report 2026 complet |

---

## 4. `accord/` — ce qu’on construit

### 4.1 Deux entrées

```bash
cd accord
python run_admin.py   # http://127.0.0.1:5055  — données + modèles
python run_user.py    # http://127.0.0.1:5056  — simulateur directeur
```

### 4.2 Pipeline données (vue d’ensemble)

```
                    [optionnel] 001.queryVentes.csv (archive)
                                    │
                                    ▼
                     hotel_sales_raw_data.xlsx   ◄── réceptions régulières
                                    │
                         sales_prep + hotel_data
                         (+ holidays pour split)
                                    │
                                    ▼
                      hotel_sales_data.xlsx (mensuel, readonly)
                                    │
        ┌───────────────┬───────────┼────────────┬──────────────┐
        ▼               ▼           ▼            ▼              ▼
   holidays         weather    proximity    hotel_data      brand_data
   (calendrier)    (Meteostat) (Overpass)   (saisie)        (saisie)
        │               │           │            │              │
        └───────────────┴─────┬─────┴────────────┴──────────────┘
                              ▼
                       all_data.xlsx  (hotel × année × mois)
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
       model_data.xlsx                 concept_pilote.xlsx
       (ML, rôles, eval)               (hôtel × année)
              │                               │
              ▼                               ▼
     Model Build / Explore            run_user étape 1
     (XGBoost design → deploy)        (moyennes marque)
```

### 4.3 Inventaire `accord/data/`

| Fichier | Grain | Rebuild UI ? | Notes |
|---------|-------|--------------|--------|
| `hotel_brand_data.xlsx` | marque | Non (éditable) | Effectifs parc |
| `hotel_data.xlsx` | hôtel | Non (éditable) | Fiche complète + lat/lon |
| `hotel_sales_raw_data.xlsx` | ticket | Non (éditable) | **Brut récurrent** |
| `hotel_sales_data.xlsx` | hôtel×an×mois | **Oui** | Agrégats + mix % + holidays |
| `hotel_holidays_data.xlsx` | hôtel×an×mois | **Oui** | Union exclusive jours |
| `hotel_weather_data.xlsx` | hôtel×an×mois | **Oui** | Meteostat |
| `hotel_proximity_data.xlsx` | hôtel | **Oui** | Overpass |
| `all_data.xlsx` | hôtel×an×mois | **Oui** | Jointure |
| `model_data.xlsx` | ML | **Oui** | Hôtels avec ventes, rôles |
| `concept_pilote.xlsx` | hôtel×**année** | **Oui** | Clients, CA moy., mix produits |
| `couts.xlsx` | multi-feuilles | Script | Extract one-shot archive |
| `rod_reference.json` | constantes | Manuel | Pilotes simulateur |

### 4.4 Rôles des modules Python clés

| Module | Rôle |
|--------|------|
| `schemas.py` | Onglets = Excel ; ordre sidebar ; colonnes éditables / readonly |
| `store.py` | Cache, pagination, CRUD Excel, coerce types |
| `sales_prep.py` | Raw → mensuel + match `hotel_code` + mix + holidays sales |
| `geo_holidays.py` | Fériés FR + vacances A/B/C ; **zones binaires** ; `jours_holidays` exclusifs |
| `geo_weather.py` / `geo_proximity.py` | Meteostat / Overpass |
| `join_data.py` | Grille parfaite + left joins + fill 0 |
| `model_data.py` | Filtre, rôles id/desc/target, dernière année = eval |
| `model_train.py` / `model_explore.py` | XGBoost multi-output, arbres, deploy |
| `concept_pilote.py` | Agrégats annuels + **moyennes marque** (hors année max) |
| `user/rules/revenue.py` | Revenus R1–R4 + impact TO + marge produit |
| `user/rules/costs.py` | Coûts techno / annexes / agencement (**séparé**) |
| `user/rules/recommendation.py` | Concepts autorisés + meilleure marge |
| `user/services/orchestrator.py` | Pipeline simulate user |

### 4.5 Ordre sidebar admin

Brand → Hotel → Holidays → Sales Raw → Sales → Weather → Proximity → All Data → **Model Data** → **Concept Pilote** → (Model Build / Explore hors datasets)

### 4.6 Model Studio (rappels)

- **Descriptive** (features) : météo, proximité, holidays counts, équipements, **mix % en nombre de ventes** (saisie directeur), zones binaires…  
- **Target** (cibles) : volumes CA / ventes / paniers / produits + autres pct (montant, paniers…) + splits holidays.  
- **Éval** : dernière année (`_is_eval`), lignes en gras UI.  
- Cible ranking modèles : **`montant_ventes`**.

### 4.7 Concept pilote (lien admin ↔ user)

Grain **hôtel × année** :

- `nb_chambres`, `taux_occupation`, `guests_per_chambre` (défaut marque)  
- `clients_jour`, `clients_mois` (= ch × TO × guests × 30,5)  
- `ca_mensuel_moyen` (moyenne des mois de `hotel_sales_data`)  
- Mix produits distincts F_B / N_F_B (depuis **raw** prioritaire)

**Étape 1 user** : `GET /api/concept_pilote/brand/<marque>`  
→ lignes de la marque, **exclure année max (ex. 2026)**, moyenne des champs d’exploitation (**sans mix** à l’étape 1).

---

## 5. Transformation non-tabulaire → tabulaire

### 5.1 Schéma de conversion

```
archive/sources/raw/                     accord/data/
─────────────────────                    ──────────────────────────
Simulateurs (formules)           ──►     rod_reference.json
                                         couts.xlsx
Paramètres / projections         ──►     hotel_brand_data.xlsx
Récap ROD wide (1 col = 1 hôtel) ──►     hotel_data.xlsx
001.queryVentes.csv              ──►     hotel_sales_raw_data.xlsx  [gardé brut]
                                         hotel_sales_data.xlsx      [agrégé auto]
lat/lon + calendriers            ──►     holidays / weather / proximity
jointures                        ──►     all_data → model_data
ventes + hotel                   ──►     concept_pilote
```

### 5.2 Pourquoi cette asymétrie ventes / reste

- **Hôtels pilotes, marques, calendriers, géo, coûts** : figés ou recalculables ; le format tabulaire est la **nouvelle source de vérité** (édition admin, pas de re-saisie Excel multi-feuilles).  
- **Ventes** : flux **vivant** ; on conserve le grain ticket pour rejouer le pipeline à chaque réception (TYPE, GAMME, EAN, boutique → `hotel_code`).

### 5.3 Formules Excel → Python (repères)

| Excel | Python `accord` |
|-------|-----------------|
| Clients C16/C17 | `HotelOperating` / `RevenueRules` / `concept_pilote` |
| Scaling clients (R1) | `RevenueRules.rule1_clients` |
| Impact TO F12 | `apply_to_impact` + `rod_reference.impact_to` |
| Mix ±10 % (R2) | `rule2_mix` |
| Catégories (R3) | `coeffs.py` + `rule3_categories` |
| m_lin (R4) | `rule4_m_lin` |
| H168 coûts | `CostRules.compute` |
| Reco taille / N-F&B | `RecommendationRules` |

---

## 6. Rôle des dossiers et fichiers (carte rapide)

### 6.1 Racine monorepo

| Chemin | Rôle |
|--------|------|
| `accord/` | Produit actif |
| `archive/` | Legacy + raw + docs audit |
| `synthese.md` | Synthèse globale (ce fichier) |
| `synthese_agents/` | Synthèses intermédiaires par agent |

### 6.2 Points d’entrée

| Commande | Port | Qui |
|----------|------|-----|
| `accord/run_admin.py` | 5055 | Data / model ops |
| `accord/run_user.py` | 5056 | Directeur |
| `archive/run_server.py` | 5000 | Legacy user (référence) |
| `archive/init.sh` | — | Rebuild référence + ML archive |

---

## 7. État d’avancement et suite

### 7.1 Fait (capacités livrées)

- [x] Admin Excel tabulaire multi-onglets + rebuilds (sales, geo, all_data, model_data, concept_pilote)  
- [x] Pipeline ventes raw → mensuel automatisé  
- [x] Holidays exclusives + zones binaires  
- [x] Model Build / Explore / Deploy XGBoost  
- [x] User wizard 5 étapes + géocode + simulateur ROD (revenus + coûts séparés + reco)  
- [x] Moyennes marque étape 1 via `concept_pilote` (holdout année max)  

### 7.2 Roadmap (priorités produit)

| Priorité | Sujet |
|----------|--------|
| **P0** | Brancher le **modèle déployé** comme moteur de **revenus** alternatif dans `run_user` (coûts inchangés) |
| **P0** | UI **comparaison** ROD règles vs IA (CA, marge, reco) |
| **P1** | Finaliser étapes 2–4 user (services, clients, corner) liées aux features model_data |
| **P1** | Perf / holdout 2026 côté accord (équivalent `performance_report` archive) |
| **P2** | API REST prédiction (héritage `rod_ia`) si besoin intégration externe |

### 7.3 Limites connues

- XGBoost **deploy** non consommé par le simulateur user (encore 100 % règles ROD pour le CA).  
- Overpass / Meteostat / Nominatim dépendent du réseau (rebuilds « light » possibles).  
- Peu d’hôtels pivots → risque de sur-ajustement ML (constaté aussi en archive).  
- README admin peut légèrement diverger de l’ordre exact des onglets (la source d’ordre est `schemas.DATASETS`).

---

## 8. Glossaire

| Terme | Définition |
|-------|------------|
| **ROD** | Retail On Demand — corner Accor |
| **SIMPLY / LIBERTY / CONNECTED** | Trois concepts / solutions retail |
| **F_B / N_F_B** | Food & Beverage / Non-Food & Beverage (TYPE) |
| **hotel_code** | Identifiant Accor canonique |
| **jours_holidays** | Union exclusive weekend ∪ fériés ∪ vacances scolaires |
| **m_lin** | Mètres linéaires du corner |
| **concept_pilote** | Table annuelle d’indicateurs + moyennes marque |
| **Holdout** | Année réservée (ex. 2026) hors apprentissage / hors moyennes marque |
| **Descriptive / target** | Feature d’entrée vs variable à prédire (model_data) |
| **Règle 1** | Scaling du CA pilote par le ratio de clients hébergés |

---

## 9. Comment relire le détail

Pour le détail exhaustif (inventaire fichier par fichier, cellules Excel, historique de consignes) :

1. [`synthese_agents/01_accord.md`](synthese_agents/01_accord.md) — code et datasets `accord/`  
2. [`synthese_agents/02_archive.md`](synthese_agents/02_archive.md) — `rod_ia`, docs, portage  
3. [`synthese_agents/03_excel_formules.md`](synthese_agents/03_excel_formules.md) — Excel, formules, extracteurs  
4. [`synthese_agents/04_objectifs_consignes.md`](synthese_agents/04_objectifs_consignes.md) — produit, roadmap, glossaire étendu  

---

*Document généré par consolidation multi-agents (exploration parallèle code / archive / Excel / consignes), monorepo `hotels`.*
