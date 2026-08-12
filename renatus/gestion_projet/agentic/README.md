# agentic — etat persistant des agents

Ce dossier contient les fichiers de **coordination entre agents**.
Il doit survivre aux arrets et redemarrages de session.

Code Python associe : package `agentic`
(`gestion_projet/src/agentic/`) — **hors** du package produit renatus.

## Contenu

| fichier / dossier | role |
|-------------------|------|
| `etat.json` | snapshot machine-lisible (schema versionne) |
| `etat_agents.md` | vue humaine gestionnaire / agents / locks |
| `session.md` | resume humain de la derniere session |
| `plan_Fxxxx.md` | plan de resolution d'une feature en cours |
| `plan_Axxxx.md` | plan de resolution d'une anomalie |
| `notes_dev_Fxxxx.md` | notes developpeur (temps, decisions) |
| `notes_test_Fxxxx.md` | notes testeur (checklist, verdict) |
| `templates/plan_Fxxxx.md` | modele a copier pour une nouvelle feature |
| `README.md` | ce fichier |

## Schema `etat.json` (version 1)

```json
{
  "schema_version": 1,
  "updated_at": "YYYY-MM-DDTHH:MM:SS",
  "watchdog": {
    "pid": null,
    "running": false,
    "heartbeat_at": null
  },
  "agents": [
    {
      "role": "developpeur|testeur|gestionnaire",
      "feature": "F0007",
      "status": "en_cours",
      "notes": "libre"
    }
  ],
  "features_en_cours": ["F0007"],
  "anomalies_en_cours": [],
  "locks": {
    "develop": null,
    "main": null
  },
  "git": {
    "local_branch": "F0007",
    "local_tip": "sha",
    "remote_tip": "sha",
    "ahead": 0,
    "behind": 0,
    "dirty": false,
    "fetch_ok": true,
    "checked_at": "YYYY-MM-DDTHH:MM:SS",
    "main_local": "18b7ccb",
    "main_origin": "18b7ccb",
    "develop_local": "18b7ccb",
    "develop_origin": "18b7ccb"
  }
}
```

### Champs

- **schema_version** : entier ; versions supportees documentees dans `EtatSchema`
- **watchdog** : pid process, flag running, dernier heartbeat (ecrit par `watchdog.py`)
- **agents** : liste des agents actifs (role unique recommande)
- **features_en_cours** / **anomalies_en_cours** : ids en travail
- **locks** : holder du lock merge (`develop` / `main`) ou null
- **git** : branche courante (ahead/behind/dirty) + SHAs courts main/develop local vs origin

## Module Python

Deux points d'entree (meme dossier d'etat) :

### 1. Package `agentic` sous `gestion_projet/src/` (agents / tests gestion)

```python
# PYTHONPATH=gestion_projet/src  (ou pytest pythonpath)
from agentic import AgenticSession, EtatStore, GitStatusChecker

session = AgenticSession()
report = session.startup(fetch=True)
if not report["ok"]:
    print(report["warnings"])

store = EtatStore()
store.update_heartbeat(pid=1234)
session.write_session_summary("# Session\n\n...")
```

| classe | role |
|--------|------|
| `AgenticPaths` | chemins agentic/ (lazy gestion_dir) |
| `Etat` / `EtatStore` | modele + lecture/ecriture atomique |
| `EtatSchema` | validation et detection de version |
| `GitStatusChecker` | fetch + ahead/behind (runner mockable) |
| `AgenticSession` | facade demarrage + helpers agents/locks |

### 2. CLI colocalisee `state.py` (gestionnaire rapide)

```bash
python gestion_projet/agentic/state.py show
python gestion_projet/agentic/state.py check
python gestion_projet/agentic/state.py refresh
```

`state.py` enrichit aussi main/develop/feature et lit `.running` / `locks/`.
Les deux formats d'agents (liste ou dict par role) sont acceptes en lecture.

## Migration : racine `gestion_projet/` vs `agentic/`

### Reste a la racine `gestion_projet/` (metier suivi projet)

| fichier | motif |
|---------|-------|
| `features.csv` | backlog features (ne pas deplacer) |
| `anomalies.csv` | backlog anomalies |
| `regles_de_gestion.md` | regles invariantes |
| `watchdog.py` | process d'ecoute |
| `.running` / `.watchdog_state` | runtime watchdog |
| `notifications.log` | journal changements |
| `locks/` | locks merge fichiers |
| `questions_reponses_.csv` | Q/R console |
| `README_gestion.md` | doc gestion |

### Va dans `agentic/` (coordination + notes agents)

| fichier | motif |
|---------|-------|
| `etat.json` | etat machine pour reprise |
| `etat_agents.md` | vue markdown gestionnaire |
| `session.md` | resume session |
| `plan_F*.md` / `plan_A*.md` | plans de resolution |
| `notes_dev_*.md` / `notes_test_*.md` | notes agents (place naturelle) |
| `templates/` | modeles de plans |

### Non migre pour l'instant (volontaire)

- `locks/` reste a la racine pour ne pas casser les scripts existants

## Watchdog

Le watchdog ecrit un **heartbeat** periodique dans `etat.json`.
Ce fichier est **ignore** pour les notifications (evite une boucle
debounce / spam gestionnaire). Les autres fichiers sous `agentic/`
(plans, session.md) restent surveilles normalement.

## Reprise apres arret

1. Lire `session.md` et `etat.json`
2. Lire le `plan_Fxxxx.md` / `plan_Axxxx.md` concerne
3. `AgenticSession().startup(fetch=True)` — corriger si behind > 0
4. Reprendre a la premiere etape non cochee du plan
