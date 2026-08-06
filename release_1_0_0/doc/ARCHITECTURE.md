# Architecture release 1.0.0

Principe : **chaque logique vit a sa place** ; le haut niveau (`run.py`, `main.py`, API/web)
**appelle** sans reimplementer.

## Couches

```
run.py / main.py / src/web / src/api     ← orchestration & exposition
        │
        ▼
src/sim_v1  src/sim_v2  src/ml           ← metier
        │
        ▼
src/pipeline                             ← runtime pipelines DuckDB
        │
        ▼
pipeline/*.yaml  +  data/files  +  data/duckdb
```

## `src/pipeline` — runtime (agnostique metier)

| Module | Role |
|--------|------|
| `paths.py` | Chemins release + `release_root()` |
| `connection.py` | `PipelineFactory` (ouvre main.duckdb + charge YAML) |
| `engine.py` | `ConnectionUtils`, `ConnectionPipeline`, `DependencyTree`, parallelisation (`ParallelIterationManager`, fingerprints, workers), helpers de schema |

Fonctions cles conservees de l'ancien `main.py` :
`process_with_requires`, `p_table_view`, `p_iteration`, `register_dataframe_as_relation`, etc.

## `src/sim_v2` — metier simulateur v2

| Module | Role |
|--------|------|
| `scenarios.py` | `ScenarioGenerator` (cumulatif, equilibres, hash, Excel) |
| `restitution.py` | `run_restitution`, mix normalise, vues d'entree |
| `loo.py` | `run_leave_one_out` |
| `modeling.py` | `main` / `run_modeling_simulation` (ranks → scenarios → iteration) |
| `service.py` | Facade : `build_modeling`, `generate_scenarios`, `run_loo`, `predict` |

## `src/sim_v1` / `src/ml`

Services metier v1 (R1–R4 LOO) et CatBoost ; s'appuient sur `PipelineFactory`.

## Haut niveau

| Fichier | Role |
|---------|------|
| `run.py` | CLI mince |
| `main.py` | **Compatibilite** : reexporte les symboles historiques (`from main import ConnectionPipeline, ScenarioGenerator, main`) sans logique |
| `src/api`, `src/web` | Exposition HTTP |

## Aucune perte fonctionnelle

Tout le contenu de l'ancien `main.py` est conserve :

- runtime pipeline + parallel → `src/pipeline/engine.py`
- scenarios → `src/sim_v2/scenarios.py`
- restitution / LOO / orchestration → `src/sim_v2/{restitution,loo,modeling}.py`
- imports historiques → `main.py` (facade)
