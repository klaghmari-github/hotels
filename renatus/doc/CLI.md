# renatus CLI

Interface en ligne de commande pour executer des etapes de pipeline DuckDB.
Mode **oneshot** (une commande puis sortie) ou **REPL** (session interactive).

## Installation

```bash
pip install -e .
```

Entrypoint : `renatus` (ou `python -m renatus`).

## Demarrage

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `db_path` | oui | Fichier DuckDB (cree si besoin selon le mode d ouverture) |
| `flow_path` | oui | Dossier flow ou fichier YAML du flux |
| `command` | non | Tokens de la commande oneshot ; absent = REPL |
| `--read-only` | non | Ouvre la base en lecture seule |

Exemples :

```bash
# REPL
renatus workspace/main.duckdb workspace/pipelines

# Oneshot : materialiser une vue avec lineage
renatus workspace/main.duckdb workspace/pipelines p_table_view v_sales

# Lecture seule
renatus main.duckdb pipelines --read-only table_view t_sales
```

## Commandes

Toutes les commandes ci-dessous prennent **un seul argument** : le nom
d etape (cle YAML), sauf `help`, `quit` et `exit`.

| Commande | Role |
|----------|------|
| `help` | Affiche l aide |
| `quit` / `exit` | Quitte le REPL |
| `p_table_view NAME` | Lineage + affichage tabulaire de la relation |
| `table_view NAME` | Affiche la relation si elle existe deja (sans creer les requires) |
| `process NAME` | Execute l etape seule |
| `process_with_requires NAME` | Execute l etape apres materialisation des requires |
| `p_iteration NAME` | Lance une iteration sequential |
| `NAME` (seul token) | Si `NAME` est une cle du flux : equivalent a `process_with_requires NAME` |

### p_table_view

Obligatoire : nom d une etape de type dataframe, table ou view.

Cree les dependances manquantes, materialise l etape, affiche le resultat
(colonnes et lignes) dans le terminal.

```bash
renatus main.duckdb pipelines p_table_view t_sales
```

### table_view

Obligatoire : nom de relation **deja presente** en base.

Ne declenche pas le lineage. Utile pour revoir un resultat sans tout
recalculer.

```bash
renatus main.duckdb pipelines table_view t_sales
```

### process

Execute uniquement l etape donnee (sans parcourir `requires`).

```bash
renatus main.duckdb pipelines process df_sales
```

### process_with_requires

Parcourt le graphe de dependances puis execute la cible.

```bash
renatus main.duckdb pipelines process_with_requires x_drop_rows
```

Raccourci REPL ou oneshot : un seul token egal a une cle flux.

```bash
renatus main.duckdb pipelines x_drop_rows
```

### p_iteration

Lance le composant iteration (voir doc core).

```bash
renatus main.duckdb pipelines p_iteration i_run
```

## REPL

```text
renatus> help
renatus> p_table_view v_sales
renatus> process_with_requires t_eu
renatus> quit
```

Les erreurs (etape absente, relation manquante, SQL) s affichent sur la
sortie d erreur ; le code de sortie oneshot est non nul en cas d echec.
