# Modifications apportées au projet **renatus**

Document à part (demande métier hotels) listant **uniquement** les changements
faits dans le dépôt `renatus/` pour permettre le flux `hotels_renatus`.

## Contexte

Le moteur renatus exécute des steps YAML (SQL / Python) sur DuckDB.  
Le projet consommateur `hotels_renatus` a besoin, pour l’étape **estimate_ml**,
d’un script Python qui **lit et écrit la même base DuckDB** que le pipeline
(features déjà matérialisées en SQL, scores modèles en table).

Or `execute_python` lançait un sous-processus **sans** indiquer le chemin de la base.

## Changements

### 1. Injection d’environnement dans `execute_python`

**Fichiers :**

- `src/renatus/pipeline/steps/python_action.py`
- `src/renatus/pipeline/engine.py` (`get_python_kernel(..., env=)`)

**Comportement ajouté :**

Avant d’exécuter un script `execute_python`, renatus renseigne :

| Variable | Contenu |
|----------|---------|
| `RENATUS_DB_PATH` | Chemin absolu du fichier DuckDB du pipeline |
| `RENATUS_PROJECT_DIR` | Répertoire projet (cwd scripts) |
| `RENATUS_FLOW_PATH` | Chemin du flow (si disponible) |

Le noyau de session (F0136) reçoit le même `env` à la création.

**Objectif :** permettre aux scripts métier d’ouvrir la base avec  
`duckdb.connect(os.environ["RENATUS_DB_PATH"])` sans hardcoder le chemin  
et sans casser l’isolation du sous-processus Python.

### 2. Non modifié

- Pas de changement du format YAML des steps  
- Pas de changement CLI oneshot/REPL (hors usage existant)  
- Pas de changement du protocole noyau JSON  

## Impact / compatibilité

- Scripts Python existants **ignorent** ces variables → comportement inchangé.  
- Nouveaux scripts (hotels) peuvent s’y appuyer.

## Référence usage hotels

Voir `hotels_renatus/flow/estimate_ml/x_estimate_ml_score.yaml`  
et `hotels_renatus/README.md`.
