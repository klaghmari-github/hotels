# Notes dev F0021 — UI sans hints redondants

## Objectif

Retirer les petits textes explicatifs de l interface GUI.
Garder titres de zone + labels courts + actions.

## Changes

- index.html: subtitle, hints, descriptions, labels longs, placeholders pedagogiques
- app.js: palette sans t-desc; yaml-status erreurs seulement; DataView meta court
- style.css: .t-desc / .yaml-hint caches

## Conserve

- Titres: Outils, Graphe, Config, DataView, YAML
- Labels champs courts
- Empty states minimaux (Pipeline vide, —)
- Erreurs YAML (actionnables)
- Toasts operationnels
