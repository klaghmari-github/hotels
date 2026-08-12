# F0052 — Composant Zone (organisationnel)

## Objectif

Introduire un composant **zone** dans la palette GUI : purement organisationnel
(aucun traitement DuckDB). Une zone = un dossier sous `pipelines/`.

## Comportement

| Action | Effet |
|--------|--------|
| Clic palette Zone | Cree un nœud zone + dossier sous l onglet actif |
| Deposer d autres composants | YAML dans le dossier de la zone (via onglet ouvert) |
| Zone dans une zone | Sous-dossier imbriqué (`pipelines/a/b/`) |
| Double-clic sur zone | Ouvre un onglet graphe sur le contenu de la zone |
| Fermer un onglet | Ferme l onglet (ne supprime pas la zone) |
| Onglet `main` | Non fermable (= racine `pipelines/`) |

## Modele disque

```
pipelines/
  df_a.yaml                 # objet en main
  zone_etl.yaml             # type: zone (nœud visible en main)
  zone_etl/                 # contenu de la zone
    t_b.yaml
    zone_sub.yaml
    zone_sub/
      v_c.yaml
```

- Id zone = nom du dossier (et du fichier `<id>.yaml` parent).
- Onglet id = chemin relatif (`main` | `zone_etl` | `zone_etl/zone_sub`).
- Le moteur ignore `type: zone` (no-op).

## Hors scope de cette version

- Drag-drop de nœuds entre zones (deplacer fichiers).
- Suite du message utilisateur coupe : « chaque composant doit avoit… » — a preciser.
