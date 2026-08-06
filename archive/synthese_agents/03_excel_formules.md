# 03 — Excel, formules ROD et logique d’extraction

Cartographie des classeurs sources (archive), des datasets tabulares `accord/data/`, des pipelines d’extraction / reconstruction, et du lien **formules Excel → code Python**.

> Dernière cartographie monorepo : 2026-07-25  
> Périmètre : `archive/sources/raw/` + `accord/data/` + scripts d’extraction

---

## 1. Excel archive — sources brutes (format original, formules, non normalisé)

Emplacement : `/media/laghmari/ssd-data/dev/hotels/archive/sources/raw/`

Ces fichiers sont la **source de vérité métier** historique. Ils ne sont **pas** lus au runtime de l’app `accord/` (sauf scripts one-shot). Format « métier Excel » : grilles multi-blocs, formules, feuilles non tabulaires.

| Fichier | Type | Rôle métier | Feuilles / structure (principales) | Consommateurs / extraction |
|---------|------|-------------|------------------------------------|----------------------------|
| **`ROD - Simulateurs + détail des coûts.xlsx`** | `.xlsx` + **formules** | Simulateurs pilote SIMPLY / LIBERTY / CONNECTED ; grilles coûts ; mix & marges ; impact TO | `SIMULATEUR SIMPLY`, `SIMULATEUR LIBERTY`, `SIMULATEUR CONNECTED` ; `COUTS - TECHNOS`, `COUTS - ANNEXES`, `COUTS - AGENCEMENT` ; `REVENUS - MIX & MARGES`, `REVENUS - IMPACT TO` | `RodExcelExtractor` → `rod_reference.json` ; `extract_couts.py` → `couts.xlsx` ; règles `user/rules/*` |
| **`ROD - Paramètres & règles + projections nb. d'hôtels.xlsx`** | `.xlsx` | Projections parc (nb hôtels / tranches chambres), règles de recommandation de concept | `NB CH 1` (stats marques) ; `REGLES POUR RECO DU CONCEPT` | `BrandProjectionsExtractor` → `brand_projections.json` ; reco `RecommendationRules` / archive `recommendation_rules.py` |
| **`Récapitulatif de l'ensemble des données ROD (2).xlsx`** | `.xlsx` | Questionnaire directeur / fiche multi-hôtels **wide** (une colonne = un hôtel) | Feuille principale `RECAP DATA ROD` : étapes / sous-étapes / libellés en lignes ; hôtels dès col. 11 (NICE, STRASBOURG, PARIS CDG, MEGEVE, …) | `RodRecapExtractor` → `rod_recap.long.csv` / `.wide.csv` / features `d_recap_*` ; base conceptuelle de `hotel_data.xlsx` |
| **`Analyse du poids des catégories de produit (2024-2025).xlsm`** | `.xlsm` (macro) | Analyse du poids des catégories F&B / NON-F&B 2024–2025 | Feuilles d’analyse métier (non normalisées) | Référence analytique ; non pipeline runtime `accord` |
| **`001.queryVentes.csv`** | `.csv` | Export tickets de vente bruts (NOM BOUTIQUE, DATE, EAN, TYPE, GAMME, prix, …) | Fichier plat ligne-ticket | Import → `hotel_sales_raw_data.xlsx` via `sales_prep.import_raw_from_csv` / `ensure_raw_sales_from_archive` |

### 1.1 Simulateur — cellules clés (formules)

Feuilles `SIMULATEUR {CONCEPT}` (valeurs **mois moyen pilote**) :

| Cellule / zone | Signification | ID règle |
|----------------|---------------|----------|
| `C9` | Nb chambres pilote | pivot |
| `C10` | Guests / chambre | pivot |
| `C11` | Taux d’occupation pilote | pivot |
| `F9` | Mètres linéaires pilote | REV-13 |
| `I9` / `I10` | Mix F&B / NON-F&B | REV-09 |
| `J9` / `J10` | Coefs marge F&B / NON-F&B | REV-16/17 |
| `C16` | Clients / jour = `(C10×C9)×C11` | REV-01 |
| `C17` | Clients / mois = `C16×30,5` | REV-02 |
| `C19` | Ventes mensuelles pilote | base sales |
| `C21` | Taux acheteur = `C19/C17` | REV-03 |
| `E34` / `E35` (ou `E120`/`E121`) | CA HT F&B / NON-F&B pilote | base CA |
| `H64–H70` / `O64–O70` | Coeffs Règle 3 catégories | REV-10 |
| Lignes 147–151 | Coûts techno (scanner/caisse/frigo, vitrine, licence, frais OS) | COST-01 |
| Lignes 155–158 | Annexes (élec., staff) | COST-02 |
| `E166` / `H166` | Agencement capex total / mensuel (`H166 = E166/84`) | COST-03 |
| `H168` | Total coûts mensuels | COST-04 |
| `E176` | Marge nette pilote | REV-19 |

