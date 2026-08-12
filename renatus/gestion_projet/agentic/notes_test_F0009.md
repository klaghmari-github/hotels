# Notes testeur — F0009 (API renatus)

Date: 2026-08-07  
Role: agent TESTEUR  
Branche: **F0009** (base main `9b81ca1`)  
Commits testeur: `4034ce5` (notes) — validation suite sur livrable API `2d758db` / tests `c6011a1`  
Temps passe: **~40 minutes** (plan, code API en evolution, tests, pytest, notes)

## Perimetre

Tests unitaires / integration legers de l'API HTTP renatus (spec plan F0009) :

1. Creation app / client (`create_app` + TestClient) db + YAML+CSV sous `tmp_path`
2. Liste des etapes pipeline (`GET /pipeline/steps`)
3. Existence relation (`GET /relations/{name}/exists`)
4. `p_table_view` lineage → JSON columns/rows (+ GET equivalent, max_rows)
5. `table_view` sans lineage (404 si absent, OK apres materialisation)
6. `process` / `process_with_requires` (effets de bord)
7. `p_iteration` sequential (fixture mini)
8. Erreurs 404/400 JSON clairs (+ validation max_rows)
9. Isolation stricte hors base hotels (`data/duckdb`)
10. Exports package, parser CLI `renatus-api`, entrypoint pyproject

Aucun merge. `features.csv` status non modifie. Code production non touche par le testeur.

## Livrable tests

| Fichier | Contenu |
|---------|---------|
| `tests/test_f0009_api.py` | **30 tests** — runtime/service + HTTP TestClient + CLI parser/exports |
| `gestion_projet/notes_test_F0009.md` | Ce fichier |

Fixture mini : `proj_api/pipelines/api.yaml` + `input/people.csv` (dataframe, table, view, execute, iteration).

## Checklist spec

| # | Item | Statut | Detail |
|---|------|--------|--------|
| 1 | App + client tmp db/pipelines | **OK** | `create_app` / `create_app_from_paths` + TestClient |
| 2 | Liste etapes GET | **OK** | `/pipeline/steps` : t_sales, v_sales, x_drop_rows, i_run… |
| 3 | Existence relation | **OK** | false avant, true apres `p_table_view` |
| 4 | p_table_view JSON | **OK** | columns/rows v_sales ; CSV t_people ; GET=POST ; max_rows |
| 5 | table_view sans lineage | **OK** | 404 si absent (ne materialise pas) ; 200 apres |
| 6 | process / process_with_requires | **OK** | actions OK + side effects |
| 7 | p_iteration | **OK** | i_run → t_results [1,2,3] |
| 8 | Erreurs 404/400 | **OK** | no_such_step 404 ; type execute 400 ; max_rows invalide |
| 9 | Isolation tmp_path | **OK** | chemins sous tmp, hors data/duckdb |
| 10 | Suite complete | **OK** | **104 passed** |

## Execution

```text
pytest tests/test_f0009_api.py -q
# 30 passed

pytest tests/ -q
# 104 passed
```

Deps : extra `[api]` (fastapi, uvicorn) ; `httpx` requis pour TestClient (installe en venv).

## Observations

1. **Architecture** (dev) : `RenatusApiRuntime` / service + routes FastAPI + `renatus-api` — testable, lifespan correct.
2. **Contrat HTTP fige** dans les tests :
   - `GET /health`, `GET /pipeline/steps`, `GET /relations/{name}/exists`
   - `POST|GET /p_table_view/{name}?max_rows=`
   - `GET /table_view/{name}`, `POST /process|process_with_requires|p_iteration/{name}`
3. **create_or_replace + p_table_view** : re-materialise t_sales (comportement moteur documente) ; effets DELETE verifies en service via SQL brut dans certains cas.
4. **Warning** non bloquant : Starlette TestClient / httpx → httpx2.

## Reserves

| Severite | Reserve | Impact merge |
|----------|---------|--------------|
| basse | `httpx` non toujours declare dans pyproject pour TestClient | non bloquant si venv dev complete |
| basse | Warning TestClient/httpx2 | non bloquant |
| info | Pendant le dev, routes ont oscille (`/pipeline` vs `/pipeline/steps`) — version finale = celle des tests | OK |

## Verdict

**GO merge** — feature API complete, 30 tests verts, isolation respectee, pas de regression suite (104 passed).

**Pour le gestionnaire :**
- merge FF `F0009` → `develop` puis `main` quand pret
- renseigner `features.csv` temps (dev ~45 min / test ~40 min)
- optionnel : ajouter `httpx` dans extra `dev` ou `api`

## Non fait (hors scope testeur)

- Merge develop/main
- Modification status `features.csv`
- Auth / multi-worker uvicorn
