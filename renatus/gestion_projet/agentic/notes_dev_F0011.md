# Notes dev F0011 — separation gestion / produit

Date: 2026-08-07
Role: developpeur + gestionnaire

## Perimetre

- Supprimer `src/renatus/agentic/` du package produit.
- Code sous `gestion_projet/src/agentic/` (package `agentic`).
- Donnees restent `gestion_projet/agentic/`.
- Tests gestion deplaces vers `gestion_projet/tests/`.
- `logs/` cree.

## Decisions

1. Package nomme `agentic` (pas `renatus.agentic`) pour eviter tout couplage.
2. `AgenticPaths` ne depend plus de `renatus.pipeline.paths`.
3. pytest pythonpath inclut `gestion_projet/src` en plus de `src`.

## Temps

~40 min
