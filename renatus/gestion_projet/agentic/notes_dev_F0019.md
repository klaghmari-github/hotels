# Notes dev F0019 — requires multi-select + DataView prerequis

## Objectif

Pour table / view / execute / iteration:
- config graphique complete et synchronisee avec le YAML
- selection des sources prerequis (requires) via multi-select (plus de champ texte virgule seul)
- en se branchant sur une source (coche ou clic nom), afficher le resultat dans DataView (bas du gui)

## Implementation

- `index.html`: `#cfg-requires-picker`, hidden `#cfg-requires`, champs iteration avec data-testid + datalist
- `app.js`: `renderRequiresPicker`, `getSelectedRequires`, `previewRequireSource`, `dataviewIsPrereq`
- `style.css`: styles `.requires-picker`, `.require-item`, badge prerequis DataView
- Sync: coche → `requires` YAML ; YAML → cochage ; save → edges graphe

## Comportement UX

1. Selectionner une step table/view/execute/iteration
2. Le picker liste les autres steps du graphe (checkbox + type)
3. Cocher une source → ajoute a `requires` + sync YAML + charge DataView de la source
4. Clic sur le nom → apercu DataView (badge "(prerequis)")
5. Build & afficher / Recharger s appliquent a la source DataView courante

## Tests

`tests/test_f0019_requires_dataview.py`
