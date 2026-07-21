# HolidaysPrep — jours fériés & vacances scolaires

Pour chaque hôtel (coords RodPrep) et chaque **année × mois** :

| Colonne | Définition |
|---------|------------|
| `nb_jours_feries` | Nombre de **jours fériés** légaux dans le mois |
| `nb_jours_vacances_scolaires` | Nombre de jours de **vacances scolaires** (zone A/B/C) |
| `nb_jours_vacances_hors_feries` | Vacances scolaires **hors** jours fériés |

## Flux

```
RodPrep (hotel_code, lat, lon)
  → reverse geocode data.gouv → département → zone scolaire
  → calendrier scolaire education.gouv (zone)
  → jours fériés France (calcul + Alsace-Moselle)
  → agrégation mensuelle
  → Output/holidays_monthly.xlsx
```

## Package

```python
from prepare import HolidaysPrep, default_paths

paths = default_paths()
prep = HolidaysPrep(paths.holidays_input, paths.holidays_output, target_years=(2023, 2024, 2025))
prep.fill_input_from_rod(paths.rod_output)
df = prep.run()
```

## Sorties (`Output/`)

| Fichier | Contenu |
|---------|---------|
| **`hotel_holidays_data.xlsx`** | Feuille `hotel_holidays` + `resume_annuel` |
| `hotel_holidays_data.parquet` / `.csv` | Grain `hotel_code × annee × mois` |
| Copie auto | `SalesPrep/Input/hotel_holidays_data.*` (si `sales_input_dir`) |

### Colonnes array (listes de jours ISO)

| Champ | Contenu |
|-------|---------|
| `jours_feries` | `["2024-01-01", "2024-05-01", …]` |
| `jours_vacances_scolaires` | Tous les jours de vacances du mois |
| `jours_vacances_hors_feries` | Vacances **sans** les fériés |

- **Parquet** : listes Python natives  
- **Excel / CSV** : JSON array string  

## Lien SalesPrep

`hotel_sales_data` joint `hotel_holidays_data` sur `hotel_code × annee × mois`  
→ compteurs + arrays disponibles dans `SalesPrep/Output/hotel_sales_data.xlsx`.

## Consommation

`AllPrep` joint `hotel_holidays_data` dans **`hotel_sales_data`** (jointure de toutes les sources), sans dupliquer les colonnes déjà présentes.

## Notes

- La **date de fin** du calendrier scolaire education.gouv = jour de reprise → **exclue**.
- Un jour à la fois férié et en vacances compte dans `nb_jours_feries` et `nb_jours_vacances_scolaires`, mais **pas** dans `nb_jours_vacances_hors_feries` ni dans `jours_vacances_hors_feries`.


