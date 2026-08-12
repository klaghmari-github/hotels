# Notes testeur — F0010 (GUI renatus)

Date: 2026-08-07  
Role: agent TESTEUR  
Branche: **F0010** (base main `4ab50fe` / F0009)  
Commits testeur: `a15334d` (tests) — `8be25c6` (notes GO) ; livrable gui dev `3b0f2b7`  
Temps passe: **~25 minutes** (contrat + tests en parallele du dev, alignement, pytest, notes)

## Perimetre

Tests unitaires / integration legers du GUI web renatus (spec feature F0010) :

1. GET `/` et `/gui` → HTML gui
2. POST `/gui/connect` avec chemins tmp (reconnect)
3. GET `/gui/graph` : nodes + edges `from`/`to` coherents avec `requires`
4. GET/PUT `/gui/step/{name}` : config editable, persistance YAML (relecture fichier)
5. POST `/gui/build/{name}` : rows pour table/vue ; execute → process_with_requires
6. GET `/gui/result/{name}` apres build (404 sans materialisation)
7. Erreurs 404/400 JSON
8. Static assets `/gui/static/*` (css/js/html) 200
9. Isolation stricte hors base hotels (`data/duckdb`)
10. Regression F0009 API (`create_app` + p_table_view)
11. Package exports + CLI parser `renatus-gui`

Aucun merge. `features.csv` / `anomalies.csv` non modifies par le testeur.  
Zone `src/renatus/gui/` laissee au developpeur (tests consomment le livrable parallele).

## Livrable tests

| Fichier | Contenu |
|---------|---------|
| `tests/test_f0010_gui.py` | **23 tests** — service store + HTTP TestClient + parser/entrypoint + isolation + reg. F0009 |
| `gestion_projet/notes_test_F0010.md` | Ce fichier |

Fixture mini : `proj_gui/pipelines/gui.yaml` + `input/people.csv`  
(dataframe, table, view, execute).

## Checklist spec

| # | Item | Statut | Detail |
|---|------|--------|--------|
| 1 | GET / ou /gui HTML | **OK** | index.html Renatus GUI |
| 2 | POST connect chemins tmp | **OK** | `/gui/connect` body `db_path` + `pipeline_path` |
| 3 | GET graph nodes/edges | **OK** | edges `(t_sales→v_sales)`, `(df_people→t_people)` |
| 4 | GET/PUT step + YAML disque | **OK** | SQL modifie, autres steps preservees |
| 5 | POST build rows | **OK** | v_sales `[[1,a],[2,b]]` ; t_people CSV |
| 6 | result apres build | **OK** | 200 apres build ; 404 sans build |
| 7 | Erreurs 400/404 | **OK** | step/build/result inconnus ; type invalide PUT |
| 8 | Static css/js | **OK** | `/gui/static/style.css`, `app.js`, `index.html` |
| 9 | Isolation tmp_path | **OK** | hors `data/duckdb` |
| 10 | Regression F0009 | **OK** | API classique toujours verte |
| 11 | Suite complete | **OK** | **127 passed** (104 + 23) |
| 12 | Entrypoint + package-data | **OK** | `renatus-gui` + `static/*` (livrable dev) |

## Execution

```text
pytest tests/test_f0010_gui.py -q
# 23 passed

pytest tests/ -q
# 127 passed, 1 warning (Starlette TestClient/httpx2)
```

Deps : extra `[api]` (fastapi, uvicorn) ; `httpx` pour TestClient.

## Contrat HTTP fige (tests)

```text
GET  / | /gui | /gui/
POST /gui/connect          {db_path, pipeline_path, read_only?}
GET  /gui/graph            {ok, nodes[{id,type,mode,file_origin}], edges[{from,to}]}
GET  /gui/step/{name}      {ok, name, config, file_origin}
PUT  /gui/step/{name}      {config: {...}}
POST /gui/build/{name}     p_table_view | process_with_requires | p_iteration
GET  /gui/result/{name}    table_view sans lineage
GET  /health
GET  /gui/static/...
```

Factory : `renatus.gui.create_gui_app(db_path, pipeline_path)`.

## Observations

1. **Architecture** (dev) : `GuiService` + `YamlStepStore` + routes `/gui/*` + static UI — reutilise `RenatusService` F0009.
2. **Edges graphe** : convention `from` = dependance, `to` = etape dependante (requires).
3. **PUT step** : peut **creer** une step absente (save_step + reload) — accepte 200 creation.
4. **build execute** : action `process_with_requires`, `has_result=false` (pas d'erreur 400).
5. **Warning** non bloquant : Starlette TestClient / httpx → httpx2.

## Reserves

| Severite | Reserve | Impact merge |
|----------|---------|--------------|
| basse | Warning TestClient/httpx2 | non bloquant |
| info | Connect invalid pipeline → code 4xx/500 selon stack | tests acceptent plage large |
| info | Editable install : entrypoint metadata peut etre stallee ; test lit aussi pyproject | non bloquant |

Les reserves entrypoint/package-data initiales sont **levees** par le livrable dev
(`renatus-gui` script + `package-data` static/* + README GUI).

## Verdict

**GO merge** — feature GUI complete cote tests, **23 tests verts**, **pas de regression** suite (127 passed), isolation respectee, contrat aligne notes_dev.

**Pour le gestionnaire :**
- merge FF `F0010` → `develop` puis `main` quand le package `src/renatus/gui/` + pyproject sont pousses par le dev
- renseigner `features.csv` temps (test ~25 min ; dev ~45 min)
- ne pas re-spawner testeur tant que F0010 `en_cours` / a merger

## Non fait (hors scope testeur)

- Merge develop/main
- Modification status `features.csv`
- Implementation production (`src/renatus/gui/` = zone dev)
- Force push
