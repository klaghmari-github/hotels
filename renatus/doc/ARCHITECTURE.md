# Architecture renatus

Document de reference architecture (F0006).  
Decrit l etat actuel du code et la cible d organisation pour la suite.  
Pas de refactor massif dans cette feature : documenter, decider, guider.

---

## 1. Objectif du projet

**renatus** est un **moteur de pipeline data lineage** :

- On declare des etapes (tables, vues, dataframes, executions SQL, iterations) en YAML.
- Chaque etape declare ses dependances (`requires`).
- A la demande d une relation (ou d une iteration), le moteur cree recursivement les ancetres manquants.
- Une seule connexion base de travail sert le graphe (aujourd hui DuckDB).

Le package Python public s appelle **`renatus`** (layout `src/`).  
Destination PyPI : uniquement lors d un **tag de release** explicite.  
En developpement : installation editable locale (`pip install -e ".[dev]"`).

Le projet hotels (simulations, ML, LOO) est un **consommateur** du moteur, pas le coeur du package.  
Les YAML metier et le perimetre hotels ne doivent pas vivre dans le package core.

---

## 2. Couches (schema ASCII)

```
+------------------------------------------------------------------+
|  gestion_projet/   (process agents, features, anomalies)         |
|  doc/              (ARCHITECTURE, docs humaines)                 |
+------------------------------------------------------------------+
|  APPLICATION / DOMAINE (hors package core a terme)               |
|    pipeline/*.yaml   -- definitions metier (hotels, sim, ml)     |
|    data/files/input  -- fichiers source                          |
|    data/files/output -- exports                                  |
|    models/           -- artefacts ML                             |
|    scope hotels      -- codes exclus / pilotes (aujourd hui      |
|                        dans renatus.pipeline.scope)              |
+------------------------------------------------------------------+
|  PACKAGE renatus (src/renatus/)  -- coeur reutilisable           |
|    +------------------------------------------------------------+|
|    | facade API                                                  ||
|    |   renatus.__init__  -> reexport pipeline                    ||
|    +------------------------------------------------------------+|
|    | renatus.pipeline                                            ||
|    |   Paths / find_project_root     -- chemins racine config.   ||
|    |   PipelineFactory               -- ouverture connexion      ||
|    |   ConnectionPipeline            -- moteur YAML + process    ||
|    |   steps/ (F0053/F0054)          -- Step ABC + build hooks   ||
|    |   schema_helpers                -- helpers schema relation  ||
|    |   DependencyTree                -- frontieres stables       ||
|    |   ParallelIterationManager      -- buckets / workers        ||
|    |   ConnectionUtils               -- primitives DuckDB        ||
|    +------------------------------------------------------------+|
|    | renatus.gui.services (F0054) GraphOps + facade           ||
|    | renatus.gui.static.app/      ConfigPanel + controllers   ||
|    +------------------------------------------------------------+|
+------------------------------------------------------------------+
|  RUNTIME EXTERNE                                                 |
|    DuckDB (fichier main + workers)  |  pandas  |  PyYAML         |
+------------------------------------------------------------------+
```

Flux d usage typique :

```
Paths(root=...)  ->  PipelineFactory.open()  ->  ConnectionPipeline
                                                      |
                              load_pipeline (YAML merges)
                                                      |
                         p_table_view(name) / p_iteration(name)
                                                      |
                              process_with_requires (DFS + modes)
                                                      |
                         DuckDB : CREATE TABLE/VIEW | register DF
```

---

## 3. Organisation packages et classes actuelles

### 3.1 Arborescence package

