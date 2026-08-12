# renatus core

**renatus** evoque la *renaissance* d un dataset : on construit des relations
DuckDB a partir d un flux YAML dont le lineage est explicite. Rejouer une
etape recree le resultat a partir de ses sources, sans boite noire.

Le coeur est le package `renatus.pipeline`. Il charge des etapes declarees en
YAML, ouvre une base DuckDB, et cree les relations en respectant le graphe de
dependances (`requires`). Le GUI et le CLI reposent sur ce meme moteur.

## Concepts

Un **pipeline** est un dictionnaire d etapes. Chaque etape a un **id**
applicatif (cle YAML, immutable) et une configuration. Les dependances se
declarent dans `requires` (toujours des ids) : le moteur cree d abord les
etapes manquantes avant d executer la cible.

### Id, label et name (F0031 / F0048)

| Notion | Role |
|--------|------|
| **id** | Identifiant unique gere par l application (ex. `dataframe_2026_08_08_14_30_05`). Cle du mapping YAML et nom de fichier `<id>.yaml`. Non modifiable. Reference dans `requires`. |
| **label** | Nom du **composant** dans l UI (optionnel, defaut = id). Modifiable librement. |
| **name** | Nom de l **entite en base** (dataframe / table / view). Utilise dans le SQL et `register`. Defaut = label ; independant ensuite. |

Exemple : composant `label: df_2026`, `name: df_sales`, fichier CSV. Une vue
`requires: [id_du_dataframe]` et SQL `SELECT * FROM df_sales`.

Un composant = un fichier `flow/[zone/]<id>.yaml` contenant un seul
mapping `{ <id>: { type, label, ... } }`.

Layout filesystem (F0045) :

| Concept | Chemin |
|---------|--------|
| Projet | dossier root (+ `.renatus.yaml`, git) |
| Pipelines | toujours `projet/flow/` |
| Zone main | `flow/<id>.yaml` |
| Zone (type zone) | `flow/<zone>.yaml` + dossier `flow/<zone>/` |
| Zone imbrique | `flow/a/b.yaml` + `flow/a/b/` |
| Objet | un fichier YAML monocomposant dans le dossier de la zone |

Le dossier ou fichier YAML est charge au demarrage. Si l argument est un
dossier, tous les fichiers `.yaml` / `.yml` (y compris sous-dossiers) sont
fusionnes. Une meme cle d etape ne peut pas apparaitre dans deux fichiers.

Le **project_dir** sert a resoudre les chemins de fichiers (dataframe).
C est le parent du dossier pipeline (ou le parent du fichier YAML unique).

### Projet `.renatus.yaml` (F0043)

Quand on travaille via un **projet** GUI :

- le root projet (= dossier du `.renatus.yaml`) est le **depot git** ;
- le dossier **pipelines** doit etre **dans** ce root (YAML versionnes) ;
- `db_path` et les fichiers sources sont des **references** : ils peuvent
  pointer hors du projet (donnees privees, non versionnees).

Voir [GUI.md](GUI.md) pour le detail GUI / git.

## Types d etapes

Types du registry (F0053 + F0128) :

| Famille | Types |
|---------|--------|
| Datasets | `dataframe`, `table`, `view` |
| Execute | `execute_sql`, `execute_python` (session notebook F0136), `execute_shell` |
| Flow | `iterate`, `zone` |
| Auto | `flatzone`, `backzone`, `forzone`, `bidzone` (templates → zone, F0139) |

Alias legacy : `execute` → `execute_sql` ; `iteration` → `iterate`.

Convention de nommage recommandee (non imposee par le moteur) :

| Prefixe | Usage |
|---------|--------|
| `df_` | dataframe charge depuis un fichier |
| `t_` | table materialisee |
| `v_` | vue SQL |
| `x_` | execute_sql (INSERT, DELETE, maintenance) |
| `i_` | iterate |
| `bac_` / `for_` / `bid_` | auto-zones (reference objet) |

**Fichier monocomposant (F0101)** : le stem du fichier **est** l id
(`t_sales.yaml` contient la cle `t_sales`).

---

### dataframe

