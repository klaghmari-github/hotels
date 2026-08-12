# F0053 — Refactor OOP (Python Steps + GUI Front)

## Objectif

Aligner le code sur la regle **100 % POO** :

- Chaque type de composant pipeline = classe Python (heritage + registry)
- Front GUI = modules ES + classes (App, State, Graph, Config, Tabs, Toolbox, StepType*)
- Zero bundler (ES modules natifs)
- Comportement utilisateur inchange

## Stories

| Id | Contenu |
|----|---------|
| S0 | Helper sources JS + migration asserts monolithe |
| S1 | Package `pipeline/steps` ABC + 6 types + factory |
| S2 | Split `app.js` → `static/app/*` modules |
| S3 | Dispatch engine via Step (process/should_process) |
| S4 | Classes JS core + StepTypeRegistry |
| S5 | GUI registry unique + extract yaml_store |
| S6 | Controllers UI Graph/Tabs/Config/Project |
| S7 | Split engine.py en modules |
| S8 | Full pytest + docs ARCHITECTURE |

## Git

```
main → F0053 → F0053-Sn → merge F0053 → develop → main
```

Python (S1/S3/S5/S7) // Front (S2/S4/S6) apres S0.

## Tests

- Pendant: tests cibles story
- Fin S8: full suite; adapter tests avant de relancer si contrats modules