```
src/renatus/
  __init__.py              # version + reexport API publique
  pipeline/
    __init__.py            # exports publics du moteur
    paths.py               # Paths, find_project_root, release_root
    connection.py          # PipelineFactory
    connection_utils.py    # ConnectionUtils (F0053-S7)
    dependency.py          # DependencyTree via Step.is_stable_frontier
    engine.py              # ConnectionPipeline + reexports
    schema_helpers.py      # F0054: schema relation helpers
    iteration_parallel.py  # ParallelIterationManager
    steps/                 # F0053/F0054: Step ABC + build_action
      base.py relation.py sql_action.py control.py org.py factory.py
    scope.py               # domaine hotels (a sortir du core)
  gui/
    yaml_store.py          # YamlStepStore (F0053-S5)
    services/              # F0054: GraphOps (facade GuiService)
    static/app/
      config/              # F0054: ConfigPanel + form/yaml/pencil/requires
      step-types/ gui-app.js graph.js tabs.js ...
    static/app/            # ES modules + classes GUI (F0053)
      main.js gui-app.js step-types/ ui-base.js ...
```

### 3.2 Role de chaque module

| Module / classe | Role |
|-----------------|------|
| **`Paths`** | Chemins generiques optionnels (`data/`, `pipeline/`, `models/`). **Pas** de sous-dossiers hotels (sim_v1, etc.). `ensure()` ne cree plus d arborescence vide ; `ensure_db_parent()` cree le parent de la base. |
| **`find_project_root` / `release_root`** | Detection de la racine (dossier avec `pipeline/` ou `src/renatus/`) ou root force. |
| **`PipelineFactory`** | Fabrique : ouvre `ConnectionPipeline` sur `main.duckdb`, option `rebuild`, fallback `main_work.duckdb` si lock concurrent. |
| **`ConnectionUtils`** | Couche basse DuckDB : connect, `table_exists` / `view_exists`, `create_relation` (modes), `table_view`. |
| **`ConnectionPipeline`** | Coeur : charge et valide les YAML, resout les chemins projet, dispatch `process` par type, `process_with_requires`, `p_table_view`, `p_iteration`, iteration sequentielle (`replace_step_view`). |
| **`DependencyTree`** | Calcule la frontiere stable (`stable_frontier`) pour les seeds workers : s arrete sur les tables/vues en `create_if_not_exists` (frontieres reutilisables). |
| **`ParallelIterationManager`** | Parallelise une iteration : buckets de scenarios, bases worker, seed, `ProcessPoolExecutor`, merge des resultats vers la base partagee. |
| **`ParallelismConfig` / `resolve_parallelism`** | Calcul workers / buckets (tasks auto ou N, reserved_cpus, threads DuckDB par worker). |
| **Helpers engine** | Schema (`relation_schema`, `ensure_table_schema`, ...), seed (`register_dataframe_as_relation`), fingerprints pipeline/source, metadata worker, `run_iteration_bucket`. |
| **`scope`** | Constantes et helpers SQL hotels (exclus, pilotes). **Domaine metier**, pas generique. |

### 3.3 Couplages metier encore presents dans le coeur (dette connue)

Ces points sont dans `engine.py` et dependent du modele hotels / simulation assortiment. Ils ne bloquent pas l usage generique de base (table/view/dataframe/execute/iteration sequentielle), mais freinent un package purement reutilisable :

- `source_fingerprint` : lit `t_sales` (colonnes QUANTITE, DATE, HOTEL_CODE, NATURE_PRODUIT).
- `ParallelIterationManager.merge_result_dataframe` : cles `scenario_id` + `hotel_code`.
- `run_iteration_bucket` / resultats par defaut : `t_dataset_pivot`, `t_scenarios`.
- `refresh_scenarios` : schema scenarios assortiment (`scenario_removed_natures_json`).

**Cible** : isoler ces parties dans une couche domaine (ou config d iteration plus generique), sans les laisser comme prerequis implicites du core.

---

## 4. Types d etapes YAML et modes

### 4.1 Types autorises (`validate_pipeline`)

| Type | Effet |
|------|--------|
| **`dataframe`** | Charge un fichier (CSV, TSV, JSON, parquet, Excel) via pandas, `register` sous le nom de l etape. |
| **`table`** | `CREATE TABLE ... AS (sql)` selon le mode. |
| **`view`** | `CREATE VIEW ... AS (sql)` selon le mode. |
| **`execute`** | Execute du SQL (effets de bord : INSERT, UPDATE, ...) sans creer de relation nommee. Toujours traite. |
| **`iteration`** | Pour chaque ligne de `scenarios`, cree une TEMP VIEW `step_view`, puis `process_with_requires(target)`. Sequential par defaut ; parallel via `ParallelIterationManager`. |