Charge un fichier tabulaire et l enregistre comme relation DuckDB
(session, catalogue temporaire pour le register).

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `type` | oui | doit valoir `dataframe` |
| `file` | oui | chemin relatif au project_dir (ex. `input/sales.csv`) |
| `mode` | non | `create_if_not_exists` (**defaut**, reutilise si deja register) ou `create_or_replace` (relecture source) |
| `name` | non | nom de relation en base (sinon label / id) |
| `label` | non | libelle UI |

Autres cles eventuelles sont passees a la lecture du fichier selon le format.

Formats supportes (suffixe) : `.csv`, `.tsv`, `.txt`, `.parquet`, `.json`,
`.xlsx`, `.xls` (Excel necessite openpyxl).

Exemple :

```yaml
df_sales:
  type: dataframe
  file: input/sales_mini.xlsx
  mode: create_if_not_exists
```

---

### table

Cree une table SQL materialisee.

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `type` | oui | `table` |
| `script` | oui | requete `SELECT` (alias legacy : `sql`) |
| `mode` | non | `create_if_not_exists` (defaut) ou `create_or_replace` |
| `requires` | non | liste d ids d etapes a materialiser avant |
| `name` | non | nom de la relation en base ; par defaut = id de l etape |

Exemple :

```yaml
t_eu:
  type: table
  mode: create_or_replace
  requires:
    - df_sales
  script: |
    SELECT * FROM df_sales
    WHERE region = 'EU'
    ORDER BY id
```

Relation renommee :

```yaml
t_people:
  type: table
  mode: create_or_replace
  name: people_master
  requires: []
  script: SELECT 1 AS id, 'alice' AS name
```

---

### view

Cree une vue SQL. Memes parametres que `table`, avec `type: view`.

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `type` | oui | `view` |
| `script` | oui | definition de la vue (alias legacy `sql`) |
| `mode` | non | `create_if_not_exists` ou `create_or_replace` |
| `requires` | non | dependances |
| `name` | non | nom de relation en base (sinon id de l etape) |

Exemple :

```yaml
v_products:
  type: view
  mode: create_or_replace
  requires:
    - t_sales
  sql: SELECT id, product, qty FROM t_sales ORDER BY id
```

---

### execute_sql

Execute du SQL sans creer de relation (INSERT, DELETE, UPDATE, DDL, etc.).
Ancien nom : `execute` (toujours accepte en entree, normalise en `execute_sql`).

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `type` | oui | `execute_sql` |
| `script` | oui | instruction(s) SQL a executer (legacy : `sql`) |
| `requires` | non | dependances a materialiser avant |

Exemple :

```yaml
x_drop_rows:
  type: execute_sql
  requires:
    - t_sales
  script: DELETE FROM t_sales WHERE id = 2
```

---

### iterate

Parcourt une table de scenarios. Pour chaque ligne :

1. cree une vue temporaire `step_view` (une ligne = scenario courant)
2. rejoue l etape `target` avec ses requires (set processed vide a chaque tour)

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `type` | oui | `iterate` |
| `scenarios` | oui | id de l etape (table/vue) listant les scenarios |
| `step_view` | oui | nom de la vue temporaire recree a chaque tour |
| `target` | oui | id de l etape a rejouer (souvent un `execute_sql`) |
| `execution` | non | `sequential` (defaut). `parallel` reserve a un gestionnaire dedie |
| `order_by` | non | liste de colonnes pour ordonner les scenarios |
| `requires` | non | dependances a preparer avant la boucle |

Important : `step_view` n est **pas** une etape du flux YAML. Elle est
creee dynamiquement. Ne la mettez pas dans `requires` (validation echoue).

La table de resultats d accumulation se declare en general en
`create_if_not_exists` pour ne pas etre videe entre les tours.

Exemple (schema simplifie) :

