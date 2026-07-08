# SalesPrep — Étape 4

Préparation des ventes : agrégations multi-niveaux, normalisation sur 12 mois, imputation des mois manquants et jointure finale.

## Objectif

Transformer le fichier de ventes ligne à ligne en features mensuelles par hôtel, comparables et complètes sur 12 mois, puis les joindre pour alimenter le feature store et AllPrep.

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `Input/` | `ventes.csv` (copie de `sources/raw/001.queryVentes.csv`) + `hotel_lookup` (RodPrep) |
| `Output/` | `step_1a` … `step_6c`, `joined`, `meta.json` (CSV + Parquet) |
| `Src/sales_prep/` | `pipeline.py`, `aggregations.py` |
| Feature store | `rod_ia/feature_store/hotels/{code}/sales_prep/monthly_features.*` |

## Filtre temporel

```
annee < holdout_year   (défaut : 2026 exclu de l'entraînement)
```

Seules les années strictement antérieures à la dernière année du fichier sont conservées.

---

## Phase 0 — Chargement et champs dérivés

### Champs source (`001.queryVentes.csv`)

| Champ CSV | Usage |
|-----------|-------|
| `NOM BOUTIQUE` | Identifiant hôtel → `nom_hotel` |
| `DATE` / `DATETIME` | Horodatage → `annee`, `mois` |
| `QUANTITE` | Quantité vendue |
| `PRIX TTC` | Prix unitaire TTC |
| `TYPE` | Catégorie F&B / NON-F&B → `categorie` |
| `GAMME` | Sous-catégorie → `sous_categorie` |
| `ORDER ID (TICKET DE CAISSE)` | Ticket caisse → `nombre_paniers` |
| `CODE EAN` | Référence produit → `nombre_produits` |
| `HEURE` | Heure de vente → `heure_vente` |

### Champs calculés (ligne à ligne)

