# Spec F0013 — Strategie de tests des interfaces graphiques

Source: avis ChatGPT transmis par l'utilisateur (console Grok, 2026-08-07).
Feature: F0013.
Capture UI liee: `gestion_projet/agentic/captures/F0012_gui_before.png`.

## Contexte

Projet renatus developpe avec Grok Build : agent gestionnaire + agent dev + agent
testeur. Question: pour une feature graphique (ex. drag & drop de composants
dans le GUI), comment le testeur code des tests automatiques ?

## Synthese de l'avis (a appliquer)

### 1. Niveaux de tests

| Niveau | Outil | Role |
|--------|-------|------|
| Logique metier | pytest | add_node / connect sans navigateur |
| Composant UI | pytest + DOM / TestClient | structure, API, data-testid |
| E2E navigateur | Playwright | parcours humain (drag, click, save) |
| Visuel | Playwright snapshots | regressions layout |

### 2. Separation critique

Le drag & drop doit appeler des fonctions metier testables :

```
gui.add_node(node_type="view", position=(420, 180))
gui.connect(source="t_sales", target="v_sales")
```

Les tests unitaires verifient le modele (nodes, edges, YAML) sans browser.

### 3. Criteres d'acceptation (exemple gui drag & drop)

- AC1 palette: Table, View, DataFrame, Execute, Iteration
- AC2 composant glissable / ajoutable sur canvas
- AC3 drop cree exactement un nœud
- AC4 position proche du drop
- AC5 type = composant choisi
- AC6 deplacement nœud existant sans duplication
- AC7 persistance apres save/reload
- AC8 suppression nœud
- AC9 liaison de dependance entre nœuds
- AC10 dependance visible dans la config

### 4. Scenario E2E metier

Ouvrir GUI → ajouter Table t_sales → View v_sales → relier → SQL → Save
→ verifier YAML backend (contrat UI → modele → pipeline).

### 5. Testabilite obligatoire

Tout element interactif important doit avoir un selecteur stable :

```
data-testid="gui-canvas"
data-testid="palette-table"
data-testid="node-t_sales"
data-testid="btn-save"
```

Interdit de s'appuyer sur `div:nth-child(...)` en E2E.

### 6. Workflow agents (TDD elargi)

```
Feature → Acceptance criteria → Tests attendus → Dev (+ testabilite) → Run tests → Review AC
```

Le testeur ne doit pas inventer des tests apres coup sans lien aux AC.

### 7. Orchestration cible

```yaml
feature:
  id: gui-drag-drop
  acceptance: [...]
  tests: { unit: true, integration: true, e2e: true, visual: true }
```

## Decision renatus (implementation F0013)

1. Enregistrer les longs descriptifs dans `gestion_projet/agentic/specs/` et
   les referencer dans features.csv.
2. Imposer `data-testid` sur le GUI (HTML + JS).
3. Tests unitaires modele gui (API create/graph/preview).
4. Tests E2E Playwright optionnels (`pytest -m e2e` + extra `e2e`).
5. Document `doc/TESTING_GUI.md` pour agents dev/test.

## Texte source integral (avis ChatGPT)

Utilise grok build pour developper ce projet. j'ai lui dis de creer des agents
un qui gere les features que je cree et les traite, le traitement consiste a
creer un agent qui fait le dev et un autre qui fait les test. quand on arrive a
une feature graphique par exemple ajoute moi dans l'interface graphique une zone
gui en mode drag & drop des composants. comment le testeur peut coder un
programme de test de cette fonctionnalite ? et comment ca peut etre teste de
facon automatique ?

Oui, un testeur peut automatiser ca. Pour une feature graphique drag & drop, il
faut penser en plusieurs niveaux de tests, pas seulement en tests unitaires.

Le plus important est de separer : logique metier du gui, comportement des
composants UI, puis parcours utilisateur reel dans un navigateur.

1. Tester la logique sans navigateur — fonctions metier add_node / connect ;
   verifications avant/apres sur le modele nodes.

2. Tester le composant graphique — monter le composant, verifier palette,
   draggable, drop, nœud, proprietes. Fragile pour vrai drag & drop.

3. Test navigateur automatise — Playwright : dragTo, expect visible, API,
   screenshots, multi-navigateurs.

4. Criteres d'acceptation precis (AC1–AC10) generes par l'agent feature.

5. Scenario E2E complet UI → YAML pipeline.

6. Identifiants stables data-testid (pas de nth-child).

7. Visual regression (toMatchSnapshot).

8. Architecture agents : Feature → Dev → Test → Review AC.

9. Tests definis avant ou avec le dev (TDD agents).

10. Orchestration Grok Build avec YAML acceptance + tests flags.

Conclusion: features graphiques testables automatiquement via Playwright +
unitaires modele + snapshots ; l'agent dev doit construire une UI testable
des le depart.
