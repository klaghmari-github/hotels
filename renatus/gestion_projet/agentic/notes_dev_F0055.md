# Notes dev F0055 — composant execute_python

Date: 2026-08-08  
Role: agent DEVELOPPEUR  
Branche: `F0055` (base main `83b6727` F0054-S4)

## Temps consomme
- Environ **75 min** (exploration architecture steps/GUI + implementation +
  alignement tests testeur + regression F0053/F0054 + CSS + commits)

## Objectif
Composant pipeline/GUI pour executer du code Python dans le `.venv` du
projet (ou un venv configure), sans casser le type SQL `execute`.

## Decisions

1. **Type YAML = `execute_python`** (pas `python` seul) — distinct et explicite
   vs `execute` (SQL / `ExecuteStep`).
2. **Module** `pipeline/steps/python_action.py` :
   - `PythonActionStep` (base) + `ExecutePythonStep`
   - `process` via `subprocess.run([python, "-"], input=script, shell=False)`
   - cwd = `project_dir`, capture stdout/stderr, timeout defaut 60s (max 3600)
   - exit non-zero → `RuntimeError` avec stdout/stderr
3. **Config** :
   - `script` (str, requis)
   - `venv` (optionnel) : dossier venv ou binaire ; relatif a project_dir ou
     absolu ; vide → `<project>/.venv`
   - `timeout` (optionnel, secondes)
   - `requires` (liste, comme les autres actions)
4. **GUI** :
   - `ExecutePythonStepType` + registry front
   - champs DOM `cfg-script` / `cfg-venv` (textarea + path) + data-testid
   - palette, icone, couleurs CSS (`--exec-py`), option select type
   - creation directe graphe (meme pattern que execute/zone)
5. **Pas de shell=True** ; isolation raisonnable (timeout, cwd projet, pas
   injection shell). Pas d'interpreteur systeme si `.venv` absent →
   `FileNotFoundError` explicite.

## Fichiers cles
- `src/renatus/pipeline/steps/python_action.py` (nouveau)
- `src/renatus/pipeline/steps/factory.py` / `__init__.py`
- `src/renatus/pipeline/engine.py` (RESERVED_KEYS + p_table_view guard)
- `src/renatus/gui/static/app/step-types/execute_python.js`
- `src/renatus/gui/static/index.html` (champs form)
- `tests/test_f0055_execute_python.py` (testeur + alignement)
- `tests/test_f0053_s1_steps.py` (REGISTRY 7 types)

## Tests
- `pytest tests/test_f0055_execute_python.py tests/test_f0053_s1_steps.py` OK
- regressions F0052 / F0054-S1 / F0022 / F0015 OK

## Hors perimetre / suite
- Pas de sandbox OS (namespaces, firejail)
- Pas d'injection contextuelle du pipeline dans le script (globals DuckDB)
- Merge = gestionnaire apres notes_test PASS

## Status
Implementation livree sur branche `F0055` ; status features reste `en_cours`
jusqu'au merge gestionnaire.
