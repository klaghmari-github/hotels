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
| `holidays_monthly.xlsx` | Feuille `holidays_monthly` + `resume_annuel` |
| `holidays_monthly.parquet` / `.csv` | Même grain `hotel_code × annee × mois` |

## Notes

- La **date de fin** du calendrier scolaire education.gouv = jour de reprise → **exclue**.
- Un jour à la fois férié et en vacances compte dans `nb_jours_feries` et `nb_jours_vacances_scolaires`, mais **pas** dans `nb_jours_vacances_hors_feries`.