`REVENUS - IMPACT TO` : impact **+1 pt TO** → `F12` (HT), `I12` (TTC) ≈ **9,23 € HT** / 0,01 TO.

### 1.2 Coûts détaillés (feuilles `COUTS - *`)

Blocs par solution **simply / liberty / connected** (colonnes décalées) :

| Feuille | Contenu | Amort. typique |
|---------|---------|----------------|
| `COUTS - TECHNOS` | Matériel, licences, frais ad hoc ; modes buy / lease / mensuel | 60 mois |
| `COUTS - ANNEXES` | Électricité équipements + personnel | 60 mois |
| `COUTS - AGENCEMENT` | m linéaires × disposition classic / premium / bespoke | 84 mois |

Extraction tabulaire : `accord/extract_couts.py` (openpyxl `data_only=True` → valeurs calculées).

### 1.3 Paramètres & règles

| Feuille | Usage |
|---------|--------|
| `NB CH 1` | Effectifs par marque et bandes de chambres → projections brand |
| `REGLES POUR RECO DU CONCEPT` | Règles taille / catégories / marques (IBB, NOV, MER…) |

### 1.4 Récap ROD

Format **non tabulaire « questionnaire »** :

- Lignes = champ (étape, sous-étape, libellé DATA)
- Colonnes hôtel (headers ligne 3) : NICE, STRASBOURG, PARIS CDG, MEGEVE, TOUR EIFFEL, MONTMARTRE, BOULOGNE…
- Mapping vers `hotel_id` canonique dans `RodRecapExtractor.RECAP_COLUMN_TO_HOTEL_ID`
- Sortie historique : `archive/data/reference/rod_recap.{long,wide}.csv` + schéma JSON

---

## 2. Excel `accord/data/` — datasets tabulaires

Emplacement : `/media/laghmari/ssd-data/dev/hotels/accord/data/`

Principe (cf. `schemas.py`) : **un onglet UI = un fichier Excel**, schéma de colonnes déclaratif, rebuilds API / scripts.

| Fichier | Feuille | Grain | Colonnes clés | Comment reconstruit |
|---------|---------|-------|---------------|---------------------|
| **`hotel_brand_data.xlsx`** | `Sheet1` | 1 ligne / marque | `Marque`, `Nb_Hotels`, `Nb_Ch_*`, `Nb_Resto_*`, `Nb_Bar_*` | Saisie UI ; inspiré Excel Paramètres / projections |
| **`hotel_data.xlsx`** | `Sheet1` | 1 ligne / hôtel | `hotel_code`, `hotel_name`, `hotel_brand`, adresse, `hotel_lat/lon`, chambres, TO, équipements lobby/F&B/NON-F&B, profil clients, corner, m_lin | Saisie UI ; issu conceptuellement du **Récap ROD** (wide → une ligne / hôtel) |
| **`hotel_holidays_data.xlsx`** | `hotel_holidays` | hôtel × année × mois | `hotel_code`, `annee`, `mois`, zones scolaires, `nb_jours_*`, listes JSON de jours | `geo_holidays.rebuild_*` (API admin) à partir de lat/lon + calendriers |
| **`hotel_sales_raw_data.xlsx`** | `sales_raw` | 1 ligne / ticket produit | `nom_boutique`, `date`, `code_ean`, `nom_produit`, `quantite`, prix HT/TTC, `type_raw`, `gamme_raw`, `order_id`… | Import CSV archive ou réceptions régulières ; **conservé brut** |
| **`hotel_sales_data.xlsx`** | `hotel_sales` | hôtel × année × mois | volumes (`nombre_ventes`, `montant_ventes`, …), mix `pct_cat_*`, `pct_sous_cat_*`, split holidays | **`sales_prep.rebuild_hotel_sales_data`** depuis raw + holidays |
| **`hotel_weather_data.xlsx`** | `Sheet1` | hôtel × année × mois | lat/lon + métriques météo mean/min/max | `geo_weather` (Meteostat) depuis `hotel_data` + années de ventes |
| **`hotel_proximity_data.xlsx`** | `hotel_proximity` | 1 ligne / hôtel | commerces 100–500 m, plage 1–5 km | `geo_proximity` (Overpass / OSM) |
| **`all_data.xlsx`** | `all_data` | hôtel × année × mois | jointure complète multi-sources | `join_data` — grille parfaite + left joins + fill num. → 0 |
| **`model_data.xlsx`** | `model_data` | sous-ensemble ML | id / descriptive / target | `model_data.rebuild_*` depuis `all_data` (hôtels avec ventes) |
| **`concept_pilote.xlsx`** | `concept_pilote` | **hôtel × année** | clients, CA moyen, mix produits | `concept_pilote.rebuild_concept_pilote` |
| **`couts.xlsx`** | multi-feuilles | grilles coûts long format | `resume`, `couts_technos`, `couts_annexes`, `couts_agencement`, `revenus_*`, `meta` | **`extract_couts.py`** (one-shot) depuis Simulateurs |
| **`rod_reference.json`** | n/a (JSON) | constantes par concept | pivots, mix, marges, `cost_lines`, `impact_to` | `RodExcelExtractor` (archive) ; runtime via `user/reference.py` |
| **`model_data_meta.json`** | n/a | méta rôles colonnes ML | id_detail / descriptive / target | généré avec `model_data` |

