# Plan de resolution — F0009

## Identite

| champ | valeur |
|-------|--------|
| id | F0009 |
| titre | api renatus |
| branche | F0009 |
| status | en_cours |
| base main | 9b81ca1 |

## Objectif

API HTTP (JSON) exposant le moteur pipeline : demarrage analogue CLI
(db duckdb + dossier pipelines), endpoints pour p_table_view, table_view,
process / process_with_requires, p_iteration, liste des etapes, existence relations.

## Spec fonctionnelle

1. **Demarrage** : `renatus-api <db.duckdb> <pipelines_dir>` (ou equivalent uvicorn/FastAPI)
2. **Endpoints JSON** (proposer REST coherent, documenter dans notes) :
   - liste des etapes pipeline
   - existence relation (table/view)
   - `p_table_view` (lineage)
   - `table_view` (sans lineage)
   - `process` / `process_with_requires`
   - `p_iteration`
3. **Package** : `src/renatus/api/` 100% POO
4. **Deps** : FastAPI (+ uvicorn si serveur) dans pyproject
5. **Tests** : TestClient + tmp_path, `tests/test_f0009_api.py`
6. **Contraintes** : TDD, push reguliers branche F0009, pas de merge develop/main par dev/test

## Etapes

- [x] 1. Lire regles + F0008 CLI (reutiliser patterns) + feature
- [x] 2. Check git branche F0009 base main
- [x] 3. Dev : package renatus.api + entrypoint
- [x] 4. Test : tests unitaires API (testeur parallele ; 22 green)
- [x] 5. Commit + push `F0009: ...`
- [x] 6. notes_dev_F0009.md / notes_test_F0009.md
- [ ] 7. Revue gestionnaire + merge FF

## Decisions

| date | decision | motif |
|------|----------|-------|
| 2026-08-07 | FastAPI + POO renatus.api | plan feature |

## Risques

- Conflits git dev/test : dev -> src/, test -> tests/
- Dependance FastAPI a ajouter (optional ou principal)

## Temps

| role | minutes |
|------|---------|
| developpeur | |
| testeur | |

## Reprise

1. plan + session + etat.json
2. git status F0009
3. premiere etape non cochee
