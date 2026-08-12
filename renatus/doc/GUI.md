# renatus GUI (renatus-gui)

Interface web pour construire et inspecter un flux : palette d outils,
graphe de dependances, formulaire de config synchronise avec le YAML,
DataView (apercu limite).

Le nom **renatus** renvoie a la renaissance des datasets : le lineage
declaratif (YAML + graphe) permet de recreer une relation a partir de ses
sources. Le logo officiel symbolise ce cycle (anneau) et la chaine de
dependances (R en graphe de noeuds) ; voir `doc/assets/renatus-logo.png`.

## Demarrage

```bash
pip install -e .
# sans argument (A0006) : workspace/main.duckdb + workspace/pipelines
renatus-gui

renatus-gui <db.duckdb> <flow_dir> [options]
renatus-gui mon.renatus.yaml
# equivalent : python -m renatus.gui ...
```

Sans argument, le GUI demarre sur le workspace par defaut du repertoire
courant (`workspace/`). S un unique fichier `*.renatus.yaml` est present a
la racine, il est charge automatiquement.

L ordre des deux chemins est flexible si l un se termine par `.duckdb`.
Si les dossiers n existent pas, le serveur prepare un workspace vide
(base et dossier flow).

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `db_path` | oui | Fichier DuckDB |
| `flow_path` | oui | Dossier flow YAML |
| `--host` | non | Defaut `127.0.0.1` |
| `--port` | non | Defaut `8000` ; port libre automatique si occupe |
| `--strict-port` | non | Echec si le port choisi est pris |
| `--read-only` | non | Pas d ecriture YAML / upload |
| `--max-rows` | non | Plafond serialisation resultats |

Ouvrir l URL affichee dans le navigateur (ex. `http://127.0.0.1:8000/`).

## Zones de l ecran

| Zone | Role |
|------|------|
| Outils | Palette par regions : **Datasets**, **Execute**, **Flow**, **Auto** (F0128) |
| Flux | Graphe `requires` ; select **toutes** zones disque + `all` + auto-vues ; zoom ; lineage gris ; import flux ; croix supprimer sur selection |
| Config | Formulaire view + crayon ; Objects / Requires ; schema / shape / renatus_time ; auto-zones RO + Convertir |
| View / Track | Apercu paginé (3–100 lignes/page) ; process Output/Error ; Track par composant |

Chaque type d outil a un pictogramme et une couleur.