### 2.1 Échantillon colonnes (schémas UI)

**Brand** (`_BRAND_EDITABLE`) : `Marque`, effectifs par tranche de chambres et restos/bars.

**Hotel** (`_HOTEL_EDITABLE`) : identité + géo + TO + booléens équipements + profil affaires/loisirs + corner actuel + m_lin + type contrat.

**Sales agrégé** (`_SALES_EDITABLE`) : clés + 4 volumes + nombre/pct catégories mois + `pct_cat_{f_b|n_f_b}_{mesure}` + `pct_sous_cat_{slug}_{mesure}` (11 gammes × 4 mesures) + colonnes holidays.

**Holidays** : compteurs exclusifs (férié / weekend / scolaire) + listes de dates ISO + `pct_jours_holidays`.

**Weather** : 8 familles de métriques × mean/min/max.

**Concept pilote** : voir §5.

### 2.2 Fichiers dérivés hors onglets « source »

| Fichier | Rôle |
|---------|------|
| `all_data.xlsx` | Table unique pour exploration / audit jointure |
| `model_data.xlsx` | Dataset d’apprentissage XGBoost |
| `concept_pilote.xlsx` | Indicateurs annuels pour l’UI concept / moyennes marque |
| `couts.xlsx` | Grilles coûts consultables (pas le runtime simulateur, qui lit le JSON) |

---

## 3. Transformation conceptuelle : non-tabulaire → tabulaire « une fois pour toutes »

Objectif de l’app **Accord** : sortir du format Excel métier (formules, wide, multi-blocs) vers des **tables stables**, jointables sur `hotel_code` (et `annee` / `mois` si temporel).

```
archive/sources/raw/                          accord/data/ (tabulaire)
─────────────────────                         ─────────────────────────
ROD Simulateurs (formules, blocs)     ──►     rod_reference.json
                                              couts.xlsx (long)
ROD Paramètres (NB CH, reco)          ──►     hotel_brand_data.xlsx
                                              (+ règles hardcodées coeffs/reco)
Récap ROD (wide hôtel en colonnes)    ──►     hotel_data.xlsx
                                              (+ historiquement rod_recap.*)
001.queryVentes.csv (tickets)         ──►     hotel_sales_raw_data.xlsx  [conservé]
                                              hotel_sales_data.xlsx      [agrégé]
(lat/lon hotel_data)                  ──►     hotel_holidays_data.xlsx
                                      ──►     hotel_weather_data.xlsx
                                      ──►     hotel_proximity_data.xlsx
jointures                             ──►     all_data.xlsx → model_data.xlsx
ventes + hotel                        ──►     concept_pilote.xlsx
```

