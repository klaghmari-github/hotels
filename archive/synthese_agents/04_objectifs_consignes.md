# Objectifs, consignes et décisions produit — monorepo hotels

Document de synthèse produit / métier pour un décideur technique.  
Sources : `archive/docs/*`, `archive/consignes.txt`, `accord/README.md`, code actif `accord/`, consignes historiques `rod_ia`, sessions compaction hotels (INDEX / segments).  
**Code actif aujourd’hui** : `accord/` (Data & Model Studio + wizard directeur).  
**Archive** : `archive/` (pipelines prepare historiques, `rod_ia`, Excel/CSV bruts, docs d’audit).

Dernière consolidation : 2026-07-25

---

## 1. Objectif métier global

### Contexte

**ROD — Retail On Demand (Accor)** est un dispositif de **corner / boutique** en hôtel. L’enjeu business est d’aider un directeur d’hôtel (ou l’équipe retail Accor) à :

1. **Estimer le chiffre d’affaires** d’un coin de vente (mensuel et annuel).
2. **Estimer les coûts** (technos, annexes, agencement amorti) liés à la solution choisie.
3. **Calculer la marge nette** (marge produit − coûts).
4. **Recommander un concept** parmi trois niveaux de solution retail :
   - **SIMPLY** — entrée de gamme, petits hôtels / budget.
   - **LIBERTY** — intermédiaire, lifestyle NON-F&B.
   - **CONNECTED** — haut de gamme / grands établissements.

### Double moteur (règles + IA)

Depuis le début du projet, deux approches coexistent et doivent être **comparables** dans l’UI :

| Moteur | Nature | Granularité | Source de vérité |
|--------|--------|-------------|------------------|
| **ROD Excel** | Déterministe (règles extraites des classeurs Excel) | **Mois moyen pilote** (plat × 12 pour l’annuel) | `rod_reference.json` ← Excel Simulateurs / Coûts |
| **IA (XGBoost)** | Apprentissage sur historique ventes | **Profil mensuel** (12 mois distincts) | Dataset `model_data` / artefacts entraînés |

Les deux passent (ou doivent passer) par le **même pipeline P&L** (marge produit, coûts, marge nette) pour comparer des pommes à des pommes.

### Valeur livrée cible

- **Admin** : préparer, éditer, joindre et trainer les données (Data Studio + Model Studio).
- **User** : parcours directeur en **5 étapes** → simulation multi-concepts → reco.
- **Décision** : concept recommandé = meilleure **marge nette ROD** parmi les concepts **autorisés** (taille, catégories N-F&B, marque).

---

## 2. Consignes utilisateur importantes (chronologie thématique)

Ordre approximatif des phases produit (pas des dates exactes). Les décisions se sont accumulées d’une architecture notebooks → `rod_ia` → monorepo `accord/` self-contained.

### Phase A — Comprendre les Excel et reproduire le simulateur

- Lire **toutes** les feuilles ROD (Paramètres & règles, Simulateurs + coûts, récap données).
- Aucune constante métier inventée : valeur = Excel, recalcul ventes, ou hypothèse documentée.
- Reproduire fidèlement : pilotes par concept, impact TO, Règles 1–4 (clients, mix ±10 %, catégories, m_lin), coûts techno / annexes / agencement, reco concept.
- Politique marque : haute gamme pour hôtels haut de gamme même si la marge pure n’est pas maximale (règles Excel + répartition marques).

### Phase B — IA sur les ventes historiques

- Cibles = montants / nombres de ventes croisés (TYPE F&B·NON-F&B × GAMME × mois) — **séparation stricte features / targets** (anti-fuite).
- **Holdout 2026** : exclure la dernière année des ventes pour l’apprentissage ; évaluer sur 2026 (mois présents, annualisation par règle de trois).
- Préférer **arbres (XGBoost / HistGB)** aux réseaux de neurones (petit N, données tabulaires).
- Enrichir les hôtels : géocodage, POI (commerces 100–500 m, plage 1–5 km), météo mensuelle.
- Comparer systématiquement **ROD vs IA** sur les pivots (onglet Performance admin historique).

### Phase C — Dataprep structurée (consigne fondatrice)

Source : `archive/consignes.txt` — *« le plus important c’est la partie dataprep, notamment SalesPrep »*.

- Données manquantes inévitables → **moyennes** projetées sur les trous (cohérence multi-agrégats).
- Grain final de jointure : **`nom_hotel` / `hotel_code` × année × mois**.
- Champs ventes :
  - TYPE → catégorie **F_B** / **N_F_B**
  - GAMME → sous-catégorie
  - `nom_boutique` → nom hôtel
  - nombre de ventes = somme quantités
  - montant = somme prix TTC
  - paniers = tickets distincts