### 4.2 Modes de creation (table / view)

| Mode | Comportement |
|------|----------------|
| **`create_if_not_exists`** (defaut) | Ne recree pas si la relation existe deja (`should_process` = false). |
| **`create_or_replace`** | Recree a chaque process. |

`dataframe` : traite seulement si la relation n existe pas encore (pas de mode YAML standard).  
`execute` / `iteration` : toujours traites.

### 4.3 Convention de nommage usuelle (hors validation)

- `t_` : table  
- `v_` : vue  
- `x_` : execute  
- `df_` : dataframe source  
Nommage libre cote moteur ; convention projet pour lisibilite.

### 4.4 Champs YAML usuels

Communs : `type`, `mode`, `requires`, `sql` ou `file`.

Iteration (extrait) :

- `scenarios` : nom de la relation des scenarios  
- `step_view` : nom de la TEMP VIEW par ligne (ne pas la mettre dans `requires` : elle n est pas une etape YAML)  
- `target` : objet a materialiser par scenario  
- `order_by` : colonnes d ordre  
- `execution` : `sequential` | `parallel`  
- parallel : `tasks`, `reserved_cpus`, `max_workers`, `duckdb_threads_per_worker`, `worker_database_pattern`, `result_table` / `completed_table`

### 4.5 Organisation dossier `pipeline/`

- Hors package Python : vit a la racine projet.
- `ConnectionPipeline` fusionne tous les `*.yaml` / `*.yml` (recursif sous le dossier pipeline).
- Doublon de nom d objet entre fichiers = erreur.
- **Aujourd hui** : dossier vide (`.gitkeep`) ; les YAML metier hotels ne sont pas dans le depot renatus core.
- **Cible organisation** (quand le metier revient) :

```
pipeline/
  common/          # etapes partagees
  sim_v1/
  sim_v2/
  ml/
```

Chemins deja prevus dans `Paths` (`pipeline_common`, `pipeline_sim_v1`, ...).  
Le moteur charge tout le dossier `pipeline/` d un coup (pas de filtrage par sous-dossier au runtime actuel).

**Regle** : aucun YAML metier hotels dans le wheel / package `src/renatus`.

---

## 5. Donnees runtime (hors depot renatus)

`data/` n'est **pas** versionne dans renatus (A0002). Un projet consommateur
peut creer localement :

```
data/
  files/input/
  files/output/
  duckdb/main/
  duckdb/workers/
```

Les sous-dossiers hotels historiques (`sim_v1`, `sim_v2`, `ml`) n'appartiennent
pas au coeur renatus.

## 5b. (historique) Donnees hotels — NE PAS RECREER DANS RENATUS


```
data/
  files/
    input/           # CSV et autres entrees
    output/
      common/
      ml/
      sim_v1/
      sim_v2/
  duckdb/
    main/            # main.duckdb (+ eventuel main_work.duckdb si lock)
    workers/         # bases par bucket d iteration parallele
```

- Production / dev local : bases reelles sous `data/duckdb/` (souvent gitignorees).
- Tests : **toujours** `tmp_path` / fixtures ; jamais la base hotels de travail.

---

## 6. Tests : `tests/`

```
tests/
  conftest.py                      # fixtures Paths, YAML minimal, db temp
  test_f0001_init.py               # smoke package / Paths / pipeline minimal
  test_f0002_pipeline_features.py  # dataframe, chaine, requires, execute,
                                   # iteration sequential, modes create
  fixtures/
    f0002/                         # CSV minimaux partageables (hotels, sales, ...)
```

Principes (regles projet + pratique actuelle) :

- TDD : developpeur + testeur en parallele.
- Tests unitaires sur bases et fichiers de test, quantites petites.
- Isolation stricte : pas d I/O sur `data/duckdb/main` de prod.
- Fixtures pytest pour root temporaire ; YAML generes dans `tmp_path` pour la plupart des cas F0002.
- Organisation future possible : `tests/unit/`, `tests/integration/`, fixtures par feature `tests/fixtures/f00xx/`.

