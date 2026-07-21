# Consignes ROD-IA

> Document unique de référence — consignes métier, état d'implémentation et backlog.
> Dernière mise à jour : 2026-07-02
>
> **Code actif** : `rod_ia/` à la racine. **Ne pas utiliser** `old/` pour l'IA.
> **Doc technique détaillée** : [`README.md`](../README.md) · **Doc code** : http://127.0.0.1:5000/docs

---

## 1. Hiérarchie des sources de vérité

| Priorité | Source | Rôle |
|----------|--------|------|
| 1 | Excel ROD (`sources/raw/`) | Règles revenus, coûts, marges, recommandation concept |
| 2 | Ce fichier + `README.md` | Consignes produit et architecture |
| 3 | `001.queryVentes.csv` | Ventes réelles — train IA et validation 2026 |
| 4 | `old/`, notebooks | Audit uniquement — pas source métier |

**Règle d'or** : aucune constante métier inventée. Valeur = Excel, recalcul ventes pivots, ou hypothèse documentée.

---

## 2. Principes métier (implémentés)

| Principe | Détail | Statut |
|----------|--------|--------|
| Config store = **sortie** | Proposée par concept (m_lin, mix F&B), pas saisie utilisateur | ✅ |
| 3 concepts | SIMPLY, LIBERTY, CONNECTED comparés à chaque simulation | ✅ |
| ROD = mois moyen | Feuille SIMULATEUR * = pilote plat ; annuel = × 12 | ✅ |
| IA = profil mensuel | 12 mois distincts prédits par XGBoost | ✅ |
| ROD par hôtel | Règle 1 Excel : `clients/mois = chambres × TO × guests × 30.5` | ✅ |http://127.0.0.1:5000/
| Jointure `hotel_id` | Registre `data/reference/hotel_identity_registry.json` | ✅ |
| Feature store | `rod_ia/feature_store/hotels/{hotel_id}/` (POI, targets, historique) | ✅ |
| Train IA | Historique ventes **&lt; 2026** → moyennes mensuelles + % (3 niveaux) | ✅ |
| Validation 2026 | Mois présents uniquement ; règle de 3 pour annualiser le réel | ✅ |
| POI proches | Rayons **0.1–0.5 km** (`settings.default_poi_radii_km`) | ✅ |
| Pipeline séparé | `./init.sh` construit · `./run.sh` sert · `./test.sh` teste | ✅ |
| Traçabilité règles | `RuleTrace` : lien Python ↔ cellule Excel | ✅ (partiel) |

---

## 3. Consignes par thème

### 3.1 Architecture et simulation

**Consigne** : comparer ROD Excel et IA sur 3 concepts ; afficher coûts, marges et pipeline IA (6 étapes) ; recommander le concept à la meilleure marge nette ROD.

**Implémentation** :
- `SimulationOrchestrator` — orchestre les 3 concepts
- `RodSimulator` — revenus + coûts déterministes
- `AIPnlService` — prédiction → % → CA → marge produit → coûts → marge nette
- UI : 4 onglets (infos, contraintes, résultats, performance)

### 3.2 Récapitulatif ROD dans le ML

**Consigne** : intégrer les variables du fichier `Récapitulatif de l'ensemble des données ROD (2).xlsx` ; imputer les trous ; exclure les variables constantes.

| Étape | Service | Sortie |
|-------|---------|--------|
| Extraction | `rod_recap_extractor.py` | `data/reference/rod_recap.*` |
| Imputation | `feature_imputer.py` | `imputation_report.json` |
| Sélection | `feature_selector.py` | `feature_selection_report.json` |
| Merge | `sales_targets_pipeline.py` | `d_recap_*` dans `X_descriptive.csv` |

**Imputation** :

| Type | Stratégie |
|------|-----------|
| Booléen | `0` |
| TO / guests | Pilote marque |
| Nb chambres | Registre identité |
| Panier | CA train / ventes train |
| Taux acheteur | Ventes / clients (C21) |
| Autres numériques | Médiane globale |
| Texte | Exclu de X |

Résultat actuel : ~142 colonnes extraites → **18 conservées** + variables dérivées (`d_clients_mois`, `d_taux_acheteur`, …).

### 3.3 Modèle IA

**Consigne initiale** : XGBoost sur moyennes mensuelles historiques ; test sur 2026 ; pas de somme brute des années.

**Implémentation actuelle** :

| Élément | Valeur |
|---------|--------|
| Algorithme | `MultiOutputRegressor(XGBRegressor)` |
| Features | 199 colonnes `d_*` |
| Targets entraînées | 24 globales (`t_m{01..12}_ca_total`, `t_m{01..12}_ventes_total`) |
| Hyperparamètres | `n_estimators=120`, `max_depth=4`, `lr=0.08`, `subsample=0.9`, `colsample_bytree=0.9` |
| Artefacts | `rod_ia/artifacts/model.joblib` |