| Domaine | Avant (source) | Après (grain) | Script principal |
|---------|----------------|---------------|------------------|
| **Hôtels** | Récap wide + saisie | 1 row / hôtel | UI `store` + schémas ; archive `RodRecapExtractor` |
| **Brand** | Excel paramètres NB CH | 1 row / marque | UI brand |
| **Holidays** | calendriers + CP | hôtel × an × mois | `geo_holidays.py` |
| **Weather** | Meteostat API | hôtel × an × mois | `geo_weather.py` |
| **Proximity** | Overpass OSM | 1 row / hôtel | `geo_proximity.py` |
| **Coûts** | feuilles COUTS + SIMULATEUR | long format / JSON pilote | `extract_couts.py`, `RodExcelExtractor` |
| **rod_reference** | cellules SIMULATEUR * | JSON concepts | extracteur archive → `accord/data/rod_reference.json` |
| **Ventes** | CSV tickets | raw + mensuel | `sales_prep.py` (**exception** : raw non jeté) |

Règles de jointure (`join_data.py`) :

- Base = tous les hôtels de `hotel_data`
- Grille = hôtel × années pertinentes × 12 mois
- Left join ventes / holidays / weather / brand / proximity
- Null numériques → 0 en fin de pipeline

---

## 4. Exception ventes : raw conservé + pipeline automatisé

Contrairement aux autres domaines (transformés une fois puis édités en tabulaire), les **ventes** restent en deux couches :

| Couche | Fichier | Pourquoi |
|--------|---------|----------|
| **Raw** | `hotel_sales_raw_data.xlsx` | Réceptions **régulières** de tickets (CSV ou xlsx) ; audit produit / EAN / TYPE / GAMME ; source du mix « produits distincts » pour `concept_pilote` |
| **Agrégé** | `hotel_sales_data.xlsx` | Grain ML / jointure : mensuel + mix % + split holidays ; **readonly** côté UI (`schemas.sales.readonly=True`) |

### Pipeline `sales_prep.py`

1. **Import** : `001.queryVentes.csv` → `hotel_sales_raw_data.xlsx` (`import_raw_from_csv` / `ensure_raw_sales_from_archive`)
2. **Normalisation colonnes** : `RAW_COLUMN_MAP` (NOM BOUTIQUE → `nom_boutique`, TYPE → `type_raw`, GAMME → `gamme_raw`, …)
3. **`prepare_lines`** :
   - filtre statut DONE
   - parse dates → `annee`, `mois`
   - montants = prix unitaire × quantité (HT prioritaire)
   - TYPE → `f_b` / `n_f_b` ; GAMME → slugs (`food_salee`, `sans_alcool`, …)
   - matching flou `nom_boutique` → `hotel_code` via `hotel_data`
4. **`build_monthly_sales`** : agrégats + pourcentages cat / sous-cat
5. **`attach_holiday_sales`** : split ventes sur `jours_holidays` vs hors holidays
6. Écriture `hotel_sales_data.xlsx` feuille `hotel_sales`

Rebuild : UI admin « Reconstruire depuis Raw » ou API liée à `rebuild_hotel_sales_data`.

---

## 5. `concept_pilote.xlsx` — grain hôtel × année

Fichier : `accord/data/concept_pilote.xlsx`  
Code : `accord/concept_pilote.py`  
Feuille : `concept_pilote`

### Grain

**`hotel_code` × `annee`** (pas de dimension mois).

### Indicateurs (`CONCEPT_PILOTE_COLUMNS`)

| Colonne | Origine / formule |
|---------|-------------------|
| `hotel_code`, `hotel_name`, `hotel_brand` | `hotel_data` |
| `annee` | union des années ventes (sales + raw) |
| `nb_chambres` | `hotel_nb_chambres` |
| `taux_occupation` | `hotel_to_annuel` (normalisé 0–1) |
| `guests_per_chambre` | défauts marque (`BRAND_GUESTS_DEFAULT` : IBB 1,7 ; IBS/MER 2,0 ; …) |
| `clients_jour` | `nb_chambres × TO × guests` |
| `clients_mois` | `clients_jour × 30,5` (`JOURS_MOIS`) |
| `n_mois_renseignes` | count des mois avec CA dans sales |
| `ca_mensuel_moyen` | mean(`montant_ventes`) mensuel sur l’année |
| `n_produits_distincts_f_b` / `_n_f_b` / `_total` | produits distincts (EAN ou nom) depuis **raw** |
| `mix_f_b`, `mix_n_f_b` | parts en **nombre de produits distincts** (pas en CA) |