Diagrammes de classes frontend : [documentation.html#uml-frontend](documentation.html#uml-frontend).

## Types d etapes dans l UI

Les parametres YAML sont les memes qu en core ([CORE.md](CORE.md)).
Correspondance formulaire :

### Dataframe

| Champ UI | YAML | Obligatoire | Role |
|----------|------|-------------|------|
| Fichier (picker / drop) | `file` | oui pour Build | Fichier source |
| Mode | `mode` | non | `create_if_not_exists` (defaut, reutilise session) / `create_or_replace` |
| Name | `name` | non | Relation en base |

Pas de SQL. Nom d etape horodate a la creation (`dataframe_YYYY_MM_DD_hh_mm_ss`),
renommable dans Config.

### Table / View

| Champ UI | YAML | Obligatoire | Role |
|----------|------|-------------|------|
| Mode | `mode` | non | create_if_not_exists / create_or_replace |
| Nom relation | `name` | non | Nom en base (sinon id step) |
| Requires | `requires` | non | Multi-select des autres steps |
| Script | `script` | oui | Definition SQL (legacy `sql` accepte) |

Cocher une source dans Requires met a jour le YAML et peut afficher son
apercu dans DataView.

### Execute

| Champ UI | YAML | Obligatoire | Role |
|----------|------|-------------|------|
| Requires | `requires` | non | Dependances |
| SQL | `sql` | oui | Instruction a executer |

### Iteration

| Champ UI | YAML | Obligatoire | Role |
|----------|------|-------------|------|
| Requires | `requires` | non | Dependances de preparation |
| Target | `target` | oui | Etape rejouee a chaque scenario |
| Scenarios | `scenarios` | oui | Table des scenarios |
| step_view | `step_view` | oui | Vue temporaire par tour |
| SQL | (optionnel UI) | non | Non utilise par le moteur sequential |

Le YAML peut aussi contenir `execution` et `order_by` (edition manuelle
dans le panneau YAML).

## Editeur YAML

- Coloration des cles et des valeurs
- Sync formulaire vers YAML et inverse
- Erreur de parsing : message avec ligne et colonne
- Pleine largeur de la colonne Config

## View (DataView)

| Action | Role |
|--------|------|
| Selection d un dataset | Apercu **paginé** (defaut 3 lignes) |
| Lignes / page | Select 3 / 10 / 25 / 50 / 100 — une page chargee a la fois |
| ‹ › | Page precedente / suivante (`limit` + `page` / `offset`) |
| Renatus | Materialise (lineage) puis page 1 |

Process (python/shell) : onglets Output / Error, pas de pagination table.

## Flux (comportements)

- **Selection** : grise les nœuds hors lineage requires amont (F0127) ; si **zone** selectionnee, tous les membres restent actifs (F0134)
- **Liens** : segments orthogonaux H/V uniquement ; ne traversent pas les nœuds (F0135)
- **Zoom** : boutons +/−/100 %, Ctrl+molette, Ctrl+0
- **Scroll** horizontal et vertical
- **Import dossier** : cree arborescence + zones ; selecteur liste toutes les zones

## Captures d ecran (F0140)

Les menus deroulants (`select.renatus-select`) utilisent une **listbox
custom** (pas le popup OS). **Print Screen** et raccourcis capture systeme
ne ferment plus le menu — vous pouvez capturer l ecran menu ouvert.

## Notebook (F0137)

Composant **notebook** (palette Execute) : meme session Python persistante
que `execute_python` (F0136). Le crayon **Script** ouvre une fenetre type
**Jupyter Lab** :

- cellule de code + **Run** (Ctrl+Enter) / **Run & Save**
- panneau **Variables session** (types, preview DataFrame…)
- clic sur une variable → insertion dans la cellule
- pas besoin de reconstruire un DataFrame deja en session

API : `GET /gui/python/session/vars`, `POST /gui/python/session/exec`.

## Progression actions longues (F0132 / F0133)

Pendant un **upload dossier** ou un **import** (et autres traitements longs),
une pop **bloquante** « Traitement en cours » s affiche avec barre de
progression. Plus d ecran vide apres fermeture du dialog d import :
le feedback reste visible jusqu a la fin (refresh graphe inclus).
ESC ne ferme pas la pop pendant le traitement.

**F0133** : apres l import serveur, le graphe se charge **sans** selection
lourde (`selectStep` / preview) sous la pop — sinon hang vers 90 %.
La selection Config est differee juste apres fermeture de la progression.

## Selecteur de zones (F0131 / F0138)

Liste **main + une entree par zone id** (chemin canonique du step `type: zone`).
Pas de vue `all` par defaut, pas d onglet `auto/*`, pas de sous-dossiers FS
fantomes (import imbriqué). Labels desambigues (chemin complet si besoin).
Une auto-zone activee (double-clic) peut apparaitre temporairement.

## Auto-zones (palette Auto, F0139)

**Templates** qui creent une **zone normale** a l init (plus de vue logique RO).

| Outil | Init |
|-------|------|
| **Flat zone** | Choisir une zone parent → copie recursive de tous les composants feuille |
| **Back zone** | Selection composant → lineage requires (amont) |
| **For zone** | Selection → required_by (aval) |
| **Bid zone** | Selection → amont + aval |

Resultat : `type: zone` + dossier + YAML copies. Editable comme toute zone.

## API HTTP du GUI (extraits)

Prefixe `/gui`. Reponses JSON.

| Methode | Chemin | Role |
|---------|--------|------|
| GET | `/gui/tools` | Catalogue palette (regions datasets/execute/flow/auto) |
| GET | `/gui/graph?tab=` | Noeuds / aretes ; tab = zone physique ou id auto-zone |
| GET | `/gui/tabs` | main + zones physiques (+ auto activee temporairement) |
| GET/PUT | `/gui/step/{id}` | Config (objects effectifs zone/auto) |
| POST | `/gui/steps` | Cree une etape |
| POST | `/gui/build/{id}` | Build unifie ; zone → `zone_build` |
| GET | `/gui/build/{id}/plan` | Plan jobs zone (progression UI) |
| POST | `/gui/build/{id}/complete` | Finalise zone orchestree client |
| GET | `/gui/preview/{id}?limit=&page=` | Apercu paginé ; `build=true` materialise |
| POST | `/gui/auto-zone` | Cree auto-zone dans main `{type, object?}` |
| POST | `/gui/auto-zone/{id}/convert` | Auto → zone physique editable |
| POST | `/gui/import/flow` | Import YAML ou dossier ; purge `import_flow/` staging apres succes (F0143) |
| POST | `/gui/upload` | Fichier vers `input/` |

Query preview/result : `limit`, `offset` ou `page` (F0123/F0124).

Exemple :

```bash
curl -s http://127.0.0.1:8000/gui/graph
curl -s -X POST http://127.0.0.1:8000/gui/build/t_sales?limit=3
```

## Workflow type

1. Lancer le GUI sur une base et un dossier flow
2. Ajouter un dataframe, choisir un fichier Excel ou CSV
3. Ajouter une table, cocher le dataframe en Requires, ecrire le SQL
4. Save YAML puis Build ; lire le DataView
5. Enchainer vues / tables (filtre, group by) ; le graphe montre les aretes
6. Pour une iteration : preparer scenarios, results, execute, puis l etape
   iteration ; Build ; controler via une vue sur la table de resultats

Les tests de chaine Excel et d iteration sont dans
`tests/test_f0023_graph_dependencies_xlsx.py` et
`tests/test_f0024_iteration_component.py`.

## Tests de l interface

Voir [TESTING_GUI.md](TESTING_GUI.md) : data-testid, niveaux unit / E2E
Playwright.


## Projet renatus (sauvegarde + git F0032 / F0043)

Un fichier `.renatus.yaml` memorise la **config de connexion** du workspace.
Le repertoire parent est le **root projet** et devient un **depot git local** :

- premiere sauvegarde / creation : `git init`, commit sur `main`, branche de
  travail `b_YYYY_MM_DD_hh_mm_ss_…`
- chaque modification de step/YAML est **auto-committee** sur la branche de travail
- a la reouverture : checkout **main** ; si une branche est en avance, le GUI
  propose de la charger
- bouton **Sauver projet** : **merge** de la branche de travail dans `main`

### Contenu versionne vs donnees privees (F0043)

| Element | Dans le projet git ? | Notes |
|---------|----------------------|--------|
| `.renatus.yaml` | oui | Config connexion (paths) |
| dossier `flow/` | **obligatoire dans le root** | YAML des steps, suivi git |
| base DuckDB (`db_path`) | non (ignore `*.duckdb`) | Chemin stocke ; fichier peut etre **hors** projet |
| fichiers sources (CSV, Excel…) | non imposes | **References** par chemin ; pas de copie imposee |
| `input/` (upload UI) | ignore git | Convenience locale seulement |

Les **pipelines de traitement doivent vivre sous le dossier projet** (sinon
impossible de suivre les modifications avec git). Les **donnees** restent
privees : on reference un chemin (absolu ou relatif), on ne versionne pas le
contenu metier.

Exemple de structure :

```text
mon_projet/                 # root = git
  mon_projet.renatus.yaml   # name, db_path, flow_path
  flow/                # = flow_path (toujours dans le projet)
    src.yaml                # zone main : YAML a la racine de flow/
    t_base.yaml
    etl/                    # zone = sous-dossier (onglet GUI)
      t_clean.yaml          # objet = un fichier <id>.yaml
      v_kpi.yaml
  .gitignore                # *.duckdb, input/, …
# Donnees ailleurs (ex.) :
# /data/private/sources/sales.csv   ← reference dans config.file
# /data/private/warehouse.duckdb    ← db_path absolu possible
```

### Mapping GUI ↔ filesystem (F0045)

| Action GUI | Sur le disque |
|---------------|----------------|
| Creer un **projet** | Dossier projet + `flow/` + `.renatus.yaml` + git |
| Zone **main** | Fichiers `flow/*.yaml` (pas de sous-dossier) |
| Creer une **zone** (bouton +) | Sous-dossier `flow/<nom>/` |
| Creer un **objet** (outil) | Fichier `flow/[zone/]<id>.yaml` |
| Requires / dependances | Ids dans le YAML (pas de copie de fichier) |

Tous les YAML de flux restent **a l interieur** de `flow/`.

### Fichier `.renatus.yaml`

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `version` | non | Format (1) |
| `name` | non | Libelle du projet |
| `db_path` | oui | Fichier DuckDB (relatif au projet ou **absolu hors projet**) |
| `flow_path` | oui | Dossier flow (**sous le root projet**, ex. `flow`) |
| `read_only` | non | Ouverture lecture seule |

### GUI

- **Ouvrir / Creer** : chemin projet ; si nouveau → configurer db + pipelines
  (pipelines forces dans le projet)
- **Sauver projet** : enregistre la config connexion + merge git
- **Ouvrir** : recharge le workspace depuis le fichier projet

### CLI

```bash
renatus-gui mon.renatus.yaml
renatus-gui --project mon.renatus.yaml
```

API : `GET /gui/project`, `POST /gui/project/save`, `POST /gui/project/open`,
`POST /gui/project/inspect`, `POST /gui/project/create`.