---

## 7. Gestion projet : `gestion_projet/`

| Element | Role |
|---------|------|
| `features.csv` / `anomalies.csv` | Backlog et suivi (gestionnaire uniquement pour le statut). |
| `regles_de_gestion.md` | Invariants : 100 % POO, TDD, git FF, push reguliers. |
| `watchdog.py` | Ecoute le dossier, notifie le gestionnaire. |
| `locks/` | Locks merge develop / main. |
| `agentic/` | Donnees agents : etat, session, plans, notes_dev / notes_test. |
| `src/agentic/` | Code Python de gestion (package `agentic`, hors renatus). |
| `logs/` | Journaux optionnels de la gestion. |
| `tests/` | Tests unitaires de la gestion uniquement. |

Ce dossier n est **pas** du runtime package produit. Separation stricte :
`src/renatus/` = metier uniquement ; `gestion_projet/` = agents + suivi.

---

## 8. Packaging : `pyproject.toml`

| Point | Etat |
|-------|------|
| Name / version | `renatus` `0.1.0` |
| Layout | `src/` (setuptools `packages.find` where = `src`) |
| Python | `>=3.10` |
| Deps runtime | duckdb, pandas, numpy, pyyaml |
| Extra `excel` | openpyxl (lecture xlsx dans le moteur) |
| Extra `dev` | pytest |
| Install dev | `pip install -e ".[dev]"` |
| Release PyPI | uniquement sur **tag** de release (pas de publish a chaque feature) |

`requirements.txt` : miroir des deps principales pour install simple hors editable.

---

## 9. Decisions cible (suite)

Ces decisions guident les features suivantes. F0006 ne les implemente pas toutes.

### 9.1 Scope hotels hors package core

- `scope.py` (EXCLUDED / PILOT / helpers SQL) est domaine hotels.
- **Cible** : deplacer vers un package ou module domaine separe (ex. `renatus_hotels` ou `domain/hotels` hors wheel core), ou au minimum `renatus.domain.hotels` clairement separe de `renatus.pipeline`.
- Le coeur pipeline ne doit plus importer de constantes hotels.

### 9.2 Paths generique (deja en place)

- `Paths(root=...)` : root configurable ; detection auto via `pipeline/` ou `src/renatus/`.
- `data/` / `models/` : conventions **runtime consommateur**, non versionnees dans le depot renatus (A0002).
- Plus de chemins hotels `sim_v1` / `sim_v2` / models catboost dans le coeur.
- Evolution possible : Paths "minimal" (data, pipeline, duckdb) + extension domaine pour sim/ml/models.

### 9.3 Abstraction connexion (au-dela de DuckDB)

- Aujourd hui : DuckDB en dur dans `ConnectionUtils` / helpers.
- **Cible progressive** :
  1. Garder DuckDB comme implementation par defaut.
  2. Introduire une interface / protocole de connexion (exists, create_relation, execute, register dataframe).
  3. Brancher d autres backends seulement si besoin reel (pas de multi-backend premature).
- Les SQL generes (`CREATE TABLE IF NOT EXISTS ... AS`) restent dialecte DuckDB tant qu on n a pas d autre cible.

### 9.4 Pas de YAML metier dans le package core

- Les definitions d etapes vivent sous `pipeline/` a la racine du **projet consommateur**.
- Le package `renatus` fournit uniquement le moteur et l API Python.
- Les tests du core utilisent des YAML synthetiques dans `tmp_path` / fixtures, pas le graphe hotels complet.

### 9.5 Decoupage futur de `engine.py`

Fichier unique ~1900 lignes. Cible de lecture / maintenance (sans urgence bloquante) :

```
pipeline/
  paths.py
  connection.py          # PipelineFactory
  engine/
    connection_utils.py
    dependency.py
    pipeline.py          # ConnectionPipeline
    iteration.py         # sequential + parallel manager
    schema.py            # helpers schema
    workers.py           # fingerprints, run_bucket
  (domain hotels separe)
```

Regle : un module = un role ; lazy loading / properties la ou ca aide (regles projet).

### 9.6 API publique stable

