# Gestion de projet renatus

Separation stricte : ce dossier orchestre les agents. Le package produit
`src/renatus/` ne contient **aucun** code de gestion.

## Racine `gestion_projet/`

| element | role |
|---------|------|
| `features.csv` | backlog features |
| `anomalies.csv` | backlog anomalies |
| `regles_de_gestion.md` | regles invariantes |
| `watchdog.py` | ecoute modifications + heartbeat |
| `.running` | watchdog actif |
| `notifications.log` | journal |
| `locks/` | locks merge develop/main |
| `questions_reponses_.csv` | Q/R console |
| `README_gestion.md` | ce fichier |

## `agentic/` — donnees agents

| fichier | role |
|---------|------|
| `etat.json` | snapshot machine |
| `etat_agents.md` | vue humaine |
| `session.md` | resume session |
| `plan_F*.md` / `plan_A*.md` | plans |
| `notes_dev_*.md` / `notes_test_*.md` | notes agents |
| `templates/` | modeles |
| `state.py` | CLI fine (check/show/refresh) |

## `src/` — programmes Python de gestion

Package **`agentic`** (pas renatus) :

```
gestion_projet/src/agentic/
  paths.py, etat.py, git_check.py, session.py
```

```bash
# depuis la racine du depot
PYTHONPATH=gestion_projet/src python -c "from agentic import AgenticSession; print(AgenticSession().startup(fetch=False))"
python gestion_projet/agentic/state.py check
```

## `logs/`

Journaux optionnels de la gestion (hors package produit).

## `tests/`

Tests unitaires **uniquement** de la gestion (package agentic, layout, watchdog).
Les tests du produit restent dans `/tests` a la racine du depot.

```bash
pytest gestion_projet/tests -q
pytest tests -q   # produit renatus seulement
```

## Cycle

1. Watchdog debounce 5s, notifie.
2. Gestionnaire lit features/anomalies, maj `agentic/etat.json`.
3. Demarrage : `python gestion_projet/agentic/state.py check`.
4. Feature = branche F00xx depuis main, dev + tests en parallele.
5. Merge FF feature -> develop (lock) puis develop -> main (lock).
