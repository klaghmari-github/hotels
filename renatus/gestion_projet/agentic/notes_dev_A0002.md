# Notes correctif A0002

## Probleme
data/ et models/ hotels versionnes ; Paths.ensure() recreait sim_v1/sim_v2/ml/catboost.

## Correctif
- Suppression data/ et models/ du depot
- Paths generique sans attributs hotels
- ensure() no-op ; ensure_db_parent() minimal
- gitignore /data/ /models/
- tests A0002 + F0001 adapte

Temps: ~35 min
