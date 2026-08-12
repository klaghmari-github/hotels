# renatus API HTTP

Service REST JSON (FastAPI + uvicorn) autour du meme moteur que le CLI.

## Demarrage

```bash
pip install -e .
renatus-api <db.duckdb> <flow_dir> [--host 127.0.0.1] [--port 8000]
# equivalent : python -m renatus.api ...
```

| Parametre | Obligatoire | Role |
|-----------|-------------|------|
| `db_path` | oui | Fichier DuckDB |
| `flow_path` | oui | Dossier ou fichier YAML |
| `--host` | non | Defaut `127.0.0.1` |
| `--port` | non | Defaut `8000` (auto si occupe selon serveur) |
| `--read-only` | non | Base en lecture seule |
| `--max-rows` | non | Plafond de lignes serialisees (defaut serveur) |

Une connexion DuckDB par process. Les appels sont serialises. Preferer un
seul worker uvicorn.

## Format de reponse

Succes : objet JSON avec au minimum `"ok": true`.

Erreur : `"ok": false`, `"error"` et `"detail"` (message), code HTTP :

| Code | Cas typique |
|------|-------------|
| 400 | Type / valeur invalide |
| 404 | Etape ou relation absente |
| 500 | Erreur interne |

## Endpoints

### Sante

`GET /health`

Sans parametre. Retourne l etat du service et les chemins configures.

```bash
curl -s http://127.0.0.1:8000/health
```

### Pipeline

| Methode | Chemin | Role |
|---------|--------|------|
| GET | `/pipeline` | Liste des etapes (nom, type, requires, mode) |
| GET | `/pipeline/steps` | Alias de `/pipeline` |
| GET | `/pipeline/{name}` | Detail de la config YAML d une etape |

Parametre de chemin `name` : obligatoire, id d etape.

```bash
curl -s http://127.0.0.1:8000/pipeline
curl -s http://127.0.0.1:8000/pipeline/t_sales
```

### Relations

| Methode | Chemin | Role |
|---------|--------|------|
| GET | `/relations/{name}` | Existence et kind (`table` / `view`) |
| GET | `/relations/{name}/exists` | Alias existence |

```bash
curl -s http://127.0.0.1:8000/relations/t_sales
```

### Lecture tabulaire

| Methode | Chemin | Role |
|---------|--------|------|
| POST | `/p_table_view/{name}` | Lineage puis SELECT * en JSON |
| GET | `/p_table_view/{name}` | Idem en GET |
| GET | `/table_view/{name}` | SELECT sans lineage (404 si absent) |

Query optionnelle :

| Query | Obligatoire | Role |
|-------|-------------|------|
| `limit` | non | Nombre max de lignes retournees |
| `max_rows` | non | Alias / plafond alternatif |

`limit` prime sur `max_rows` s ils sont tous deux fournis.

```bash
curl -s -X POST 'http://127.0.0.1:8000/p_table_view/v_sales?limit=50'
curl -s 'http://127.0.0.1:8000/table_view/v_sales?max_rows=10'
```

Reponse type (extrait) : `columns`, `rows`, `row_count`, `truncated`, `limit`.

### Execution

| Methode | Chemin | Role |
|---------|--------|------|
| POST | `/process/{name}` | process simple |
| POST | `/process_with_requires/{name}` | process + requires |
| POST | `/p_iteration/{name}` | iteration sequential |

```bash
curl -s -X POST http://127.0.0.1:8000/process_with_requires/x_drop_rows
curl -s -X POST http://127.0.0.1:8000/p_iteration/i_run
```

## Exemple de session

```bash
# Materialiser une table et lire 3 lignes
curl -s -X POST 'http://127.0.0.1:8000/p_table_view/t_sales?limit=3'

# Controler qu une relation existe
curl -s http://127.0.0.1:8000/relations/t_sales/exists
```

La description des etapes YAML (parametres `type`, `sql`, `requires`, etc.)
est dans [CORE.md](CORE.md).
