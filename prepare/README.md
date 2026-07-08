# Pipeline prepare/

Préparation des données pour le modèle — architecture décrite dans `consignes.txt`.

## Étapes

| # | Dossier | Documentation | Rôle |
|---|---------|---------------|------|
| 1 | [RodPrep/](RodPrep/README.md) | Récap Excel + registre identité → `hotel_lookup` |
| 2 | [MeteoPrep/](MeteoPrep/README.md) | Météo mensuelle 2024–2025 par hôtel |
| 3 | [ProximityPrep/](ProximityPrep/README.md) | Plage et commerces de proximité |
| 4 | [SalesPrep/](SalesPrep/README.md) | Agrégations ventes, imputation, jointure |
| 5 | [AllPrep/](AllPrep/README.md) | Dataset final fusionné |

## Exécution

```bash
python run_prepare.py
python run_prepare.py --skip-meteo --skip-proximity   # sans appels API
```

## Flux

```
RodPrep → MeteoPrep ──┐
       → ProximityPrep ┼→ AllPrep → dataset_full.parquet
       → SalesPrep ────┘
```

Chaque étape documente ses champs source, champs calculés et formules dans son `README.md`.

## Exploration interactive

Chaque sous-dossier contient un notebook `Explore/explore.ipynb` qui :

1. Charge les entrées et affiche les DataFrames pandas à chaque étape
2. Appelle toutes les fonctions de `Src/` (y compris les résultats intermédiaires)
3. Remplit le dossier `Output/` de l'étape

Ordre recommandé : RodPrep → MeteoPrep / ProximityPrep / SalesPrep → AllPrep.