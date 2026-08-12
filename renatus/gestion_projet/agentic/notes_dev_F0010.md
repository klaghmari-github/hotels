# Notes dev F0010 — Renatus GUI (GUI web)

Date: 2026-08-07  
Role: agent DEVELOPPEUR  
Branche: F0010 (base main `4ab50fe`)  
Temps passe: **~45 minutes** (impl + tests TDD + validation)

## Perimetre

- Interface web gui : connect db + pipelines, graphe requires, edit config,
  build step, visualiser resultats
- Package `renatus.gui` (POO), reutilise `renatus.api.service.RenatusService`
- Pas de modification `engine.py` / tests F0009
- Pas de merge develop/main, pas de force push
- Pas de modification `features.csv` / `anomalies.csv` (gestionnaire)
- Bases uniquement sous `tmp_path` dans les tests

## Livrables

| Fichier | Action |
|---------|--------|
| `src/renatus/gui/__init__.py` | Exports publics |
| `src/renatus/gui/__main__.py` | `python -m renatus.gui` |
| `src/renatus/gui/schemas.py` | Dataclasses reponse gui |
| `src/renatus/gui/service.py` | `GuiService` + `YamlStepStore` |
| `src/renatus/gui/app.py` | FastAPI UI + routes `/gui/*` |
| `src/renatus/gui/server.py` | CLI `renatus-gui` / uvicorn |
| `src/renatus/gui/static/*` | `index.html`, `app.js`, `style.css` |
| `tests/test_f0010_gui.py` | Tests TDD (service + HTTP + entrypoint) |
| `pyproject.toml` | script `renatus-gui`, package-data static, extra `[gui]` |
| `README.md` | Section GUI |
| `gestion_projet/notes_dev_F0010.md` | Ce fichier |
| `gestion_projet/agentic/plan_F0010.md` | Plan etapes |

## Decisions

1. **Package separe `renatus.gui`** plutot que sous-module de `api` :
   garde F0009 intact ; reutilise `RenatusService` en composition.
2. **YamlStepStore** : index step -> fichier YAML ; save ne touche qu'une
   cle du dict fichier (round-trip PyYAML, commentaires non conserves).
3. **Reload apres save** : close + reopen `RenatusService` (ConnectionPipeline
   charge le pipeline au init uniquement).
4. **Build unifie** :
   - `table` / `view` / `dataframe` → `p_table_view` (+ rows)
   - `iteration` → `p_iteration` (pas de result set)
   - `execute` (et reste) → `process_with_requires`
5. **Graphe UI** : layout hierarchique par profondeur `requires` (JS pur),
   pas de lib force-directed.
6. **Edition config** : JSON dans le navigateur, YAML cote serveur.
7. **Extra `[gui]`** = alias de `[api]` (fastapi/uvicorn deja la).
8. **Serialisation** : verrou RLock local + lock du service API.

## Endpoints

```text
GET  /  et  /gui          # UI
POST /gui/connect
GET  /gui/graph
GET  /gui/step/{name}
PUT  /gui/step/{name}
POST /gui/build/{name}
GET  /gui/result/{name}
GET  /gui/static/*
GET  /health
```

## Validation

```text
pytest tests/test_f0010_gui.py -q   # 22 passed
pytest tests/test_f0009_api.py -q      # non-regression
pytest tests/ -q                       # 126 passed
```

## Commits / push

Branche : `F0010` → `origin/F0010` (tracking OK)

| hash | message |
|------|---------|
| `a15334d` | F0010: tests GUI web (testeur) |
| `3b0f2b7` | F0010: Renatus GUI GUI (package + static + entrypoint) |

Tip : `3b0f2b7` = `origin/F0010`. Push sans force. Pas de merge develop/main.

## Non fait (volontaire / hors scope)

- Auth / multi-utilisateur
- Editeur YAML monaco / CodeMirror
- Drag-and-drop creation de steps
- Merge develop/main (gestionnaire)
