# Notes F0027 — onglets multi-pipeline

## Modele

- `pipelines/*.yaml` → onglet **main**
- `pipelines/<nom>/*.yaml` → onglet **nom**
- Moteur charge toujours tout (build lineage OK)
- Graphe filtre par onglet (`GET /gui/graph?tab=`)

## API

- GET/POST /gui/tabs
- POST /gui/tabs/{name}/activate
- DELETE /gui/tabs/{name} (vide seulement)
- POST /gui/steps body.tab

## UI

Barre d onglets sous le titre Graphe ; + pour creer.
