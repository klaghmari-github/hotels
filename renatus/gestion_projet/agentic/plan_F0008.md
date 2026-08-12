# Plan de resolution — F0008

## Identite

| champ | valeur |
|-------|--------|
| id | F0008 |
| titre | cli renatus |
| branche | F0008 |
| status | en_cours |
| base main | a21fdc3 |

## Objectif

Fournir une CLI renatus (oneshot + REPL) : connexion DuckDB, chargement YAML pipelines,
execution de commandes `p_table_view`, etapes `process` (ex. `x_drop_rows`), et
`table_view` sans lineage.

## Spec fonctionnelle

1. **Oneshot** : `python renatus.py <db.duckdb> <pipelines_dir> <cmd> [args...]`
   - Exemple : `python renatus.py main.duckdb pipelines p_table_view v_sales`
   - Connecte la base, charge tous les YAML du dossier, execute la commande, affiche resultat, exit.
2. **REPL** : `python renatus.py <db.duckdb> <pipelines_dir>`
   - Console interactive : lignes du type `p_table_view v_sales`, `x_drop_rows`, `table_view v_achats`.
3. **Commandes**
   - `p_table_view <name>` : lineage + materialisation via `ConnectionPipeline.p_table_view`, affiche apercu.
   - `<name>` simple (ex. `x_drop_rows`) : si present dans le pipeline YAML, `process_with_requires(name)` (etape execute/table/view/iteration).
   - `table_view <name>` : sans lineage (`ConnectionUtils.table_view`) ; erreur claire si relation absente.
4. **Livrables**
   - `src/renatus/cli.py` (ou package `renatus.cli`)
   - `renatus.py` a la racine (script mince)
   - entrypoint optionnel dans `pyproject.toml` (`renatus = renatus.cli:main`)
   - tests `tests/test_f0008_cli.py` sur tmp_path
5. **Contraintes** : 100% POO, TDD, pas de merge develop/main par dev/test, push reguliers branche F0008, notes temps.

## Etapes

- [x] 1. Lire regles + feature + etat agentic
- [x] 2. Check git (branche F0008 base main)
- [x] 3. Dev : module CLI oneshot + REPL
- [x] 4. Test : tests unitaires CLI tmp_path (27 tests, suite 74 OK)
- [x] 5. Commit + push `F0008: ...`
- [x] 6. notes_dev_F0008.md / notes_test_F0008.md
- [ ] 7. Revue gestionnaire + merge FF

## Decisions

| date | decision | motif |
|------|----------|-------|
| 2026-08-07 | module renatus.cli + renatus.py racine | plan feature + usage documente |
| 2026-08-07 | 3 classes POO (ResultPrinter, CommandRunner, RenatusCli) | separation affichage / commandes / orchestration |
| 2026-08-07 | pytest pythonpath=src + bootstrap lanceur | eviter shadow renatus.py vs package |

## Risques / blocages

- Conflits git si dev et test touchent les memes fichiers (coordonner : test ecrit tests/, dev ecrit src/ + renatus.py)
- Shadow name : renatus.py racine vs package src/renatus (mitige)

## Temps

| role | minutes |
|------|---------|
| developpeur | 35 |
| testeur | 25 |

## Reprise apres arret

1. Lire ce plan + session.md + etat.json
2. git status / branche F0008
3. Reprendre premiere etape non cochee
