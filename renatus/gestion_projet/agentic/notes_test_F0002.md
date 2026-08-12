# Notes testeur — F0002 (fonctionnement correct pipeline)

Date: 2026-08-07  
Role: agent TESTEUR  
Branche: F0002  
Temps passe: **18 minutes** (lecture engine.py / API, redaction tests, pytest, notes)

## Perimetre

Tests unitaires cibles des fonctionnalites pipeline listees dans F0002.  
Bases et fichiers uniquement sous `tmp_path` pytest — jamais la base hotels reelle.  
`test_f0001_init.py` laisse intact et toujours vert.

## Structure creee

```
tests/
  test_f0002_pipeline_features.py   # 7 tests unitaires
  fixtures/f0002/                   # dossier reserve (YAML/CSV generes dans tmp_path)
gestion_projet/
  notes_test_F0002.md               # ce fichier
```

Aucun YAML/CSV metier du depot n'est lu. Les mini-pipelines sont construits dans `tmp_path` a chaque test.

## Cas couverts

| test | objectif | resultat |
|------|----------|----------|
| `test_dataframe_from_csv_then_table_select` | type dataframe + CSV, table `SELECT * FROM df` | PASS |
| `test_table_view_chain_t_a_v_b_t_c` | chaine t_a -> v_b -> t_c | PASS |
| `test_p_table_view_creates_missing_ancestors` | requires absents en base : creation recursive | PASS |
| `test_execute_sql_side_effect_no_relation` | type execute INSERT sans relation nommee | PASS |
| `test_iteration_sequential_one_row_per_scenario` | iteration sequential scenarios/step_view/target | PASS |
| `test_create_if_not_exists_skips_when_present` | mode create_if_not_exists ne recree pas | PASS |
| `test_create_or_replace_rebuilds_table` | mode create_or_replace recree | PASS |

## Commande et resultat pytest

```text
.venv/bin/python -m pytest tests/ -v --tb=short

============================= test session starts ==============================
platform linux -- Python 3.12.4, pytest-9.1.1
collected 13 items

tests/test_f0001_init.py::test_import_package PASSED
tests/test_f0001_init.py::test_public_api_exports PASSED
tests/test_f0001_init.py::test_paths_configurable PASSED
tests/test_f0001_init.py::test_connection_pipeline_empty_yaml PASSED
tests/test_f0001_init.py::test_connection_pipeline_materialize_simple_table PASSED
tests/test_f0001_init.py::test_pipeline_factory_open_with_tmp_paths PASSED
tests/test_f0002_pipeline_features.py::test_dataframe_from_csv_then_table_select PASSED
tests/test_f0002_pipeline_features.py::test_table_view_chain_t_a_v_b_t_c PASSED
tests/test_f0002_pipeline_features.py::test_p_table_view_creates_missing_ancestors PASSED
tests/test_f0002_pipeline_features.py::test_execute_sql_side_effect_no_relation PASSED
tests/test_f0002_pipeline_features.py::test_iteration_sequential_one_row_per_scenario PASSED
tests/test_f0002_pipeline_features.py::test_create_if_not_exists_skips_when_present PASSED
tests/test_f0002_pipeline_features.py::test_create_or_replace_rebuilds_table PASSED

============================== 13 passed in 0.81s ==============================
```

Environnement: `.venv` local (editable install renatus, duckdb, pandas, pyyaml, pytest).

## Decisions testeur (comportement observe dans engine.py)

1. **Chemin CSV / dataframe** : `resolve_project_path` resout un chemin relatif par rapport a `project_dir` = parent du dossier pipeline (si on passe un repertoire). Les tests placent donc le CSV sous `project/input/` et le YAML sous `project/pipeline/` avec `file: input/people.csv`.

2. **step_view et requires** : `validate_pipeline` exige que toute dependance dans `requires` existe comme cle du pipeline. Or `step_view` est une TEMP VIEW creee par `replace_step_view` a chaque tour d'iteration, **hors** definition YAML. Donc `v_step` ne doit **pas** etre dans `requires` du target execute (contrairement a l'exemple naif de la mission). Le SQL du target reference `v_step` directement ; l'iteration la cree avant `process_with_requires(target)`.

3. **API iteration** : `p_iteration("i_run")` appelle `process_with_requires` puis `process_iteration_sequential`. Le target execute est rejoue a chaque scenario (`processed=set()` a chaque tour). `t_results` en `create_if_not_exists` n'est pas recree entre les tours, ce qui permet l'accumulation des INSERT.

4. **execute n'est pas une relation** : `p_table_view` leve `TypeError` sur un objet `execute` / `iteration` ; `table_exists` / `view_exists` / `relation_exists` restent faux pour le nom de l'execute.

5. **Modes** : `should_process` renvoie toujours True pour `create_or_replace` et pour `execute`/`iteration` ; pour `create_if_not_exists` il s'arrete si la relation existe deja.

## Anomalies

Aucune. Tous les tests legitimes passent sans xfail. Code production non modifie.

## Non fait / hors scope

- Iteration parallele (`ParallelIterationManager`) — hors cas demandes
- Commit / push / merge — non (consigne)
- Modification de `features.csv` / `anomalies.csv` — non (consigne ; temps a reporter par le gestionnaire si souhaite)

## Code production

Non modifie (mission testeur pure).
