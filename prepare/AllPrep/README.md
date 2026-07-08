# AllPrep — Étape 5

Jointure finale des sorties RodPrep, SalesPrep, MeteoPrep et ProximityPrep en un dataset unique.

## Objectif

Assembler toutes les features préparées sans dupliquer les lignes ventes (grain principal : `hotel_code × annee × mois`).

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `Input/` | Copies des outputs des étapes précédentes |
| `Output/` | `dataset_full.parquet`, `dataset_full.csv` |
| `Src/all_prep/prep.py` | Classe `AllPrep` |

## Entrées

| Fichier Input | Source | Grain |
|---------------|--------|-------|
| `sales_joined.parquet` | SalesPrep `joined` | `nom_hotel`, `hotel_code`, `annee`, `mois` + features ventes |
| `meteo_monthly.parquet` | MeteoPrep | `hotel_code`, `annee`, `mois` + `meteo_*` |
| `proximity.parquet` | ProximityPrep | `hotel_code` + indicateurs géo |
| `rod_hotel_lookup.parquet` | RodPrep `hotel_lookup` | `hotel_code` + attributs hôtel / `d_recap_*` |

## Traitement

Jointures successives en left join pour préserver le grain ventes.

### 1. Base ventes

```
result = sales_joined
```

### 2. Météo (si disponible)

**Clés :** `hotel_code`, `annee`, `mois`

```
result = result LEFT JOIN meteo_monthly ON (hotel_code, annee, mois)
```

Les colonnes météo déjà présentes dans `result` conservent leur nom ; les doublons reçoivent le suffixe `_meteo`.

### 3. Proximité (si disponible)

**Clé :** `hotel_code` uniquement (données statiques par hôtel)

```
result = result LEFT JOIN proximity ON hotel_code
```

Suffixe `_prox` en cas de collision de noms.

### 4. Attributs RodPrep (si disponible)

**Clé :** `hotel_code`

Seules les colonnes absentes de `result` (ou la clé) sont ajoutées :

```
rod_cols = [c for c in rod.columns if c not in result.columns or c == "hotel_code"]
result = result LEFT JOIN rod[rod_cols] ON hotel_code
```

Suffixe `_rod` en cas de collision.

### 5. Nettoyage des noms

```
result.columns = sanitize_column_name(col) pour chaque colonne
```

Règle : minuscules, accents supprimés, apostrophes et caractères spéciaux → `_`.

## Sortie

### `dataset_full`

| Type de champ | Exemples |
|-------------|----------|
| Clés | `nom_hotel`, `hotel_code`, `annee`, `mois` |
| Mesures ventes | `nombre_ventes`, `montant_ventes`, `nombre_paniers`, `nombre_produits` |
| Catégories wide | `cat_f_b_montant_ventes`, `sous_cat_sans_alcool_nombre_ventes` |
| Heure wide | `heure_12_montant_ventes` |
| Week-end wide | `weekend_1_nombre_paniers` |
| Férié wide | `holiday_0_montant_ventes` |
| Météo | `meteo_temperature_c_mean`, `meteo_precipitations_mm_max`, … |
| Proximité | `plage_distance_km`, `commerce_fb_100m`, `distance_alcohol_m`, … |
| Récap hôtel | `d_recap_*`, `hotel_brand`, `nb_chambres`, … |

## Règles de non-duplication

- Le nombre de lignes ventes **ne change pas** lors des jointures météo (même grain temporel).
- Proximité et récap sont des attributs hôtel : répétés sur chaque mois sans multiplication des lignes sales.
- Les jointures sont des `LEFT JOIN` : un hôtel sans météo ou sans proximité conserve ses lignes ventes avec valeurs nulles.

## Exécution

```bash
python run_prepare.py
```

Sortie finale : `prepare/AllPrep/Output/dataset_full.parquet`