**Interprétation** (consigne 2026-07-02) : page `/interpretation` + API `/api/model-interpretation` — importance globale/hôtel, config modèle, règles globales et par hôtel.

### 3.4 Performance ROD vs IA

**Consigne** : onglet dédié ; comparer sur l'année 2026 partielle.

Constat (5 hôtels, ~4 mois 2026) :
- Écart moyen absolu période : ROD **69,7 %** · IA **49,9 %**
- IA meilleure sur **2 / 5** hôtels — instable hôtel par hôtel

**Causes identifiées** :
1. n=6 hôtels train — variance élevée
2. POI/météo/plage pas fusionnés systématiquement dans `X_descriptive.csv` au init
3. Décalage train (targets globales) ↔ inférence (reconstruction via % TYPE/GAMME)
4. Petit échantillon → sur-apprentissage possible

### 3.5 Mix produits (UI contraintes)

**Consigne** : catégories = **F&B / NON-F&B** uniquement ; sous-catégories = **GAMME** du CSV ventes (ne pas inventer) ; sliders 0–100 % (pas cases à cocher) ; afficher le reste à distribuer ; bouton distribuer équitablement.

**Source** (`001.queryVentes.csv`) :
- TYPE : `F&B`, `NON-F&B`
- GAMME : ACCESSOIRES, ALCOOL, COSMETIQUE, FOOD SALEE, FOOD SUCREE, JEUX / ENFANTS, PAP, SANS ALCOOL, SOS, SOUVENIRS

**API** : `GET /api/sales-catalog`

### 3.6 Enrichissement géographique

**Consigne** : feature distance minimale à la plage (ex. maillots).

**Implémentation** : `EnrichHotelService` → `d_nearest_beach_m`, `d_nearest_beach_km` (Overpass : `natural=beach`, `leisure=beach_resort`). Sentinelle `99999` si aucune plage dans le rayon.

**À faire** : merger systématiquement POI/météo/plage dans le dataset train au `init.sh` (voir backlog §4).

### 3.7 Opérationnel

| Consigne | Statut |
|----------|--------|
| Tests unitaires hors `init.sh` → `test.sh` | ✅ |
| `.venv` et gros fichiers hors git (`.gitignore`) | ✅ |
| README détaillé (composants, flux, modèle) | ✅ |
| Un seul fichier consignes dans `docs/` | ✅ |

---

## 4. Backlog — amélioration IA

Ordre recommandé : **A1 → A2 → B1 → B3 → évaluation → B2**

### Phase A — Features

| # | Action | Statut |
|---|--------|--------|
| A1 | Distance plage (`d_nearest_beach_*`) | ✅ |
| A2 | Fusion POI/météo/plage dans `X_descriptive.csv` au init | ⏳ |
| A3 | Features ventes dérivées (panier, top gammes par hôtel) | ⏳ |
| A4 | Conserver plus de booléens récap après sélection | ⏳ |

### Phase B — Modèle

| # | Action | Statut |
|---|--------|--------|
| B1 | Hiérarchie cible : CA global puis résiduel % TYPE/GAMME | ⏳ |
| B2 | Régularisation + leave-one-hotel-out CV | ⏳ |
| B3 | Blend `α × ML + (1-α) × ROD_scaled` par marque | ⏳ |
| B4 | Fallback ROD si confiance faible (hors pivots) | ⏳ |
| — | Stacking OOF (consigne initiale) | ⏳ |

### Phase C — Données

| # | Action | Statut |
|---|--------|--------|
| C1 | Plus d'hôtels pivots dans le registre | ⏳ |
| C2 | Validation temporelle 2025 + test 2026 | partiel |
| C3 | Cibles lissées (moyenne mobile multi-années) | ⏳ |

---

## 5. Ce qu'il ne faut pas faire

- Utiliser `old/` ou les notebooks comme source de vérité métier
- Sommer les ventes historiques par mois au lieu de moyenner
- Encoder des catégories texte du récap dans X (fuite d'identité)
- Traiter la config store comme entrée utilisateur
- Committer `.venv`, `sources/raw/`, `*.joblib`
- Inventer des GAMME ou TYPE hors CSV ventes

---

## 6. Références

| Document | Rôle |
|----------|------|
| [`README.md`](../README.md) | Architecture complète, flux, API, composants |
| `rod_ia/web/docs/index.html` | Doc code auto-générée (`./init.sh`) |
| http://127.0.0.1:5000/interpretation | Interprétation modèle IA |

---

## 7. Template — nouvelles consignes

```markdown
### [DATE] — Titre

**Consigne**
> …

**Réponse / statut**
- …
```