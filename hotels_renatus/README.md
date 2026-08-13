# hotels_renatus

Projet **consommateur** de l’outil [renatus](../renatus/) pour les flux
**Accor ROD** (sim_v1, sim_v2, ml, ROI).

Le package `renatus` reste générique. Ici : zones + composants métier SQL-first.

## Zones

| Zone | Rôle | SQL / Python |
|------|------|----------------|
| `sources` | Excel → tables communes | dataframe + table SQL |
| `build_sim_v1` | Params, refs, R1–R4, LOO v1 | views + iterate |
| `build_sim_v2` | Sales, ranks, scénarios, pivot, coeffs, LOO v2 | views + iterate parallèle |
| `build_ml` | Contexte rich + dataset train | views SQL |
| `estimate_sim_v1` | 1 ligne leviers → CA / marge | **SQL pur** (R1–R4) |
| `estimate_sim_v2` | 1 ligne → CA restitution | **SQL pur** (coeffs) |
| `estimate_ml` | 1 ligne → CA chaîne ml | SQL features + **Python** scoring |
| `roi` | Marge − coûts, payback | **SQL pur** |

Présences multi-zones via **symlinks** (même id, fichier unique) :  
ex. `estimate_sim_v1/t_pilot_defaults.yaml` → `build_sim_v1/…`.

## Layout

```
hotels_renatus/
  hotels_renatus.renatus.yaml
  flow/                 # YAML monocomposants + zones
  input → release_1_0_0/data/files/input   # symlink sources
  input_estimate/       # lignes d'estimation (xlsx)
  data/main.duckdb      # runtime (recréable)
  scripts/bootstrap_and_run.py
  tests/
  doc/RENATUS_MODIFICATIONS.md   # diffs sur le repo renatus
  PLAN_MIGRATION.md
```

## Prérequis

```bash
# renatus
cd ../renatus && source .venv/bin/activate && pip install -e .

# release (modèles ml + service de référence pour parity)
# release_1_0_0/.venv avec deps ML
```

## Créer / exécuter (from scratch)

```bash
cd hotels_renatus

# 1) Base neuve + estimate sim_v1 + ROI + test de parité vs release
../renatus/.venv/bin/python scripts/bootstrap_and_run.py --fresh --parity

# 2) CLI renatus équivalente
../renatus/.venv/bin/renatus data/main.duckdb flow/ process_with_requires v_estimate_sim_v1
../renatus/.venv/bin/renatus data/main.duckdb flow/ process_with_requires v_roi_from_estimate_v1

# 3) Build LOO sim_v1 (plus long)
../renatus/.venv/bin/python scripts/bootstrap_and_run.py --fresh --full-build-v1

# 4) GUI
cd ../renatus && renatus-gui ../hotels_renatus/hotels_renatus.renatus.yaml
```

### Build sim_v2 / ml (lourd)

Après `sources` + sales :

```bash
renatus data/main.duckdb flow/ process_with_requires t_dataset_pivot   # iterate scénarios
renatus data/main.duckdb flow/ process_with_requires v_restitution_solution_coefficients
renatus data/main.duckdb flow/ process_with_requires v_estimate_sim_v2
renatus data/main.duckdb flow/ process_with_requires v_estimate_ml
```

## Tests

```bash
cd hotels_renatus
../renatus/.venv/bin/pytest tests/ -q
```

## Parité release

| Moteur | Méthode renatus | Méthode classique |
|--------|-----------------|-------------------|
| sim_v1 estimate | `v_estimate_sim_v1` | `SimV1Service.predict_from_levers` |
| sim_v2 estimate | `v_estimate_sim_v2` | `SimV2Service.predict` (coeffs build) |
| ml estimate | `t_estimate_ml` | `SuperModelService.predict_row` |
| ROI | `v_roi_from_estimate_v1` | `enrich_prediction_with_costs` |

`scripts/bootstrap_and_run.py --parity` vérifie sim_v1 (tolérance 0,05 €).

## Modifications renatus

Toute évolution du **core** renatus pour ce projet est listée dans  
[doc/RENATUS_MODIFICATIONS.md](doc/RENATUS_MODIFICATIONS.md)  
(actuellement : `RENATUS_DB_PATH` injecté dans `execute_python`).
