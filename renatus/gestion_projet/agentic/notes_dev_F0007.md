# Notes dev F0007 — organisation agentic + etat + git check

Date: 2026-08-07  
Role: agent DEVELOPPEUR  
Branche: F0007 (base main `18b7ccb`)  
Temps passe: **~45 minutes**

## Perimetre

- Fichiers de coordination agents dans `gestion_projet/agentic/`.
- Etat persistant (`etat.json`, `session.md`, plans) pour reprise apres arret.
- Package POO `renatus.agentic` (etat, git check, session).
- Watchdog : heartbeat dans `etat.json` (sans spam notifications).
- CLI `agentic/state.py` (check / refresh / show).
- Pas de merge develop/main, pas de force push.
- Pas de modification `features.csv` status/temps ni `etat_agents.md`.

## Livrables

| Fichier | Action |
|---------|--------|
| `src/renatus/agentic/` | Package : paths, etat, git_check, session |
| `gestion_projet/agentic/README.md` | Spec schema + migration + usage |
| `gestion_projet/agentic/etat.json` | Snapshot machine F0007 |
| `gestion_projet/agentic/session.md` | Resume session |
| `gestion_projet/agentic/plan_F0007.md` | Plan de resolution |
| `gestion_projet/agentic/templates/plan_Fxxxx.md` | Modele de plan |
| `gestion_projet/agentic/state.py` | CLI mince vers renatus.agentic |
| `gestion_projet/watchdog.py` | Heartbeat + ignore etat.json |
| `gestion_projet/README_gestion.md` | Section agentic |
| `tests/test_f0007_agentic.py` | Tests unitaires (14) |
| `gestion_projet/notes_dev_F0007.md` | Ce fichier |

## Decisions

1. **Code Python dans `src/renatus/agentic/`** : import propre, tests pytest
   sans path-hack, reutilisable par watchdog et gestionnaire.

2. **Donnees dans `gestion_projet/agentic/`** : etat.json, session, plans —
   regle feature (coordination agents hors metier pipeline).

3. **agents = liste** d objets `{role, feature, status, notes}` (schema v1).

4. **locks/** et **notes_dev_*** restent a la racine `gestion_projet/`
   (historique + chemins stables). Migration locks optionnelle plus tard.

5. **etat_agents.md** coexiste (vue narrative gestionnaire) ; **etat.json**
   est le snapshot machine.

6. **Watchdog** ignore `agentic/etat.json` pour les notifications, ecrit
   heartbeat periodique (pid, running, heartbeat_at).

7. **Git** : check branche courante (ahead/behind/dirty) + SHAs courts
   `main_local/origin` et `develop_local/origin` pour le tableau de bord.

8. **CLI** `state.py` : mince facade (pas de logique dupliquee).

## Validation

```text
python gestion_projet/agentic/state.py check --no-fetch
# ok=True ; main/develop 18b7ccb aligns ; WARN pas de origin/F0007

pytest tests/test_f0007_agentic.py -q   # 14 passed
pytest tests/ -q                        # suite verte
```

## Commits / push

Branche : `F0007` → `origin/F0007` (tracking OK)

| hash | message |
|------|---------|
| `9c4c6ee` | F0007: agentic etat persistant, package renatus.agentic, check git |
| `cb510af` | F0007: notes_dev hashes commit et push origin/F0007 |
| `abdc08d` | F0007: CLI state.py --gestion/--repo pour tests isoles |

Tip : `abdc08d` = `origin/F0007`. Push sans force.

## Non fait (volontaire / hors scope)

- Merge develop/main (gestionnaire)
- Modification features.csv / etat_agents.md (gestionnaire)
- Deplacement locks/ ou notes historiques
- Extension schema au-dela de v1 (versioning prevu dans EtatSchema)

## Anomalies

Aucune.

## Pret pour revue / merge

Oui cote dev apres push — merge reste gestionnaire.
