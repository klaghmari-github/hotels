# Plan de resolution — F0007

## Identite

| champ | valeur |
|-------|--------|
| id | F0007 |
| titre | organisation agentic |
| branche | F0007 |
| status | en_cours |
| base main | 18b7ccb |

## Objectif

Centraliser les fichiers de coordination entre agents dans `gestion_projet/agentic/`,
avec etat machine-lisible (`etat.json`), resume session, plans de resolution,
module Python POO (etat + check git), heartbeat watchdog, tests unitaires.

## Etapes

- [x] 1. Checkout F0007, lire regles et draft agentic/README
- [x] 2. Module `renatus.agentic` (paths, etat, git_check, session)
- [x] 3. Fichiers etat.json, session.md, template plan, plan_F0007
- [x] 4. Tests unitaires `tests/test_f0007_agentic.py`
- [x] 5. Watchdog heartbeat + ignore etat.json (pas de boucle notify)
- [x] 6. README agentic + README_gestion (migration racine vs agentic)
- [x] 7. notes_dev_F0007 + commits/push `F0007: ...`
- [x] 8. Pret revue gestionnaire

## Decisions

| date | decision | motif |
|------|----------|-------|
| 2026-08-07 | Code Python dans `src/renatus/agentic/` | import package + tests pytest sans path hack |
| 2026-08-07 | Fichiers d'etat dans `gestion_projet/agentic/` | regle feature: coordination agents |
| 2026-08-07 | features.csv reste a la racine gestion_projet | explicitement demande, pas de migration |
| 2026-08-07 | locks/ reste a la racine pour l'instant | eviter casser flux existant; doc migration optionnelle |
| 2026-08-07 | etat.json ignore par notify watchdog | heartbeat ne doit pas spammer le gestionnaire |
| 2026-08-07 | CLI state.py mince + package renatus.agentic | un seul code source, CLI pour agents |
| 2026-08-07 | git.main_* / develop_* dans etat | check main/develop local vs origin |

## Risques / blocages

- Import renatus dans watchdog: fallback JSON minimal si package non installe

## Temps

| role | minutes |
|------|---------|
| developpeur | (voir notes_dev_F0007.md) |
| testeur | |

## Reprise apres arret

1. Lire ce plan + `session.md` + `etat.json`
2. `AgenticSession().startup(fetch=True)`
3. Reprendre a la premiere etape non cochee
