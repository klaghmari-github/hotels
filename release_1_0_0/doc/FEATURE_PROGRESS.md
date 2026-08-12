# Feature — Barre de progression reelle (operations longues)

## Objectif

Les operations lentes (estimation du meilleur mix, optimisation) doivent
afficher une **barre de progression reelle**, pas un simple spinner
indetermine, pour que l’utilisateur voie l’avancement.

## Architecture

```
UI  ──POST /api/user/jobs/optimize──►  cree job + thread worker
UI  ──GET  /api/user/jobs/<id> ─────►  { pct, done, total, message, status }
worker ──progress_cb(done,total,msg)──►  JobStore (memoire process)
worker ──complete(result) ───────────►  status=done + result
```

## API

| Methode | Route | Role |
|---------|-------|------|
| POST | `/api/user/jobs/optimize` | Demarre le calcul (product_rank ou grid) |
| GET | `/api/user/jobs/<job_id>` | Etat + `pct` + `message` + `result` si done |
| POST | `/api/user/optimize` | Version **synchrone** (compat, sans progress) |

Reponse job (extrait) :

```json
{
  "ok": true,
  "job_id": "a1b2c3d4e5f6",
  "status": "running",
  "done": 3,
  "total": 7,
  "pct": 42.9,
  "message": "Estimation CA (sim_v1 / sim_v2 / ml) — mix SIMPLY (3/7)…"
}
```

`status` : `pending` | `running` | `done` | `error`.

## Etapes reelles (product_rank)

1. Preparation des vues assortiment  
2. Pour chaque solution (SIMPLY / LIBERTY / CONNECTED) : calcul top produits / mix  
3. Pour chaque mix obtenu : evaluation CA sim_v1 + sim_v2 + ml  

`total ≈ 1 + 2 × n_solutions` (recalibré si un assortiment échoue).

## UI

- `runJobWithProgress(startUrl, payload, host)` — poll ~400 ms  
- Barre CSS `.progress-wrap` / `.progress-fill`  
- Utilisee par :
  - **Estimer le meilleur mix + CA** (`runSim`)
  - **Lancer l’optimisation** (`runOptimize`)

## Code

| Fichier | Role |
|---------|------|
| `src/user/jobs.py` | `JobStore` + `JobState` |
| `src/user/optimize.py` | `progress_cb` dans product_rank / grid |
| `src/api/app.py` | routes jobs |
| `src/web/pages_user.py` | barre + poll |

## Extension

Toute operation longue doit :

1. creer un job (`JOB_STORE.create`)  
2. passer `progress_cb` aux etapes metier  
3. exposer start + poll  
4. brancher `runJobWithProgress` cote UI  
