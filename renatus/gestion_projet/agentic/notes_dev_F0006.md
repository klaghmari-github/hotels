# Notes dev F0006 — architecture projet renatus

Date: 2026-08-07  
Role: agent DEVELOPPEUR  
Branche: F0006  
Temps passe: **~35 minutes** (lecture code engine/connection/paths/scope, README, tests, pyproject ; redaction ARCHITECTURE.md ; notes ; commits/push)

## Perimetre

Feature de **reflexion architecture** uniquement :

- Produire `doc/ARCHITECTURE.md` actionnable.
- Pas de refactor massif du code.
- Pas de modification de `features.csv` / `anomalies.csv`.
- Pas de merge develop/main (gestionnaire).

## Livrables

| Fichier | Contenu |
|---------|---------|
| `doc/ARCHITECTURE.md` | Objectif renatus, packages/classes, roles modules, YAML types/modes, data/, tests/, gestion_projet/, packaging, decisions cible, schema ASCII couches |
| `gestion_projet/notes_dev_F0006.md` | Ce fichier (temps + decisions) |

## Analyse code (etat actuel)

Modules lus avant redaction :

- `src/renatus/pipeline/engine.py` (~1900 lignes) : ConnectionUtils, DependencyTree, ConnectionPipeline, ParallelIterationManager, helpers schema/workers
- `src/renatus/pipeline/connection.py` : PipelineFactory (main.duckdb, fallback lock)
- `src/renatus/pipeline/paths.py` : root configurable, arborescence data/pipeline/models
- `src/renatus/pipeline/scope.py` : hotels exclus/pilotes (deja annote F0006)
- `src/renatus/__init__.py`, `pipeline/__init__.py` : API publique reexportee
- `tests/conftest.py`, `test_f0001_*`, `test_f0002_*`, fixtures f0002
- `README.md`, `pyproject.toml`

Constat principal :

1. Le **coeur generique** fonctionne (dataframe, table, view, execute, iteration sequential, requires, modes create).
2. Des **couplages metier hotels** restent dans `engine.py` (fingerprints `t_sales`, merge parallel `hotel_code`, `t_dataset_pivot`, `refresh_scenarios`).
3. `scope.py` est domaine hotels dans le package pipeline.
4. `pipeline/` racine est vide (pas de YAML metier dans le depot core) — conforme a la cible.
5. `Paths(root=...)` est deja generique.

## Decisions documentees (pas implementees)

1. **scope hotels hors package core** — a deplacer vers domaine separe plus tard ; ne plus l importer dans le coeur pipeline.
2. **Paths generique** — conserver root configurable (deja en place) ; chemins sim/ml = conventions projet hotels.
3. **Abstraction connexion** — progressive, DuckDB par defaut ; interface seulement si besoin reel multi-backend.
4. **Pas de YAML metier dans le package core** — YAML sous `pipeline/` du projet consommateur uniquement.
5. **Pas de refactor massif dans F0006** — la feature est documentaire ; decoupage futur de `engine.py` decrit comme cible, non execute.
6. **API publique** — stabiliser autour de Paths / PipelineFactory / ConnectionPipeline / DependencyTree / ParallelIterationManager.

## Commits / push

Branche de travail : `F0006`.

1. `F0006: documenter architecture cible et etat actuel` — ajout `doc/ARCHITECTURE.md`
2. `F0006: notes_dev temps et decisions architecture` — ce fichier

Note incident : un premier commit a ete pose par erreur sur une branche locale `F0004` (checkout concurrent). Corrige par cherry-pick sur `F0006` + reset local de `F0004` sur le tip main commun. Seule `F0006` est poussee avec le contenu architecture.

## Non fait (volontaire)

- Deplacement de `scope.py`
- Abstraction connexion multi-backend
- Split de `engine.py`
- Ajout de YAML metier
- Modification features/anomalies
- Merge develop/main

## Anomalies

Aucune (Axxxx non cree).

## Fin de mission dev F0006

- Architecture ecrite et poussee sur `F0006`.
- Code production inchange (sauf doc).
- Pret pour revue gestionnaire + merge develop quand valide.
