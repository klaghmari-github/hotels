# Synchronisation local → Adixon (release_1_0_0)

## Règle d’or

| Action | Quand |
|--------|--------|
| Travail / commits / push GitHub | libre, au fil de l’eau |
| **Déploiement Adixon** | **uniquement** sur consigne explicite (« déploie sur Adixon ») |

Source de vérité **code** = machine locale (`release_1_0_0/`).  
On n’édite pas `src/`, `pipeline/`, `static/` à la main sur le VPS.

```
Local (release_1_0_0/)  ──./scripts/deploy_to_adixon.sh──►  Adixon
                                                              /var/www/rod-ia
                                                              https://rod-ia.adixon-dev.fr
```

## Cible

| Item | Valeur |
|------|--------|
| SSH | `adixon@178.62.220.14` |
| Répertoire | `/var/www/rod-ia` |
| Public | https://rod-ia.adixon-dev.fr |
| User | `/user` |
| Admin | `/admin` (auth) |
| Legacy | `/studio` → redirect `/admin` (PM2 `rod-ia-admin` :8001) |
| App Flask | PM2 `rod-ia-user` → `run.py serve` :8000 |

## Commandes

Depuis la racine **release_1_0_0/** :

```bash
./scripts/deploy_to_adixon.sh           # code + static + doc + scripts + reload PM2
./scripts/deploy_to_adixon.sh --deps    # + pip install -r requirements.txt
./scripts/deploy_to_adixon.sh --data    # + data/files (input/output, hors _raw_sources)
./scripts/deploy_to_adixon.sh --duckdb  # + data/duckdb (main.duckdb)
./scripts/deploy_to_adixon.sh --models  # + models/ (super + legacy)
./scripts/deploy_to_adixon.sh --raw     # + _raw_sources (lourd)
./scripts/deploy_to_adixon.sh --auth    # + data/auth (secrets / comptes)
./scripts/deploy_to_adixon.sh --all     # code + deps + data + duckdb + models
./scripts/deploy_to_adixon.sh --dry-run # simulation rsync
```

Variables optionnelles :

```bash
export ADIXON_HOST=adixon@178.62.220.14
export ADIXON_REMOTE=/var/www/rod-ia
```

## Ce qui est synchronisé (défaut)

| Local | Serveur `/var/www/rod-ia/` |
|-------|----------------------------|
| `src/` | ✓ |
| `pipeline/` | ✓ |
| `static/` | ✓ |
| `doc/` | ✓ |
| `scripts/` (dont `studio_redirect.py`, ce script) | ✓ |
| `run.py`, `requirements.txt`, `ecosystem.config.js` | ✓ |
| `RELEASE.txt` (stamp git + date) | ✓ |

## Ce qui n’est **pas** écrasé (sauf flag)

| Sur le serveur | Flag pour forcer |
|----------------|------------------|
| `data/` (fichiers métier) | `--data` |
| `data/duckdb/` | `--duckdb` |
| `models/` | `--models` |
| `data/auth/` (secrets) | `--auth` |
| `data/files/input/_raw_sources/` | `--raw` (ou `--data --raw`) |
| `.venv/` | `--deps` réinstalle les paquets |

## Premier déploiement (install complète)

Une fois, après préparation serveur (venv, logs, Apache déjà en place) :

```bash
cd release_1_0_0
./scripts/deploy_to_adixon.sh --all
```

Puis smoke navigateur :

- https://rod-ia.adixon-dev.fr/
- https://rod-ia.adixon-dev.fr/user
- https://rod-ia.adixon-dev.fr/admin
- https://rod-ia.adixon-dev.fr/studio/ → doit rediriger vers `/admin`

## Mises à jour courantes (code only)

```bash
./scripts/deploy_to_adixon.sh
# si requirements.txt a changé :
./scripts/deploy_to_adixon.sh --deps
# si modèles re-entraînés :
./scripts/deploy_to_adixon.sh --models
```

## PM2 (référence)

Fichier local : `ecosystem.config.js`

| Process | Port | Script |
|---------|------|--------|
| `rod-ia-user` | 8000 | `run.py serve --host 127.0.0.1 --port 8000` |
| `rod-ia-admin` | 8001 | `scripts/studio_redirect.py` (compat Apache `/studio`) |

Logs : `/var/log/rod-ia/*.log`

## Voir aussi

- [ARCHITECTURE.md](ARCHITECTURE.md) — couches package
- `ecosystem.config.js` — config PM2
- `scripts/deploy_to_adixon.sh` — script source
