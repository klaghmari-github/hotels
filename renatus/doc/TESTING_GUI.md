# Tests des interfaces graphiques — renatus

Strategie inspiree de la spec
`gestion_projet/agentic/specs/F0013_gui_testing_strategy.md` (F0013).

## Principes

1. **Plusieurs niveaux** : unit (modele/API) → integration → E2E navigateur →
   snapshots visuels optionnels.
2. **UI testable** : tout controle important a un `data-testid` stable.
3. **Criteres d'acceptation (AC)** definis avec la feature, avant ou pendant
   le dev — le testeur ne devine pas apres coup.
4. **Contrat metier** : un test E2E utile valide UI → API → YAML pipeline,
   pas seulement qu'un div a bouge.

## data-testid GUI (obligatoires)

| testid | Element |
|--------|---------|
| `gui-palette` | boite a outils |
| `palette-dataframe` / `palette-table` / `palette-view` / `palette-execute` / `palette-iteration` | outils |
| `gui-canvas` | zone graphe |
| `node-<name>` | nœud graphe |
| `gui-config` | panneau config |
| `btn-dv-build` | Renatus (View) — F0086: plus de boutons actions Config |
| `gui-dataview` | zone bas |
| `btn-dv-build` / `btn-dv-reload` | actions dataview |
| `chip-db` / `chip-pipe` | chips workspace |
| `new-step-dialog` / `new-step-name` | creation step |

## Niveaux concrets renatus

### A. Unit / integration (pytest, toujours CI)

- `tests/test_f0012_gui.py` : tools, create, graph edges, preview
- `tests/test_f0010_gui.py` : connect, save YAML, static HTML
- Nouveau : presence des `data-testid` dans index.html / app.js

### B. E2E Playwright (optionnel, extra `e2e`)

```bash
pip install -e ".[e2e]"
playwright install chromium
pytest -m e2e -q
```

Scenario type :

1. Demarrer app gui (fixture uvicorn / TestClient ASGI)
2. Verifier palette visible (`get_by_test_id("palette-table")`)
3. Creer une step table via UI
4. Verifier nœud `node-t_demo`
5. Save → controler fichier YAML sur disque

### C. Visual regression (optionnel)

```js
await expect(page).toHaveScreenshot("gui-empty.png");
```

Compare a un snapshot de reference sous `tests/e2e/__snapshots__/`.

## Workflow agents (gestion_projet)

```
Feature Agent
  → ecrit specs/Fxxxx_*.md + AC
  → reference captures/ si screenshot
Developer Agent
  → implemente + data-testid
  → push branche Fxxxx
Test Agent
  → unit + integration
  → e2e si feature UI
  → notes_test_Fxxxx.md (mapping AC → tests)
Review / Gestionnaire
  → merge si AC couverts et pytest vert
```

## Exemple AC pour drag & drop futur

| AC | Then |
|----|------|
| AC1 | palette contient 5 outils |
| AC2 | drop table sur canvas cree 1 nœud |
| AC3 | type nœud = table |
| AC4 | YAML persiste apres save |
| AC5 | requires cree une arete graphe |

## Commandes

```bash
# CI rapide (pas de browser)
pytest -q -m "not e2e"

# Complet UI
pytest -q
pytest -m e2e -q
```