| Champ | Formule |
|-------|---------|
| `montant_ventes` | `QUANTITE × PRIX TTC` |
| `nombre_ventes` | `QUANTITE` (somme à l'agrégation) |
| `nombre_paniers` | Identifiant ticket (décompte `nunique` à l'agrégation) |
| `nombre_produits` | `CODE EAN` (décompte `nunique` à l'agrégation) |
| `categorie` | `TYPE` normalisé : `F&B` → `F_B`, `NON-F&B` → `N_F_B` |
| `sous_categorie` | `GAMME` |
| `heure_vente` | 2 premiers caractères de `HEURE`, ou heure extraite de la date |
| `is_weekend` | `1` si samedi ou dimanche, sinon `0` |
| `is_holiday` | `1` si jour férié fixe France, sinon `0` |
| `hotel_code` | Jointure `nom_hotel` ↔ `hotel_lookup` (RodPrep) |

**Jours fériés retenus :** 1/1, 1/5, 8/5, 14/7, 15/8, 1/11, 11/11, 25/12.

---

## Indicateurs temporels (communs étapes 1 et 2)

Calculés par `(nom_hotel, annee)` à partir des mois ayant au moins une vente :

| Champ | Formule |
|-------|---------|
| `nombre_mois` | Nombre de mois distincts avec ventes |
| `premier_mois` | `min(mois)` |
| `dernier_mois` | `max(mois)` |
| `mois_manquants` | `(premier_mois - 1) + (12 - dernier_mois)` |
| `mois_actifs` | `12 - mois_manquants` |

**Exemple :** ventes en février, juin, septembre → `premier_mois=2`, `dernier_mois=9`, `mois_manquants=4` (janvier + oct.–déc.), `mois_actifs=8`.

**Mois à imputer :** uniquement les mois **hors** de l'intervalle `[premier_mois, dernier_mois]` (pas les mois sans vente à l'intérieur de l'intervalle).

```
mois_imputes = [1 .. premier-1] ∪ [dernier+1 .. 12]
```

---

## Étape 1 — Agrégation annuelle

### 1.a `step_1a` — brut annuel

**Group by :** `nom_hotel`, `annee`

| Champ calculé | Méthode |
|---------------|---------|
| `nombre_ventes` | `SUM(nombre_ventes)` |
| `montant_ventes` | `SUM(montant_ventes)` |
| `nombre_paniers` | `NUNIQUE(nombre_paniers)` |
| `nombre_produits` | `NUNIQUE(nombre_produits)` |
| `nombre_categories_annee_f_b` | `NUNIQUE(sous_categorie)` où `categorie = F_B` |
| `nombre_categories_annee_n_f_b` | `NUNIQUE(sous_categorie)` où `categorie = N_F_B` |
| `pct_categories_annee_f_b` | `nb_F_B / (nb_F_B + nb_N_F_B)` |
| `pct_categories_annee_n_f_b` | `nb_N_F_B / (nb_F_B + nb_N_F_B)` |
| + indicateurs temporels | voir ci-dessus |

### 1.b `step_1b` — annualisé sur 12 mois

Pour chaque mesure dans `{nombre_ventes, montant_ventes, nombre_paniers, nombre_produits}` :

```
valeur_1b = valeur_1a / mois_actifs × 12
```

Les champs `*_f_b` / `*_n_f_b` ne sont pas normalisés (déjà au format annuel).

### 1.c `step_1c` — moyenne mensuelle simple

```
valeur_1c = valeur_1a / 12
```

---

## Étape 2 — Agrégation mensuelle

### 2.a `step_2a` — brut mensuel

**Group by :** `nom_hotel`, `annee`, `mois`

Mêmes mesures que 1.a, avec suffixe `mois` pour les comptages catégoriels (`nombre_categories_mois_f_b`, etc.). Indicateurs temporels repris au niveau année.

### 2.b `step_2b` — imputation mensuelle

Pour chaque mois dans `mois_imputes` :

```
mesure_imputee = SUM(mesure sur mois existants) / mois_actifs
```

Champs catégoriels (`pct_categories_mois_*`) : moyenne arithmétique des mois existants.

---

## Étape 3 — Catégorie et sous-catégorie

### 3.a `step_3a` — brut

**Group by :** `nom_hotel`, `annee`, `mois`, `categorie`, `sous_categorie`

| Mesure | Agrégation |
|--------|------------|
| `nombre_ventes` | `SUM` |
| `montant_ventes` | `SUM` |
| `nombre_paniers` | `NUNIQUE` |
| `nombre_produits` | `NUNIQUE` |

### 3.b `step_3b` — imputation

Par combinaison `(nom_hotel, annee, categorie, sous_categorie)` : ajout des mois imputés avec la même formule que 2.b.

### 3.c `step_3c` — format wide

**Clés :** `nom_hotel`, `annee`, `mois`

Pivot des mesures par `categorie` et par `sous_categorie` :

```
cat_{categorie}_{mesure}       ex. cat_f_b_montant_ventes
sous_cat_{gamme}_{mesure}      ex. sous_cat_alcool_nombre_ventes
```

Noms nettoyés : caractères spéciaux → `_`, minuscules.

---

## Étape 4 — Heure de vente

### 4.a `step_4a`

**Group by :** `nom_hotel`, `annee`, `mois`, `categorie`, `sous_categorie`, `heure_vente`

### 4.b `step_4b` — imputation par heure

Même logique que 3.b, conservant `heure_vente`.

### 4.c `step_4c` — wide

```
heure_{HH}_{mesure}   ex. heure_12_montant_ventes
```

---

## Étape 5 — Week-end

### 5.a / 5.b / 5.c

Identique à l'étape 4 avec `is_weekend` ∈ {0, 1}.

Colonnes wide : `weekend_0_montant_ventes`, `weekend_1_nombre_ventes`, etc.

---

## Étape 6 — Jour férié

### 6.a / 6.b / 6.c

Identique à l'étape 4 avec `is_holiday` ∈ {0, 1}.

Colonnes wide : `holiday_0_montant_ventes`, `holiday_1_nombre_ventes`, etc.

---

## Étape 7 — Jointure

**Tables jointes :** `step_2b`, `step_3c`, `step_4c`, `step_5c`, `step_6c`

**Clés :** `nom_hotel`, `hotel_code`, `annee`, `mois`

```
joined = step_2b
  OUTER JOIN step_3c ON clés
  OUTER JOIN step_4c ON clés
  OUTER JOIN step_5c ON clés
  OUTER JOIN step_6c ON clés
```

Noms de colonnes finalisés par `sanitize_column_name` (apostrophes et caractères spéciaux → `_`).

**Feature store :** une partition par `hotel_code` dans `sales_prep/monthly_features.*`.

---

## Exécution

```bash
python run_prepare.py
```

Tests : `pytest tests/test_sales_prep.py`