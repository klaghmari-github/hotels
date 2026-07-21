# Package `prepare`

Pipeline de préparation des données pour le modèle — **package Python importable**.

## Architecture

```
RodPrep ──► MeteoPrep ────┐
        ├──► ProximityPrep ─┼──► AllPrep → dataset_full
        ├──► HolidaysPrep ──┤
        └──► SalesPrep ─────┘
```

**RodPrep est la source de vérité** : code Accor (`hotel_code` = `code_h`), noms, marque, ville, `hotel_lat` / `hotel_lon`.  
MeteoPrep, ProximityPrep, HolidaysPrep et SalesPrep **consomment** cette table ; ils ne redéfinissent pas l’identité hôtel.

## Package Python

| Import | Rôle |
|--------|------|
| `prepare.rod_prep` | Extraction Excel récap + lookup identité |
| `prepare.meteo_prep` | Météo mensuelle au point (lat, lon) |
| `prepare.proximity_prep` | POI commerces + distance plage |
| `prepare.holidays_prep` | Fériés + vacances scolaires par mois (zone via coords) |
| `prepare.sales_prep` | Agrégations ventes 1.a→7 + `hotel_code` |
| `prepare.all_prep` | Jointure finale |
| `prepare.pipeline` | Orchestrateur `PreparePipeline` |
| `prepare.paths` | Chemins Input/Output par étape |
| `prepare._shared` | Colonnes, mois, chargement ventes |

### Usage

```python
from prepare import PreparePipeline, RodPrep, HolidaysPrep, default_paths

result = PreparePipeline().run()
# ou seulement HolidaysPrep
paths = default_paths()
prep = HolidaysPrep(paths.holidays_input, paths.holidays_output, target_years=(2024, 2025))
prep.fill_input_from_rod(paths.rod_output)
df = prep.run()  # → Output/holidays_monthly.xlsx
```

### CLI

```bash
python run_prepare.py
python run_prepare.py --skip-meteo --skip-proximity
python run_prepare.py --skip-holidays
python -m prepare --holdout-year 2026
```

## Données par étape (Input / Output / Explore)

Les dossiers d’artefacts restent à la racine de chaque étape :

| Dossier | Code (package) | Artefacts |
|---------|----------------|-----------|
| `RodPrep/` | `prepare.rod_prep` | `Input/`, `Output/`, `Explore/` |
| `MeteoPrep/` | `prepare.meteo_prep` | idem |
| `ProximityPrep/` | `prepare.proximity_prep` | idem |
| `SalesPrep/` | `prepare.sales_prep` | idem |
| `AllPrep/` | `prepare.all_prep` | idem |

Les anciens chemins `*/Src/*_prep` sont des **shims** de compatibilité pour les notebooks ; le code source canonique vit sous `prepare/{rod,meteo,proximity,sales,all}_prep/`.

## Identifiants — ne pas confondre

| Champ | Exemple | Rôle |
|-------|---------|------|
| `hotel_code` | `H2075` | **Code Accor** (`code_h` RodPrep) — clé de jointure |
| slug registre | `ibis-budget-nice` | Identité interne registry / feature store historique |
| `hotel_name` / `nom_hotel` | `Ibis budget Nice` | Libellés (jointure ventes) |

`hotel_code` n’est **jamais** un nom d’hôtel.

## Documentation par étape

- [RodPrep/README.md](RodPrep/README.md)
- [MeteoPrep/README.md](MeteoPrep/README.md)
- [ProximityPrep/README.md](ProximityPrep/README.md)
- [SalesPrep/README.md](SalesPrep/README.md)
- [AllPrep/README.md](AllPrep/README.md)
