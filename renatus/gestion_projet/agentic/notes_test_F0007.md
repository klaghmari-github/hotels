# Notes testeur — F0007 (organisation agentic)

Date: 2026-08-07  
Role: agent TESTEUR  
Branche: **F0007**  
Base review: working tree + commits `9c4c6ee`…`7f9f3e1` / `origin/F0007`  
Temps passe: **~35 minutes** (attente livrables, dualite schema puis unification, CLI, layout/watchdog, pytest, notes)

## Perimetre

Checklist de **conformite** feature F0007 :

1. Fichiers de coordination agents dans `gestion_projet/agentic/`
2. Etat persistant (`etat.json`, `session.md`, plans) pour reprise apres redemarrage
3. Verification git local vs remote au demarrage (outil documente + executable)
4. Separation metier (`features.csv`, …) vs agentic
5. Pas de regression : tests historiques F0001/F0002 verts
6. Doc (`README_gestion`, `agentic/README`) pointe vers agentic
7. Historique `notes_*` non casse

Aucun merge. `features.csv` / `anomalies.csv` / `etat_agents.md` non modifies par le testeur.

## Structure livree

```
gestion_projet/
  features.csv, anomalies.csv, watchdog.py, locks/, notes_*   # racine metier / historique
  README_gestion.md                                          # section agentic
  agentic/
    README.md, etat.json, session.md
    plan_F0007.md, templates/plan_Fxxxx.md
    state.py                     # CLI mince -> renatus.agentic
    __init__.py
src/renatus/agentic/
  paths.py, etat.py, git_check.py, session.py, __init__.py
tests/
  test_f0007_agentic.py            # 14 — package (mock git)
  test_f0007_agentic_state.py      # 10 — CLI + integration package
  test_f0007_layout_watchdog.py    # 10 — layout depot + watchdog isole
```

## Checklist

| # | Item | Statut | Detail |
|---|------|--------|--------|
| 1 | Dossier `gestion_projet/agentic/` existe et documente | **OK** | README role + migration + schema v1 + templates |
| 2 | `etat.json` present, JSON valide, champs utiles | **OK** | `schema_version`, watchdog, agents, features_en_cours, locks, git (branch, tips, ahead/behind, main_*/develop_*) |
| 3 | `session.md` et `plan_F0007.md` presents et coherents | **OK** | F0007 / base 18b7ccb / reprise documentee ; plan etapes cochees cote dev |
| 4 | Separation metier vs agentic | **OK** | features/anomalies/regles/watchdog/notes/locks a la racine ; etat/session/plans dans agentic/ |
| 5 | Procedure / outil check git local vs origin | **OK** | `AgenticSession.startup` + CLI `python gestion_projet/agentic/state.py check` (fetch, ahead/behind, dirty, SHAs main/develop) |
| 6 | Pas de regression pytest historiques | **OK** | 13 tests F0001+F0002 verts |
| 7 | README_gestion pointe vers agentic | **OK** | section + cycle demarrage git + code sample |
| 8 | Historique `notes_*` non casse | **OK** | notes_dev/test F0001–F0006 toujours a la racine `gestion_projet/` |
| 9 | Schema live chargeable par `renatus.agentic` | **OK** | `EtatStore.read()` OK ; agents = liste |
| 10 | Source de verite unique etat/git | **OK** | `state.py` = CLI mince ; metier dans `src/renatus/agentic/` |
| 11 | Watchdog `.running` + ignore heartbeat | **OK** | `IGNORE_REL_PATHS` + heartbeat package/fallback |
| 12 | Suite complete verte | **OK** | **47 passed** (13 historiques + 34 F0007) |

## Evolution pendant la revue

1. **Dualite initiale (NO-GO temporaire)** : monolithe `state.py` (agents **dict**, git main/develop/feature) vs package `renatus.agentic` (agents **list**, git local_branch). Live `etat.json` non chargeable par `EtatStore` (`EtatSchemaError: agents doit etre une liste`).
2. **Correction dev** : `state.py` reduit a CLI mince ; `etat.json` aligne schema package ; champs git etendus (`main_local`, `develop_local`, …) ; push `origin/F0007`.
3. **Re-test** : dualite levee ; CLI + package + layout/watchdog verts.

## Execution manuelle (outils)

```text
python gestion_projet/agentic/state.py check
# ok=True
# branche=F0007 ahead=0 behind=0 dirty=True fetch_ok=True
# main_local=18b7ccb = main_origin ; develop_local=18b7ccb = develop_origin
# WARN: working tree non propre (fichiers gestionnaire / etat heartbeat)

python gestion_projet/agentic/state.py show   # JSON schema v1 valide
python gestion_projet/agentic/state.py refresh --no-fetch  # OK
```

`AgenticSession().startup(fetch=True)` : `ok=True`, warnings dirty WT seulement.

## Tests

### Package (`test_f0007_agentic.py`) — 14 PASS

paths, schema, store roundtrip / load_or_create / heartbeat / corrupt JSON,  
git mock (ahead/behind, no remote, fetch fail), session startup / summary / agents, exports.

### CLI + integration (`test_f0007_agentic_state.py`) — 10 PASS

CLI show/check/refresh, show sans fichier, check mini-repo, refresh alias, commande inconnue,  
roundtrip package, git checker mini-repo + feature branch, session startup, state.py non-duplique.

### Layout + watchdog (`test_f0007_layout_watchdog.py`) — 10 PASS

agentic + README, csv racine, artefacts reprise, watchdog present, schema_version live,  
ignore etat.json, snapshot, create_running+heartbeat, fallback sans package, resume simule.

## Commande et resultat pytest

```text
.venv/bin/python -m pytest tests/ -q
# 47 passed in ~1.0s

.venv/bin/python -m pytest tests/test_f0001_init.py tests/test_f0002_pipeline_features.py -q
# 13 passed
```

Environnement: `.venv` local, package renatus editable 0.1.0, pytest-9.1.1.

## Ecarts restants (non bloquants)

1. Working tree souvent **dirty** (heartbeat `etat.json`, fichiers gestionnaire hors scope F0007) — le check signale correctement `dirty=True`.
2. Couverture unitaire legere sur desync **main/develop** derriere origin (champs presents, cas d erreur dedie optionnel).
3. `plan_F0007.md` case « temps testeur » vide — renseignee ici (**35 min**).

## Non fait (hors scope testeur)

- Merge develop/main
- Modification `features.csv` / `anomalies.csv` / `etat_agents.md`
- Force push

## Verdict

### **GO merge**

**Motifs GO :**

- Organisation `gestion_projet/agentic/` documentee + artefacts de reprise (etat, session, plan, templates).
- Package `renatus.agentic` POO (etat versionne, git mockable, session startup) + CLI `state.py`.
- Schema live unifie et chargeable ; check git local/remote executable et utile (ahead/behind, main/develop, dirty).
- Separation metier / agentic respectee ; historique notes_* intact.
- Watchdog heartbeat sans boucle notifications ; `.running` preserve.
- **47 tests verts** dont 13 historiques (pas de regression F0001–F0002) et 34 F0007.

**Pour le gestionnaire :** merge FF `F0007` → `develop` puis `main` quand pret ; renseigner `features.csv` temps (dev ~45 min / test ~35 min) hors agent testeur.