- Pipeline SalesPrep en **étapes 1.a → 7** (annuel, mensuel, cat/sous-cat, heure, weekend, holidays) puis jointure large.
- Architecture folders : `prepare/` / `evaluate/` / `serve/` — construire **step by step sans casser** l’existant.
- Chaîne préparée : **RodPrep → MeteoPrep → ProximityPrep → SalesPrep → AllPrep**.
- Identité = **code Accor (`hotel_code`)**, pas les slugs / noms seuls.

### Phase D — Application web monolithe historique (`rod_ia`)

- Split **user** (simulateur directeur, port 5000) / **admin** (exploration, interprétation, perf, port 5001) / **API** (port 5002).
- Wizard **5 étapes** côté user ; exploration / interprétation / évaluation **admin only**.
- Config store (m_lin, mix F&B, concept) = **sortie** proposée par concept, pas saisie directe forcée.
- Feature store par `hotel_id` ; registre identité ; traçabilité `RuleTrace` Excel ↔ Python.

### Phase E — Refonte `accord/` (Data & Model Studio + User)

Décisions consolidées dans `accord/README.md` et sessions compaction :

- Application **self-contained** : Excel sous `accord/data/`, archive non requise au runtime.
- **Admin** (`run_admin.py`, port **5055**) : édition WYSIWYG tabulaire des datasets + Model Build / Explore / Deploy.
- **User** (`run_user.py`, port **5056**) : wizard directeur + simulation ROD + reco.
- Moteurs **revenus** et **coûts découplés** pour qu’une future IA puisse remplacer **uniquement les revenus**.
- Ventes : **raw récurrentes** → rebuild sales ; autres tables (hotel, brand, weather, proximity, holidays) plutôt **one-shot / rebuild à la demande**.
- Holidays : union **exclusive** weekend ∪ fériés ∪ vacances ; zones scolaires en binaires a/b/c.
- Model Data : rôles **id_detail / descriptive / target** ; dernière année = **évaluation** ; cible ranking = `montant_ventes`.
- Concept pilote : moyennes marque pour préremplir l’étape 1, **hors dernière année**.

---

## 3. Décisions d’architecture

### 3.1 Split admin / user

| Entrée | Public | Port | Rôle |
|--------|--------|------|------|
| `accord/run_admin.py` | Data science / métier data | 5055 | Édition Excel, jointures All Data / Model Data, train XGBoost, explore, deploy |
| `accord/run_user.py` | Directeur d’hôtel | 5056 | Wizard 5 étapes → enrichissement → revenus + coûts → marge → reco concept |

Historique `archive/` : `run_server.py` (user 5000), `run_admin.py` (admin 5001), `run_api.py` (API 5002).

**Principe** : le user ne voit ni Model Explore, ni tables brutes d’entraînement, ni jargon pipeline.

### 3.2 Format tabulaire (source de vérité éditable)

- Chaque onglet admin = un fichier Excel sous `accord/data/`.
- UI **WYSIWYG paginée** : cellules éditables, dirty map, Ctrl+S.
- `all_data.xlsx` et `model_data.xlsx` sont **dérivés** (boutons Reconstruire), pas sources primaires.
- Identité hôtel = **`hotel_code`**.
- Null numériques post-jointure → **0** (mois sans ventes, etc.).

Ordre sidebar demandé (sessions) :

> Brand → Hotel → Holidays → Sales Raw → Sales → Weather → Proximity → All Data → Concept pilote → Model Data → (Model Build / Explore hors datasets)

### 3.3 Ventes raw récurrentes vs autres données one-shot

| Donnée | Nature | Flux |
|--------|--------|------|
| **Sales raw** (`hotel_sales_raw_data.xlsx`) | Récurrente (tickets / exports) | Import → `sales_prep` → `hotel_sales_data.xlsx` (rebuild) |
| **Hotel / Brand** | Fiche et parcs relativement stables | Édition manuelle admin |
| **Weather / Proximity / Holidays** | Calculables depuis lat/lon + calendrier | Rebuild load-or-compute (Meteostat, Overpass, calendrier FR) |
| **Coûts** (`couts.xlsx`) | Extraction one-shot depuis Excel ROD archive | `extract_couts.py` |
| **rod_reference.json** | Constantes pilotes | Extraction Excel (archive) puis consommation user |

Consigne SalesPrep : indépendance progressive de l’archive — le rebuild sales vit sous `accord/sales_prep.py`.

### 3.4 Découplage revenus / coûts (préparation IA)

