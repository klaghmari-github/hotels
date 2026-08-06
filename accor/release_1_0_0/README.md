# Accor ROD — release 1.0.0

Package reorganise : pipelines YAML, base DuckDB unique, services sim_v1 / sim_v2 / CatBoost, API et GUI.

## Arborescence

```
release_1_0_0/
  data/
    files/input/          # ventes, referentiels, brands
    files/output/         # eval LOO, predictions, extracts
      sim_v1/ sim_v2/ ml/ common/
    duckdb/
      main/main.duckdb    # base partagee sim_v1 + sim_v2 + ml
      workers/            # bases intermediaires parallelisation
  pipeline/
    common/               # (reserve)
    sim_v1/               # YAML R1–R4 + LOO
    sim_v2/               # YAML modelisation / restitution / LOO
    ml/                   # dataset ML
  src/
    pipeline/             # ConnectionPipeline, Paths
    sim_v1/ sim_v2/ ml/   # services metier
    api/                  # table_view, p_table_view, predict
    web/                  # GUI evaluation + prediction + hotels
  doc/                    # documentation HTML
  models/catboost/        # modeles .cbm
  run.py
```

## Usage

```bash
cd release_1_0_0
# depuis la racine release, avec le venv projet parent :
../.venv/bin/python run.py sim-v1 --rebuild
../.venv/bin/python run.py sim-v2 --rebuild
../.venv/bin/python run.py ml --rebuild
../.venv/bin/python run.py serve --port 5080
```

- UI : http://127.0.0.1:5080/
- Evaluation LOO : http://127.0.0.1:5080/eval
- Prediction : http://127.0.0.1:5080/predict
- Hotels : http://127.0.0.1:5080/hotels

## API (extraits)

| Methode | Route | Role |
|---------|-------|------|
| GET | `/api/health` | sante |
| GET | `/api/tables/<name>` | table/vue existante |
| GET | `/api/p_tables/<name>` | construit via pipeline puis lit |
| GET | `/api/hotels` | hotels pilotes |
| GET | `/api/eval/sim_v1` · `sim_v2` · `ml` | resultats LOO Excel |
| POST | `/api/predict/sim_v1` · `sim_v2` · `ml` | prediction |

## ML

CatBoost uniquement (pas XGBoost, pas reseau). LOO hotel + export `data/files/output/ml/eval_catboost_loo.xlsx`.

## Note

La base `main.duckdb` est initialisee a partir du dataset sim_v2 deja calcule.  
Les tables sim_v1 se rajoutent dans la meme base. Reconstruire le catalogue scenarios complet reste un job pipeline sim_v2 long (hors GUI).