### Rebuild

`rebuild_concept_pilote()` :

1. charge hotels + sales mensuel  
2. mix prioritaire depuis raw (`prepare_lines`) ; fallback sales agrégé  
3. grille hotel × années ; filtre lignes avec au moins un mois de CA ou des produits  
4. écrit xlsx ; UI admin onglet concept_pilote  

Usages : moyennes par marque pour le wizard / UI (`concept_pilote` loaders).

---

## 6. `extract_couts.py` et `rod_reference.json`

### 6.1 `accord/extract_couts.py`

| | |
|--|--|
| **Source** | `archive/sources/raw/ROD - Simulateurs + détail des coûts.xlsx` |
| **Lecture** | openpyxl `data_only=True` (valeurs **calculées** — le fichier doit avoir été ouvert/sauvé dans Excel/LibreOffice si caches vides) |
| **Sortie** | `accord/data/couts.xlsx` |

Feuilles produites :

| Feuille | Contenu |
|---------|---------|
| `resume` | Synthèse par solution (techno / annexes / personnel / agencement classic 6 m) |
| `couts_technos` | Long : solution, équipement, qty, modes buy/lease/mensuel, amort 60 |
| `couts_annexes` | Électricité + personnel + totaux |
| `couts_agencement` | m_lin × classic/premium/bespoke, amort 84 |
| `revenus_mix_marges` | Mix F&B / N-F&B et marges par solution |
| `revenus_impact_to` | CA pilotes + impact 1 % TO |
| `meta` | provenance |

Usage : `python extract_couts.py` (depuis `accord/`). **One-shot** ; n’est pas le chemin runtime du simulateur user.

### 6.2 `rod_reference.json`

| | Archive | Accord runtime |
|--|---------|----------------|
| Chemin historique | `archive/data/reference/rod_reference.json` | **`accord/data/rod_reference.json`** |
| Producteur | `RodExcelExtractor` (`archive/rod_ia/domain/services/rod_excel_extractor.py`) | même structure, copiée / régénérée |
| Consommateur | pipelines archive | `user/reference.RodReference` → `RevenueRules`, `CostRules` |

Structure (extrait conceptuel) :

```json
{
  "_source": "ROD - Simulateurs + détail des coûts.xlsx",
  "impact_to": { "ht_per_0_01_to": 9.23397…, "ttc_per_0_01_to": 10.40… },
  "concepts": {
    "SIMPLY": {
      "pivot_nb_chambres": 129, "pivot_guests_per_chambre": 1.7,
      "pivot_to": 0.8, "pivot_m_lin": 6,
      "mix_fb": 0.4, "mix_nf": 0.6,
      "margin_fb_pct": 2.6, "margin_nf_pct": 1.45,
      "base_monthly_sales": 231,
      "base_monthly_ca_fb": 533, "base_monthly_ca_nf": 187,
      "monthly_cost_total": 247.14…,
      "cost_lines": { "techno": [...], "annexes": [...], "agencement": {...} },
      "techno_monthly": 75, "annexes_monthly": 15,
      "agencement_per_m": 2200, "amort_months": 84
    },
    "LIBERTY": { "...": "..." },
    "CONNECTED": { "...": "..." }
  }
}
```

Mapping cellules Excel (audit `archive/scripts/extract_excel_rules.py`) :

| Clé JSON | Feuille | Cellule |
|----------|---------|---------|
| `concepts.SIMPLY.pivot_nb_chambres` | SIMULATEUR SIMPLY | C9 |
| `concepts.SIMPLY.pivot_to` | | C11 |
| `concepts.SIMPLY.pivot_m_lin` | | F9 |
| `concepts.SIMPLY.base_monthly_ca_fb` | | E34 |
| `concepts.SIMPLY.base_monthly_ca_nf` | | E35 |
| `concepts.SIMPLY.base_monthly_sales` | | C19 |
| `concepts.SIMPLY.margin_fb_pct` | | J9 |
| `concepts.SIMPLY.monthly_cost_total` | | H168 |
| `impact_to.ht_per_0_01_to` | REVENUS - IMPACT TO | F12 |

Lignes coûts extracteur : techno 147–150, annexes 155–157, agencement E166/H166/C166.

---

## 7. Lien formules Excel ROD → code Python

