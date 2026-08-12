# Notes dev F0009 — API HTTP renatus

Date: 2026-08-07  
Role: agent DEVELOPPEUR  
Branche: F0009 (base main `9b81ca1`)  
Temps passe: **~55 minutes** (implementation + alignement contrats tests + validation)

## Perimetre

- API HTTP JSON exposant le moteur (apres CLI F0008)
- FastAPI + uvicorn en extra `[api]`
- Pas de modification `engine.py` / CLI F0008
- Pas de merge develop/main, pas de force push
- Pas de modification `features.csv` / `anomalies.csv` (gestionnaire)
- Pas de bases hotels reelles (tmp_path uniquement)
- Zone `tests/` laissee au testeur (fichier present en parallele)

## Livrables

| Fichier | Action |
|---------|--------|
| `src/renatus/api/__init__.py` | Exports publics |
| `src/renatus/api/__main__.py` | `python -m renatus.api` |
| `src/renatus/api/schemas.py` | Dataclasses reponse JSON |
| `src/renatus/api/service.py` | `RenatusService` + `RenatusApiRuntime` + Lock |
| `src/renatus/api/app.py` | Fabrique FastAPI, routes (double contrat) |
| `src/renatus/api/server.py` | CLI `renatus-api` / uvicorn |
| `pyproject.toml` | extra `[api]`, script `renatus-api` |
| `README.md` | Section API (install + curl) |
| `gestion_projet/notes_dev_F0009.md` | Ce fichier |
| `gestion_projet/agentic/plan_F0009.md` | Etapes dev cochees |

## Decisions

1. **Architecture POO** : `RenatusService` (metier) + `RenatusApiRuntime`
   (cycle de vie) + `create_app` (routes minces) + schemas dataclasses.
2. **`PipelineApiService = RenatusService`** : un seul moteur metier,
   deux noms d'export pour les imports tests.
3. **Extra `[api]`** plutot que deps principales : fastapi/uvicorn optionnels ;
   `dev` reutilise `renatus[api]`.
4. **Thread Lock** dans le service : connexion DuckDB non multi-thread.
5. **Lifespan** FastAPI pour open/close (pas `on_event` deprecie).
6. **Erreurs** : KeyError/LookupError → 404, ValueError/TypeError → 400 ;
   corps `{"ok": false, "error": "...", "detail": "..."}`.
7. **Double contrat routes** (stabilite tests paralleles) :
   - `/pipeline` et `/pipeline/steps`
   - `/relations/{name}` et `/relations/{name}/exists`
   - query `limit` et `max_rows`
   - health expose `pipeline_path` **et** `pipelines_dir`
8. **Reutilisation moteur** : uniquement `ConnectionPipeline`, pas de
   reimplementation du lineage.
9. **workers uvicorn = 1 process** documente (connexion unique).

## Endpoints

```text
GET  /health
GET  /pipeline
GET  /pipeline/steps          # alias
GET  /pipeline/{name}
GET  /relations/{name}
GET  /relations/{name}/exists # alias
POST /p_table_view/{name}?limit=&max_rows=
GET  /p_table_view/{name}
GET  /table_view/{name}?limit=&max_rows=
POST /process/{name}
POST /process_with_requires/{name}
POST /p_iteration/{name}
```

## Validation

```text
pytest tests/test_f0009_api.py -q   # 30 passed (contrat live testeur)
pytest tests/ -q                    # suite complete + regression
```

## Commits / push

Branche : `F0009` → `origin/F0009` (tracking OK)

| hash | message |
|------|---------|
| `c6011a1` | F0009: API HTTP FastAPI (renatus.api) + tests TestClient |
| `5b7ba93` | F0009: notes_dev hash commit et push origin/F0009 |
| `2d758db` | F0009: API HTTP FastAPI renatus (package renatus.api) |
| `4034ce5` | F0009: tests API HTTP complets (TestClient, service, isolation) |

Tip : `4034ce5` = `origin/F0009`. Push sans force. Pas de merge develop/main.

## Non fait (volontaire / hors scope)

- Auth / multi-tenant
- OpenAPI custom poussee
- Refactor CommandRunner pour partager 100% du code CLI
- Merge develop/main (gestionnaire)
- Status features.csv (gestionnaire)