```yaml
t_scenarios:
  type: table
  mode: create_or_replace
  requires: []
  sql: |
    SELECT * FROM (VALUES ('EU'), ('US')) AS t(region)

t_results:
  type: table
  mode: create_if_not_exists
  requires: []
  sql: |
    SELECT CAST(NULL AS VARCHAR) AS region,
           CAST(NULL AS VARCHAR) AS product,
           CAST(NULL AS BIGINT) AS total_qty
    WHERE 1 = 0

x_agg:
  type: execute_sql
  requires:
    - t_sales
    - t_results
  script: |
    INSERT INTO t_results
    SELECT (SELECT region FROM v_step), product, SUM(qty)
    FROM t_sales
    WHERE region = (SELECT region FROM v_step)
    GROUP BY product

i_run:
  type: iterate
  execution: sequential
  requires:
    - t_scenarios
    - t_results
    - t_sales
  scenarios: t_scenarios
  step_view: v_step
  target: x_agg
  order_by:
    - region
```

Pour verifier la fin de parcours, on branche souvent une vue sur `t_results` :

```yaml
v_final:
  type: view
  mode: create_or_replace
  requires:
    - t_results
  sql: SELECT * FROM t_results ORDER BY region, product
```

---

### zone

Composant organisationnel (F0052 / F0056 / F0116) : dossier UI + membership.

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `type` | oui | `zone` |
| `label` | non | libelle UI |
| `objects` | non | `{ id_membre: {} }` (multi-zones possibles) |
| `workers` | non | `auto` \| `queue` \| `N` (lignes de flux) |
| `renatus_mode` | non | `required_for_leaves` \| `root_to_leaves` |

Layout : `flow/<zone>.yaml` + dossier `flow/<zone>/` (main : `flow/main.yaml` + `flow/main/`).

Build zone = Renatus des membres selon `renatus_mode` / `workers`.

### flatzone / backzone / forzone / bidzone (F0128 / F0139)

**Templates d initialisation** (palette Auto). A la creation : materialisent
une **zone physique** (`type: zone`) + copie des YAML des membres. Ensuite
comportement 100 % zone.

| Template | Params | Membership initiale (copie) |
|----------|--------|------------------------------|
| `flatzone` (ex `allzone`) | `parent` | feuilles recursives sous parent |
| `backzone` | `object` | requires recursifs |
| `forzone` | `object` | required_by recursifs |
| `bidzone` | `object` | amont + aval |

Legacy : YAML `allzone`/`backzone`… encore chargeables ; Convertir possible.

---

## Modes de creation

| Mode | Comportement |
|------|----------------|
| `create_if_not_exists` | Cree / register seulement si la relation n existe pas encore |
| `create_or_replace` | Recree / re-register a chaque process |

S applique a **dataframe**, **table**, **view**. Pour `execute_*` et `iterate`,
le moteur rejoue toujours. Les **auto-zones** n ont pas de mode : membership
toujours recalcule.

## Methodes principales (Python)

```python
from renatus.pipeline import ConnectionPipeline

cp = ConnectionPipeline("main.duckdb", "flow/")
try:
    cp.process_with_requires("t_eu")   # lineage + process
    cp.p_table_view("v_products")      # lineage + SELECT *
    rel = cp.table_view("v_products")  # SELECT sans lineage
    cp.p_iteration("i_run")
finally:
    cp.close()
```

| Methode | Role |
|---------|------|
| `process(name)` | Execute une etape seule (sans requires) |
| `process_with_requires(name)` | Cree les requires manquants puis process |
| `p_table_view(name)` | Lineage puis retourne le resultat tabulaire |
| `table_view(name)` | Lit une relation deja presente (erreur sinon) |
| `p_iteration(name)` | Prepare requires puis boucle sequential |
| `relation_exists(name)` | Table ou vue presente en base |
| `relation_name(name)` | Nom reel en base (`name` optionnel table/view) |

## Fichiers pipeline (F0101)

**Convention monocomposant** : un fichier `<id>.yaml` contient la cle `id`.
Le load pipeline force l id = stem pour les fichiers monocomposants.

```yaml
# flow/main/df_sales.yaml
df_sales:
  type: dataframe
  file: input/sales.csv
  mode: create_if_not_exists

# flow/main/t_sales.yaml
t_sales:
  type: table
  mode: create_or_replace
  requires:
    - df_sales
  script: SELECT * FROM df_sales
```

Les fichiers multi-cles (plusieurs etapes dans un seul YAML) restent supportes
en lecture ; le GUI et l import ecrivent en monocomposant.