Exporter depuis `renatus` / `renatus.pipeline` uniquement ce qui est stable :

- Usage courant : `Paths`, `PipelineFactory`, `ConnectionPipeline`, `DependencyTree`, `ParallelIterationManager`.
- Helpers bas niveau : exportes aujourd hui ; a documenter comme "advanced" ou a restreindre plus tard.

---

## 10. Git et cycle de feature (rappel architecture process)

```
main  --branch-->  Fxxxx  --merge FF-->  develop  --merge FF-->  main
                     ^
                     | push reguliers pendant le dev
```

- Une branche feature par id (ex. `F0006`).
- Pas de merge parallele sans lock.
- Le package n est publie sur PyPI que sur tag release, independamment des merges feature.

---

## 11. Resume pour les prochains agents

| Faire | Eviter |
|-------|--------|
| Etendre le moteur avec TDD + fixtures tmp | Coller du SQL hotels dans le package core |
| Garder YAML metier sous `pipeline/` projet | Publier PyPI a chaque feature |
| Sortir `scope` et fingerprints metier progressivement | Refactor massif sans tests verts |
| Documenter les decisions dans notes_dev | Modifier features.csv / anomalies.csv (gestionnaire) |
| Push reguliers sur la branche feature | Merger develop/main (gestionnaire) |

Ce document est la reference architecture a jour au moment de F0006
(mise a jour documentation UML : F0108).  
Toute decision structurelle majeure doit le mettre a jour.

---

## 12. Diagrammes UML (classes metiers)

Les diagrammes de classes **complets avec attributs** sont rendus dans :

**[documentation.html — UML Backend](documentation.html#uml-backend)**  
**[documentation.html — UML Frontend](documentation.html#uml-frontend)**

### Backend (Python) — packages

| Package | Classes metiers (attributs dans HTML) |
|---------|----------------------------------------|
| `pipeline.steps` | `Step`, `RelationStep`, `DataframeStep`, `TableStep`, `ViewStep`, `ControlStep`, `IterationStep`, `OrgStep`, `ZoneStep` (+ `objects`), `ExecuteStep`, `ExecutePythonStep`, `ExecuteShellStep`, `StepFactory` |
| `pipeline` | `Paths`, `PipelineFactory`, `ConnectionUtils`, `ConnectionPipeline`, `DependencyTree`, `ParallelismConfig`, `ParallelIterationManager`, `RenatusProject`, `ProjectGit`, `PendingBranch` |
| `api` | `RenatusService`, `RelationSerializer`, `RenatusApiRuntime`, `RenatusApiApp`, DTO `HealthResponse`, `PipelineStepInfo`, `RelationDataResponse`… |
| `gui` | `GuiService`, `YamlStepStore` (`ROOT_TAB`, `ALL_TAB`), `GraphOps`, `GuiApp` (FastAPI), schemas `GraphNode`/`GraphEdge`/… |
| `cli` | `RenatusCli`, `CommandRunner`, `CommandResult`, `ResultPrinter` |

### Frontend (JS ES modules) — classes

| Module | Classes |
|--------|---------|
| `gui-app.js` | `GuiApp` — composition state + controllers |
| `state.js` | `GuiState` — connected, selected, graph, tabs, layout… |
| `api.js` | `ApiClient` |
| `ui-base.js` | `UiController` |
| Controllers | `GraphCanvas`, `PipelineTabs`, `Toolbox`, `ConfigPanel`, `DataViewPanel`, `ChangelogPanel`, `ProjectDialogs` |
| `step-types/*` | `StepType` + `DataframeStepType`, `TableStepType`, `ViewStepType`, `Execute*`, `IterationStepType`, `ZoneStepType`, `StepTypeRegistry` |

### Relations majeures

```
YamlStepStore  <--store--  GuiService  --_api-->  RenatusService
                                |                      |
                             GraphOps           ConnectionPipeline
                                |                      |
                           /gui/graph              Step hierarchy
                                                       |
Frontend: GuiApp --> GraphCanvas / ConfigPanel / PipelineTabs
              \--> GuiState (selected, activeTab, graph…)
```
