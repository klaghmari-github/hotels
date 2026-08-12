# Notes testeur — F0055 (composant execute_python)

Date: 2026-08-08  
Role: agent TESTEUR  
Branche: `F0055` (commit `2576380` + working tree)  
Temps passe: **35 minutes** (lecture plan/patterns F0023-F0024/F0052-F0053, harness tests, mock venv, pytest cible + suite, notes)

## Verdict

**PASS**

Tous les AC minimaux sont couverts et verts. Regression execute SQL OK. Suite large verte (hors flake port A0003 environnement).

## Perimetre AC

| AC | Description | Resultat |
|----|-------------|----------|
| 1 | Factory reconnait `execute_python` sans collision avec `execute` SQL | PASS |
| 2 | Script simple via python du `.venv` projet (mock shell) | PASS |
| 3 | `venv` custom (relatif + absolu) respecte | PASS |
| 4 | Exit non-zero / RuntimeError propages (stdout/stderr dans message) ; `last_result` sur succes | PASS |
| 5 | GUI registry + champs script/venv (static JS + HTML data-testid + API create YAML) | PASS |
| 6 | Regression type `execute` SQL toujours OK (+ coexistence meme pipeline) | PASS |

## Fichiers tests

- `tests/test_f0055_execute_python.py` — 17 tests
- Adaptation REGISTRY F0053: `tests/test_f0053_s1_steps.py` (7 types, incl. execute_python) — faite cote dev

## Commande et resultat pytest (cible)

```text
.venv/bin/python -m pytest tests/test_f0055_execute_python.py -v --tb=short

======================== 17 passed, 1 warning in 1.22s =========================
```

Tests:

1. `test_feature_f0055_registered`
2. `test_factory_recognizes_execute_python`
3. `test_factory_rejects_unknown_still`
4. `test_tool_meta_and_catalog_include_execute_python`
5. `test_script_runs_with_project_default_venv`
6. `test_script_runs_via_process_with_requires`
7. `test_custom_venv_config_respected`
8. `test_custom_venv_absolute_path`
9. `test_nonzero_exit_raises`
10. `test_python_exception_propagates`
11. `test_stdout_or_result_available_on_success`
12. `test_gui_static_registry_and_fields`
13. `test_gui_create_step_api_yaml`
14. `test_gui_icons_mention_execute_python`
15. `test_regression_execute_sql_still_ok`
16. `test_execute_and_execute_python_coexist_in_pipeline`
17. `test_build_action_execute_python`

## Suite raisonnable (regression)

```text
.venv/bin/python -m pytest tests/test_f0055_execute_python.py \
  tests/test_f0053_s1_steps.py tests/test_f0002_pipeline_features.py \
  tests/test_f0024_iteration_component.py tests/test_f0052_zone_component.py \
  tests/test_f0054_s1_backend_oop.py tests/test_f0012_gui.py \
  tests/test_f0022_type_icons.py -q --tb=line

74 passed, 1 warning in 3.73s
```

Suite quasi-complete:

```text
.venv/bin/python -m pytest tests/ -q --tb=line \
  --ignore=tests/test_a0003_gui_bootstrap.py

388 passed, 1 deselected, 1 warning in 17.39s
```

### Note flake hors scope

`tests/test_a0003_gui_bootstrap.py::test_gui_server_main_bootstraps_user_order` peut echouer si le port 8765 est deja occupe (message: utilisation du port 8766). Independant de F0055.

## Decisions testeur

1. **Type YAML** : `execute_python` (plan + implementation dev) — distinct de `execute` SQL.
2. **Mock venv** : shell `bin/python` qui log un tag puis `exec` le vrai `.venv` repo — prouve la selection d'interpreteur sans `venv.create` lent.
3. **Skip parallel** : decorateur `requires_execute_python` si type absent du REGISTRY (travail parallele dev) ; devenu no-op une fois le code present.
4. **Echec** : `RuntimeError` avec `exit N` + stdout/stderr (comportement observe dans `python_action.py`).
5. **GUI** : asserts static sur `ExecutePythonStepType`, `data-testid="cfg-script"` / `cfg-venv`, option select, API `POST /gui/steps` + graph.
6. **stdout** : `step.last_result["stdout"]` apres `process` sur instance step (get_step recree une instance propre).

## data-testid UI verifies (static)

- `field-script`, `cfg-script`, `display-cfg-script`, `edit-cfg-script`, `script-hint`
- `field-venv`, `cfg-venv`, `display-cfg-venv`, `edit-cfg-venv`, `venv-hint`
- option `value="execute_python"`
- icon type `execute_python` dans `icons.js`

## Anomalies

Aucune bloquante.  
Hors scope: flake port A0003 si 8765 occupe.

## Verdict final

**PASS**