```
Saisie wizard
    → enrichissement (géocode, météo, proximité, holidays)
    → moteur REVENUS (aujourd’hui règles Excel ROD)
    → moteur COÛTS (technos / annexes / agencement)  ← stable
    → marge nette + recommandation
```

**Décision produit** : demain, l’IA remplace **seulement** l’étape revenus ; les coûts et la reco (marge) restent.

### 3.5 Holidays exclusive

- `nb_jours_holidays` / `jours_holidays` = union **sans double-comptage** : weekend ∪ fériés ∪ vacances scolaires.
- Zones scolaires : binaires `zone_scolaire_a/b/c` (texte de zone retiré comme feature redondante).
- Sales joint les jours holidays pour produire des % / volumes **holidays vs hors holidays**.

### 3.6 Concept pilote

- Table `concept_pilote.xlsx` : grain **hôtel × année** (clients, CA mensuel moyen, mix produits distincts F_B / N_F_B).
- Sources : `hotel_data` + `hotel_sales_data` + raw (EAN / TYPE).
- **API user** `GET /api/concept_pilote/brand/<marque>` :
  - filtre marque ;
  - **exclut l’année max globale** du fichier (holdout, ex. 2026) ;
  - moyenne arithmétique des indicateurs d’exploitation (étape 1, **sans mix produits**).
- Sert à **préremplir** chambres / TO / guests du wizard.

### 3.7 Jointures et grille temporelle

- Grille **parfaite** All Data : chaque hôtel × chaque année pertinente × 12 mois.
- Clés : `hotel_code` (+ année, mois quand disponible).
- Pas de duplication des lignes sales lors des merges (clés strictes par table).

---

## 4. Règles UI

### 4.1 Wizard user — 5 étapes

| # | Étape | Contenu |
|---|--------|---------|
| 1 | **Hôtel** | Identité, adresse, géocode, chambres, TO, guests ; préremplissage moyennes marque (concept_pilote hors dernière année) |
| 2 | **Services** | Équipements F&B / lobby / services |
| 3 | **Clients** | Profil clients, besoins (toggles catégories) |
| 4 | **Corner** | Corner existant, m_lin, mix |
| 5 | **Simulation** | Lancement multi-concepts, revenus, coûts, marge, recommandation |

Navigation stepper cliquable ; étape 5 relance la simulation.

### 4.2 Langage métier côté user (pas de jargon Excel)

- Libellés orientés **directeur** : hôtel, clients, corner, simulation de revenu, concept recommandé.
- Pas d’exposition des cellules Excel (C21, H168…), des noms de fichiers sources, ni des onglets Model Explore.
- Les références techniques (Règle 1, CA pilote) peuvent apparaître en **détail de résultat** pour la transparence, pas dans le parcours de saisie.
- Admin assume le jargon data (datasets, R², arbres, rôles de colonnes).

### 4.3 Config store = sortie

- L’utilisateur saisit identité + opérationnel + contraintes (besoins, exclusions).
- Le système **propose** m_lin / mix / concept par solution.
- Surcharges possibles via corner / contraintes, mais le concept n’est pas une simple case à cocher libre sans règles.

### 4.4 Recommandation affichée

- Concepts **autorisés** selon règles Excel (taille, N-F&B lifestyle, marque).
- Choix final : **meilleure marge nette** parmi les autorisés.
- Warnings métier si marque exige LIBERTY mais catégories absentes, etc.

### 4.5 Admin UI

- Tables dirty + sauvegarde.
- Model Data : en-têtes colorés (id / desc / cible), lignes d’**évaluation en gras**.
- Model Explore : liste design triée par perf, importance, arbres cumulés, **Deploy** → un seul modèle `models/deploy/`.

---

## 5. Model studio (descriptives vs targets, eval dernière année)

### 5.1 Chaîne données → modèle

```
hotel_* + sales + holidays + weather + proximity
        → all_data.xlsx          (grille hotel × année × mois)
        → model_data.xlsx        (hôtels avec ventes, rôles colonnes)
        → models/design/<nom>/   (Build & Save)
        → models/deploy/         (Deploy unique)
```

### 5.2 Rôles de colonnes (`model_data`)

| Rôle | Couleur UI | Contenu |
|------|------------|---------|
| **id_detail** | Jaune / or | `hotel_code`, nom, marque, adresse, ville, lat/lon, année, mois, zone… |
| **descriptive** | Neutre | Météo, équipements, brand stats, holidays counts, **mix saisi** en *nombre de ventes* (`pct_*_nombre_ventes`, `pct_categories_mois_*`, `nombre_categories_mois_*`) |
| **target** | Vert | Volumes (`nombre_ventes`, `montant_ventes`, paniers, produits) + **autres pct** (montant, paniers, produits) |

