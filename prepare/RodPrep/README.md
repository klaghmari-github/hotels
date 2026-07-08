# RodPrep — Étape 1

Extraction et structuration des données hôtel saisies dans le récapitulatif Excel ROD et du registre d'identité.

## Objectif

Produire une table de liaison entre le nom d'hôtel (ventes), le code hôtel canonique (`hotel_code`), la marque, la ville et les coordonnées. Cette table sert d'entrée aux étapes MeteoPrep, ProximityPrep et SalesPrep.

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `Input/` | `recapitulatif_rod.xlsx` (copié depuis `sources/raw/` si absent) |
| `Output/` | `hotel_lookup.parquet`, `rod_features.parquet`, exports CSV intermédiaires |
| `Src/rod_prep/prep.py` | Classe `RodPrep` |

## Entrées

### Excel récapitulatif (`Input/recapitulatif_rod.xlsx`)

Feuille **RECAP DATA ROD** — une colonne par hôtel pivot, lignes descriptives.

| Champ source (Excel) | Description |
|---------------------|-------------|
| Colonne 2 — Étape | Regroupement thématique (informations générales, équipements…) |
| Colonne 3 — Sous-étape | Sous-section |
| Colonne 4 — Libellé donnée | Nom de la variable (TO, chambres, bar, spa…) |
| Colonnes 11+ — En-tête hôtel | Nom court pivot (NICE, STRASBOURG, TOUR EIFFEL…) |
| Cellule (ligne, colonne hôtel) | Valeur brute (nombre, %, OUI/NON, texte) |

### Registre identité (`data/reference/hotel_identity_registry.json`)

| Champ source | Description |
|--------------|-------------|
| `hotel_id` | Code canonique (ex. `ibis-budget-nice`) |
| `name_ventes` | Libellé dans le fichier ventes (`NOM BOUTIQUE`) |
| `name_display` | Nom affiché |
| `name_rod` | Libellé dans le récap Excel |
| `brand` | Marque (IBIS BUDGET, NOVOTEL…) |
| `city` | Ville |
| `lat_nominatim`, `lon_nominatim` | Coordonnées géocodées |
| `lat_canonical`, `lon_canonical` | Coordonnées de référence |
| `nb_chambres` | Nombre de chambres |

## Traitement

1. Lecture de la feuille RECAP DATA ROD via `RodRecapExtractor`.
2. Transformation long → wide : chaque ligne descriptive devient une colonne `d_recap_*`.
3. Résolution colonne Excel → `hotel_code` via `RECAP_COLUMN_TO_HOTEL_ID` et le registre identité.
4. Normalisation des valeurs brutes :
   - OUI / YES / X → `1`
   - NON / NO → `0`
   - Pourcentages (`65%`) → valeur décimale (`0.65`)
   - Nombres français (`1,5`) → float
5. Construction de `hotel_lookup` par fusion registre + features récap.

## Sorties calculées

### `hotel_lookup` (table principale)

| Champ | Méthode |
|-------|---------|
| `hotel_code` | `hotel_id` du registre |
| `hotel_name` | `name_display`, sinon `name_ventes`, sinon `hotel_id` |
| `nom_hotel` | `name_ventes` (clé de jointure ventes) |
| `hotel_brand` | `brand` |
| `hotel_city` | `city` |
| `hotel_lat` | `lat_nominatim` ou `lat_canonical` |
| `hotel_lon` | `lon_nominatim` ou `lon_canonical` |
| `nb_chambres` | `nb_chambres` du registre |
| `d_recap_*` | Une colonne par variable du récap (préfixe ML `d_recap_`) |

### `rod_features` (wide récap seul)

| Champ | Méthode |
|-------|---------|
| `hotel_id` | Code hôtel |
| `d_recap_{etape}_{sous_etape}_{libelle}` | Valeur normalisée de la cellule Excel |

## Formules et règles

**Clé de colonne récap :**

```
field_key = slug(etape + "_" + sous_etape + "_" + libelle)
feature_column = "d_recap_" + field_key
```

**Slug :** minuscules, accents supprimés, caractères spéciaux → `_`.

**Jointure lookup :**

```
hotel_lookup = registre LEFT JOIN rod_features ON hotel_code = hotel_id
```

## Exécution

```bash
python run_prepare.py   # étape 1 incluse
```

Ou en Python :

```python
from rod_prep.prep import RodPrep
prep = RodPrep("prepare/RodPrep/Input", "prepare/RodPrep/Output")
prep.seed_input_from_sources()
lookup = prep.run()
```