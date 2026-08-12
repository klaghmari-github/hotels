# Notes dev F0020 — YAML colore + erreurs + pleine largeur

## Objectif

- Coloration syntaxique YAML (cles / valeurs / nombres / bool / null / commentaires)
- Erreurs de parsing indiquees clairement (ligne, colonne, snippet)
- Zone YAML stylisee en pleine largeur de la sidebar config

## Implementation

- Dual-layer: `pre#yaml-highlight` (couleurs) + `textarea#config-editor` (saisie transparente)
- `highlightYaml` / `formatYamlError` dans `app.js`
- CSS tokens `.y-key`, `.y-string`, … + `.raw-yaml` margin negative pour full width
- Statut `#yaml-status` bandeau err/ok

## Tests

`tests/test_f0020_yaml_highlight.py`
