# Console web de gestion (hors produit renatus)

Interface web pour envoyer des demandes (feature / anomalie / question) depuis
n'importe ou (telephone). Le **worker local** sur ce PC :

1. recoit la file d'attente
2. inscrit dans `features.csv` / `anomalies.csv` / `questions_reponses_.csv`
3. remonte un **statut toutes les 60s** (pensee courante, restants)

## Demarrage

```bash
cd gestion_projet/web_console
./start.sh
```

Le script affiche l'URL Cloudflare (`https://….trycloudflare.com`).

## Arret

```bash
./stop.sh
```

## Donnees

| chemin | role |
|--------|------|
| `agentic/web_console/messages.json` | chat |
| `agentic/web_console/queue.json` | file |
| `agentic/web_console/status.json` | heartbeat |
| `logs/web_console/` | logs api/worker/tunnel |

Ne modifie **pas** `src/renatus/`.
