# AllPrep — jointure complète → `hotel_sales_data`

Assemble **toutes** les sorties prepare en un dataset unique, **sans doublons de colonnes**.

## Objectif

Grain principal : `hotel_code × annee × mois` (lignes ventes).

```
sales_joined
  + hotel_holidays_data  (hotel_code, annee, mois)  ← arrays de jours
  + meteo_monthly        (hotel_code, annee, mois)
  + proximity            (hotel_code)
  + rod_hotel_lookup     (hotel_code)
  → hotel_sales_data.xlsx / .parquet / .csv
```

## Règle anti-doublons

Si une colonne existe déjà à gauche, la version droite est **ignorée**  
(pas de `hotel_name_x` / `hotel_name_prox` / etc.).

Source de vérité pour les holidays : `hotel_holidays_data` (remplace d’éventuelles colonnes déjà collées par SalesPrep).

## Entrées (`Input/`)

| Fichier | Source | Clés |
|---------|--------|------|
| `sales_joined.parquet` | SalesPrep | `hotel_code, annee, mois` |
| `hotel_holidays_data.parquet` | HolidaysPrep | `hotel_code, annee, mois` + arrays |
| `meteo_monthly.parquet` | MeteoPrep | `hotel_code, annee, mois` |
| `proximity.parquet` | ProximityPrep | `hotel_code` |
| `rod_hotel_lookup.parquet` | RodPrep | `hotel_code` |

## Sorties (`Output/`)

| Fichier | Rôle |
|---------|------|
| **`hotel_sales_data.xlsx`** | Jointure complète (feuille `hotel_sales`) |
| `hotel_sales_data.parquet` / `.csv` | Idem |
| `dataset_full.*` | Alias rétrocompat |

### Colonnes holidays (arrays)

| Champ | Contenu |
|-------|---------|
| `jours_feries` | liste ISO des jours fériés du mois |
| `jours_vacances_scolaires` | liste des jours de vacances |
| `jours_vacances_hors_feries` | vacances hors fériés |

Excel/CSV : JSON `["2024-01-01", …]` — Parquet : listes natives.

## Exécution

```python
from prepare import PreparePipeline
result = PreparePipeline().run()
# → prepare/AllPrep/Output/hotel_sales_data.xlsx
```