Règles :

1. Uniquement hôtels avec au moins une vente > 0.
2. Colonnes **constantes** supprimées.
3. Listes de jours (`jours_*`) **hors modèle** (trop textuelles / array).
4. Ordre colonnes : id → descriptive → target.
5. Cible principale de ranking : **`montant_ventes`**.

### 5.3 Split train / évaluation

- **Dernière année calendaire** présente dans les données = **évaluation** (`_is_eval=1`, gras UI).
- Années strictement antérieures = **train**.
- Aligné avec la consigne historique holdout 2026 (dernière année des ventes).

### 5.4 Build / Explore / Deploy

- Features = **toutes** les descriptives.
- XGBoost multi-output (hyperparams exposés dans l’UI).
- Explore : R² / RMSE cumulés par arbre, importance, visualisation SVG.
- Un seul modèle déployé à la fois pour la prod applicative.

### 5.5 Lien historique `rod_ia` (archive)

- Convention `d_*` (features) / `t_*` (targets).
- 24 targets globales mensuelles (CA + ventes) entraînées ; targets détaillées TYPE/GAMME en dataset mais pas toutes dans le fit.
- Évaluation 2026 : best-fit concept, règle de trois sur 4 mois, rapport `performance_report.json`.

---

## 6. Travail restant / roadmap

Synthèse du backlog historique (`archive/docs/consignes.md`) et des intentions `accord/` actuelles.

### 6.1 Priorité produit `accord/`

| Priorité | Item | Commentaire |
|----------|------|-------------|
| **P0** | **IA remplace les revenus** | Brancher le modèle deploy sur l’étape revenus du wizard ; garder coûts + reco inchangés |
| **P0** | **Comparaison ROD vs IA** dans l’UI user (ou admin) | Parité avec l’ancien onglet Performance ; CA, ventes, marge par concept |
| **P1** | Hydratation wizard depuis admin | Contexte hôtel (`hotel_data` + `model_data`) déjà partiel — fiabiliser préremplissage |
| **P1** | Qualité SalesPrep / holidays | Rebuild e2e, pas de doublons merge, colonnes `pct_*_holidays` stables |
| **P2** | Extension parc pivots | Plus d’hôtels avec ventes pour stabiliser l’IA (n actuel faible) |
| **P2** | Deploy → consommation user | Garantir qu’un modèle déployé est bien celui appelé à la simulation |

### 6.2 Backlog IA (archive, toujours pertinent)

**Features**

- Fusion systématique POI / météo / plage dans le dataset train.
- Features ventes dérivées (panier moyen, top gammes).
- Conserver plus de booléens récap après sélection.

**Modèle**

- Hiérarchie cible : CA global puis résiduel % TYPE/GAMME.
- Régularisation + leave-one-hotel-out.
- Blend `α × ML + (1−α) × ROD` par marque.
- Fallback ROD si confiance faible hors pivots.

**Données**

- Plus d’hôtels pivots dans le registre.
- Validation temporelle multi-années + holdout dernière année.
- Cibles lissées (moyenne mobile).

### 6.3 Constats perf (historique, ~juil. 2026)

- ~5 hôtels évalués, ~4 mois 2026.
- Écarts absolus moyens élevés (ordre de grandeur 50 %+) ; IA parfois meilleure, instable hôtel par hôtel.
- Causes : petit N, features géo pas toujours fusionnées au train, décalage agrégats train / inférence.

### 6.4 Restrictions pérennes

- Ne pas inventer de GAMME / TYPE hors catalogue ventes.
- Ne pas sommer les ventes historiques brutes sans normaliser (moyennes / mois actifs).
- Ne pas traiter la config store comme seule entrée utilisateur.
- Ne pas utiliser `old/` / notebooks comme source métier.
- Ne pas encoder le texte libre récap en features sans stratégie.

---

## 7. Glossaire