Documentation détaillée d’audit : `archive/docs/rod_rules.md`.  
Implémentation **Accord user** (découplée revenus / coûts) :

| Module | Rôle |
|--------|------|
| `accord/user/rules/revenue.py` | `RevenueRules` — CA, ventes, marge produit |
| `accord/user/rules/costs.py` | `CostRules` — techno + annexes + agencement amorti |
| `accord/user/rules/recommendation.py` | Concepts autorisés + best marge nette |
| `accord/user/rules/coeffs.py` | Coeffs Règle 3 + marques + LIBERTY NFB |
| `accord/user/models.py` | `HotelOperatingState` (`clients_jour`, `clients_mois`, `JOURS_MOIS=30.5`) |
| `accord/user/reference.py` | Lecture `rod_reference.json` |
| `accord/user/services/orchestrator.py` / `simulator.py` | Orchestration 3 concepts |

(Archive miroir : `rod_ia/domain/rules/{revenue,cost,recommendation}_rules.py`.)

### 7.1 Clients hébergés (REV-01 / REV-02)

| Excel | Python |
|-------|--------|
| `C16 = (C10×C9)×C11` | `clients_jour = nb_chambres × TO × guests` |
| `C17 = C16×30,5` | `clients_mois = clients_jour × 30.5` (`HotelOperatingState`, `concept_pilote`) |

Pilote : `clients_pilote = pivot_nb × pivot_to × pivot_guests × 30.5`  
(`RevenueRules.compute`)

### 7.2 Impact TO (REV-06 / REV-07)

| Excel | Python |
|-------|--------|
| Feuille IMPACT TO, ~9,23 € HT / 0,01 TO | `impact_to = (to_hotel - pivot_to) / 0.01 × ht_per_0_01_to` réparti F&B/N-F&B proportionnellement au CA ref |

→ `RevenueRules.apply_to_impact`

### 7.3 Règle 1 — clients / taux acheteur (REV-03…05)

| Excel | Python |
|-------|--------|
| `C21 = C19/C17` | `taux_acheteur = ventes_ref / clients_pilote` |
| Projection ventes `M19 = M17×C21` | `nbr_ventes = taux_acheteur × clients_hotel` |
| Facteur clients | `ca *= clients_hotel / clients_pilote` (`rule1_clients`) |

### 7.4 Règle 2 — mix ±10 % (REV-08 / 09)

| Excel | Python |
|-------|--------|
| Ajustement mix F&B / NON-F&B par pas de 10 % | `unit_fb = (ca_fb_ref × 0.10) / ref_mix_fb` ; `steps = (user_mix − ref_mix) × 10` ; `ca += unit × steps` |

→ `RevenueRules.rule2_mix` (`MIX_STEP = 0.10`)

### 7.5 Règle 3 — catégories / besoins clients (REV-10…12)

| Excel | Python |
|-------|--------|
| Coeffs H64–H70 (F&B), O64–O70 (N-F&B) | `RULE3_FB_COEFFS` / `RULE3_NFB_COEFFS` dans `coeffs.py` |
| Baseline assortiment complet | `RULE3_BASELINE_FB` / `_NF` = somme des coeffs |
| Delta relatif | `ca ← ca + ca × (cumul − baseline)` |

→ `rule3_categories` + `cumul_rule3(client_needs)`

### 7.6 Règle 4 — mètres linéaires (REV-13 / 14)

| Excel | Python |
|-------|--------|
| `O112 = O94 ± (E34/F9)×|Δm_lin|` | `unit = ca_ref / pivot_m_lin` ; `ca ± unit × |m_lin − pivot_m_lin|` |
| Coût agencement `E166 = capex_per_m × m_lin` | `CostRules` : `agencement_capex = per_m × m_lin` ; mensuel `/ amort_months` (84) |

→ `RevenueRules.rule4_m_lin` + `CostRules.compute`

### 7.7 Marge produit (REV-16…18)

| Excel | Python |
|-------|--------|
| `E132 = E120 − (E120/E128)` avec coef J9 | `marge = CA − CA/coef` (`marge_produit`) |
| Total E134 = F&B + NON-F&B | somme des deux branches |

### 7.8 Coûts amortis (COST-01…04)

