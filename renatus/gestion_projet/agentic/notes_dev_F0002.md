# Notes dev F0002 — tests unitaires fonctionnels pipeline

Date: 2026-08-07  
Role: agent DEVELOPPEUR support  
Branche: F0002  
Temps passe: **~15 minutes** (lecture engine, smoke manuel des cas F0002, fixtures CSV, surveillance tests testeur, pytest F0001+F0002)

## Perimetre

Support developpeur pour la feature F0002 (tests unitaires ecrits en parallele par le testeur).  
Pas de refactor massif. Pas de changement d API publique. Pas de commit / push / merge.  
Pas de modification de `features.csv` / `anomalies.csv`.

## Analyse moteur (src/renatus/pipeline/engine.py)

Points cles verifies avant / avec les tests:

| Methode | Role |
|---------|------|
| `validate_pipeline` | types autorises: dataframe, table, view, execute, iteration; requires doivent exister dans le dict YAML |
| `df_from_file` | CSV/TSV/JSON/parquet/excel; chemins relatifs resolus via `project_dir` (parent du dossier pipeline) |
| `create_relation` | TABLE/VIEW, modes `create_if_not_exists` et `create_or_replace` |
| `process` | dispatch par type (register dataframe, create table/view, execute SQL, process_iteration) |
| `process_with_requires` | creation recursive des requires puis process |
| `process_iteration` / sequential | lit scenarios, `replace_step_view` (TEMP VIEW), process target a chaque ligne |
| `p_table_view` / `p_iteration` | entrees haut niveau; refuse execute/iteration pour p_table_view |

Comportements utiles pour les tests (pas des bugs):

1. Dossier pipeline sans aucun YAML -> `FileNotFoundError` (deja note F0001).
2. `step_view` d iteration est cree dynamiquement: ne doit pas etre dans `requires` (sinon validation echoue car absent du pipeline).
3. Modes create: `create_if_not_exists` skip si relation presente; `create_or_replace` rebuild a chaque process.

## Smoke manuel (avant tests testeur)

Scenario minimal tmp_path + fixtures CSV: dataframe->table, chaine requires, execute INSERT, iteration sequential 3 scenarios, `df_from_file`, `create_relation`, validate_pipeline (type invalide + dep manquante).  
**Resultat: 10/10 OK** — aucun correctif production necessaire a ce stade.

## Fixtures livrees (helpers pour tests)

Dossier `tests/fixtures/f0002/` (CSV minimaux, pas de tests ecrits par le dev):

| Fichier | Contenu |
|---------|---------|
| `products.csv` | 4 produits (product_id, name, category, price) |
| `sales.csv` | 5 ventes (sale_id, hotel_code, product_id, quantity, amount) |
| `scenarios.csv` | 3 scenarios (scenario_id, hotel_code, label) |
| `hotels.csv` | 3 hotels (hotel_code, name, city) |

Note: le testeur a finalement genere ses propres CSV inline dans `tmp_path` (approche isolee correcte). Les fixtures restent disponibles pour extensions futures.

## Correctifs production

**Aucun.** Le code F0001 suffit pour tous les cas F0002 cibles.

## Resultats pytest

Commande:

```text
.venv/bin/python -m pytest tests/test_f0001_init.py tests/test_f0002_pipeline_features.py -v --tb=short
```

| Suite | Resultat |
|-------|----------|
| F0001 (6 smoke) | 6 passed |
| F0002 (7 fonctionnels) | 7 passed |
| **Total** | **13 passed** (~0.8s) |

Tests F0002 (ecrits par le testeur, fichier `tests/test_f0002_pipeline_features.py`):

1. `test_dataframe_from_csv_then_table_select` — dataframe CSV + table SELECT
2. `test_table_view_chain_t_a_v_b_t_c` — chaine table -> vue -> table
3. `test_p_table_view_creates_missing_ancestors` — requires non crees, creation recursive
4. `test_execute_sql_side_effect_no_relation` — execute INSERT, pas de relation nommee
5. `test_iteration_sequential_one_row_per_scenario` — iteration sequential, 1 ligne / scenario
6. `test_create_if_not_exists_skips_when_present` — pas d ecrasement
7. `test_create_or_replace_rebuilds_table` — recreation a chaque process

## Decisions

1. **Pas de patch engine** : smoke + suite testeur verts; hors scope de changer l API ou l architecture (F0006).
2. **Fixtures CSV conservees** meme si non utilisees par le testeur actuel: utiles pour TDD ulterieur (fichiers reels partages).
3. **Iteration parallele** non couverte ici (ParallelIterationManager) — hors perimetre minimal F0002 sequential; a traiter si feature ulterieure.
4. **CSV gestion** non modifies (consigne).

## Anomalies

Aucune (Axxxx non cree).

## Fin de mission dev F0002

- Code production inchange et conforme aux tests F0001 + F0002.
- Fixtures `tests/fixtures/f0002/*.csv` en place.
- Documentation dans ce fichier.
- Commit / merge / status features.csv: **gestionnaire**.