| Terme | Définition |
|-------|------------|
| **ROD** | Retail On Demand — offre Accor de corner retail en hôtel |
| **SIMPLY** | Concept entrée de gamme (pilote type petit budget, ex. ~129 ch, 6 m_lin) |
| **LIBERTY** | Concept intermédiaire (lifestyle N-F&B, pilote ~142 ch, 8 m_lin) |
| **CONNECTED** | Concept haut de gamme / grand hôtel (pilote ~305 ch, 7 m_lin) |
| **F_B / F&B** | Food & Beverage — catégorie produits alimentaires / boissons |
| **N_F_B / NON-F&B** | Hors food — cosmétiques, kids, apparel, souvenirs, SOS, etc. |
| **TYPE** | Champ ventes brut → F&B ou NON-F&B |
| **GAMME** | Sous-catégorie produit (FOOD SALEE, SANS ALCOOL, COSMETIQUE…) |
| **hotel_code** | Identifiant Accor de l’hôtel — **clé de jointure** du monorepo |
| **nom_boutique** | Nom point de vente dans le CSV ventes ; mappé vers `hotel_code` |
| **hotel_id** | Identifiant historique archive / feature store `rod_ia` (lié au registre) |
| **Pilote (concept)** | Hôtel de référence Excel pour un concept ; base des règles de trois |
| **concept_pilote** | Table admin hôtel×année (CA moyen, clients, mix) + API moyennes **marque** hors dernière année |
| **m_lin** | Mètres linéaires de rayonnage / surface de corner |
| **TO** | Taux d’occupation (rooms) |
| **guests_per_chambre** | Clients moyens par chambre occupée |
| **clients_mois** | `nb_chambres × TO × guests × 30,5` (REV-01/02) |
| **taux_acheteur** | Ventes / clients hébergés (réf. Excel C21) |
| **mix F&B** | Part F&B vs NON-F&B (assortiment ou CA) |
| **Config store** | Paramètres de la boutique **en sortie** (concept, m_lin, mix) |
| **jours_holidays** | Liste de dates (ISO) union exclusive weekend ∪ fériés ∪ vacances |
| **nb_jours_holidays** | Compteur exclusif de ces jours dans le mois |
| **pct_jours_holidays** | `nb_jours_holidays / nb_jours_dans_mois` |
| **Sales raw** | Tickets / lignes brutes (`hotel_sales_raw_data`) |
| **Sales data** | Agrégats mensuels rebuild depuis raw (`hotel_sales_data`) |
| **All Data** | Jointure complète multi-sources (grille hotel×année×mois) |
| **Model Data** | Dataset ML dérivé (rôles id/desc/cible, split dernière année) |
| **descriptive** | Features d’entrée du modèle |
| **target** | Variables à prédire (volumes + pct non saisis) |
| **id_detail** | Colonnes d’identité / contexte non utilisées comme features pures |
| **Holdout / dernière année** | Année max des données réservée à l’évaluation (ex. 2026) |
| **Règle de trois** | Projection / annualisation proportionnelle (période partielle → annuel) |
| **Best-fit concept** | Concept dont le CA ROD est le plus proche du réel (évaluation) |
| **Reco marge** | Concept choisi par meilleure marge nette parmi les autorisés |
| **design / deploy** | Modèles exploratoires vs modèle unique de production |
| **Règle 1–4** | Enchaînement revenus Excel : clients → mix → catégories → m_lin |
| **RECO #1 / #2** | Taille (<50 ch → SIMPLY) ; catégories N-F&B lifestyle → ouvre LIBERTY |
| **capex / agencement** | Investissement aménagement, souvent amorti (ex. 84 mois) |
| **Marge produit** | CA − coût d’achat (coefs marge F&B / N-F&B Excel) |
| **Marge nette** | Marge produit − coûts mensuels d’exploitation corner |
| **ROI mois** | Capex / (marge nette annuelle / 12) si marge > 0 |
| **Feature store** | Cache par hôtel (archive `rod_ia`) : géo, targets, historique simus |
| **rod_reference** | JSON des constantes pilotes et grilles extraites Excel |
| **Pivot hôtel** | Hôtel déjà équipé ROD avec historique ventes pour train/éval |

---

## 8. Cartographie rapide des sources de vérité

| Priorité | Source | Usage |
|----------|--------|-------|
| 1 | Excel ROD (`archive/sources/raw/`) | Règles revenus, coûts, reco, pilotes |
| 2 | Ventes (`001.queryVentes` / sales raw) | Historique CA, mix, targets IA |
| 3 | `accord/data/*.xlsx` | Source de vérité **éditable** runtime admin |
| 4 | Docs consignes + ce document | Intentions produit et architecture |
| 5 | Sessions compaction hotels | Historique décisions d’implémentation (ne pas inventer au-delà) |

---

## 9. Points d’entrée opérationnels (rappel)

```bash
cd accord
python run_admin.py   # http://127.0.0.1:5055 — data + model studio
python run_user.py    # http://127.0.0.1:5056 — wizard directeur ROD
```

Archive (legacy, audit / extraction) :

```bash
cd archive
./init.sh             # extraction + dataset + train + éval
python run_server.py  # ancien user :5000
python run_admin.py   # ancien admin :5001
```

---

*Fin du document 04 — Objectifs, consignes et décisions produit.*