| Excel | Python |
|-------|--------|
| Lignes techno / annexes (qty × capex / monthly) | `cost_lines` dans JSON ; `_line_monthly` : si `monthly_unit` sinon `capex/amort` |
| Agencement H166 = E166/84 | `agencement_m = (per_m × m_lin) / 84` |
| H168 = Σ | `monthly = techno_m + annexes_m + agencement_m` |

→ `CostRules.compute` ; fallback agrégats `techno_monthly` / `annexes_monthly` si `cost_lines` absents.

### 7.9 Recommandation concept (RECO-01…04)

| Excel (Paramètres) | Python |
|--------------------|--------|
| Règle taille &lt; 50 ch → SIMPLY | `allowed_concepts` : `n < 50` → `["SIMPLY"]` |
| N-F&B lifestyle → LIBERTY | `LIBERTY_NFB_NEEDS` (cosmetics, kids, apparel, accessories, souvenirs) |
| Choix final | meilleure **marge nette** parmi concepts autorisés |

### 7.10 Formule consolidée (alignée colonnes O SIMULATEUR)

```
clients_pilote = pivot_nb × pivot_to × pivot_guests × 30.5
clients_hotel  = nb_chambres × to_hotel × guests_hotel × 30.5

ca_fb, ca_nf ← ca_fb_ref, ca_nf_ref + impact_TO réparti
ca_fb, ca_nf ← ca × (clients_hotel / clients_pilote)          # R1
ca_fb, ca_nf ← ca + unit_mix × steps_mix                       # R2
ca_fb, ca_nf ← ca + ca × (cumul_coeffs − baseline)             # R3
ca_fb, ca_nf ← ca ± (ca_ref / m_lin_pilote) × |Δm_lin|         # R4

ventes_mensuelles = (ventes_pilote / clients_pilote) × clients_hotel
marge_produit     = Σ (CA − CA/coef_marge)
coûts_mensuels    = Σ techno + annexes + agencement(m_lin)
marge_nette       = marge_produit − coûts_mensuels
ca_annuel         = ca_ht_mensuel × 12
```

---

## 8. Cartes de dépendance rapides

### Sources → artefacts

```
Simulateurs.xlsx ──RodExcelExtractor──► rod_reference.json ──► RevenueRules / CostRules
                 ──extract_couts.py───► couts.xlsx
Paramètres.xlsx  ──BrandProjections───► brand_projections.json (archive)
                 ──(règles reco)──────► RecommendationRules / coeffs.py
Récap.xlsx       ──RodRecapExtractor──► rod_recap.* (archive) / logique hotel_data
queryVentes.csv  ──sales_prep─────────► hotel_sales_raw + hotel_sales_data
hotel_data       ──geo_*──────────────► holidays, weather, proximity
sources multi    ──join_data──────────► all_data → model_data
hotel + sales    ──concept_pilote─────► concept_pilote.xlsx
```

### Où lire la doc métier

| Doc | Contenu |
|-----|---------|
| `archive/docs/rod_rules.md` | Catalogue complet REV/COST/RECO + statut d’implémentation |
| `archive/docs/consignes.md` / `sources/raw/docs/consignes.md` | Hiérarchie sources de vérité |
| `accord/README.md` | Architecture app Data & Model Studio + simulateur user |
| `accord/schemas.py` | Contrat colonnes de chaque Excel `data/` |

---

## 9. Synthèse opérationnelle

1. **Les Excel archive** portent encore les **formules** et le layout métier ; ils ne sont plus le runtime de l’UI Accord, mais restent source d’extraction.
2. **`accord/data/`** matérialise le passage **tabulaire** : hôtels, brand, holidays, weather, proximity, ventes agrégées, jointures, coûts long format.
3. **Exception ventes** : le raw est **conservé** pour les imports récurrents et le détail produit ; l’agrégé est rebuildable.
4. **`rod_reference.json`** est le pont constantes Excel → moteur déterministe ; **`couts.xlsx`** est la vue tabulaire des grilles (one-shot).
5. **`concept_pilote.xlsx`** agrège les indicateurs annuels (clients, CA, mix distinct) pour le pilotage / UI, en réutilisant la même formule clients `× 30,5` que le simulateur.
6. Toute évolution des règles ROD doit partir des cellules documentées dans `rod_rules.md` et se refléter dans `user/rules/*` + éventuellement re-extraction du JSON.

---

*Fichier généré pour la série `synthese_agents/` — exploration monorepo hotels.*
