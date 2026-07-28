# Synchronisation local ↔ Adixon (prod client)

## Circuit de travail (à partir de maintenant)

```
Toi  ──consignes──►  Console Cloudflare (run_dev LOCAL uniquement)
                              │
                              ▼
                     Agent applique en LOCAL (accor/)
                              │
                              ▼
                     ./scripts/deploy_to_adixon.sh
                              │
                              ▼
                     Prod client Adixon (PAS de Cloudflare)
```

| Environnement | Rôle | Cloudflare ? |
|---------------|------|--------------|
| **Local + run_dev** | consignes / chat avec l’agent | **Oui** (tunnels gratuits) |
| **Local admin/user** | tests lab | Oui (tunnels lab) |
| **Adixon VPS** | prod client | **Non** — Apache SSL direct |

**Cloudflare = uniquement lab local.**  
**Adixon = déploiement depuis le local** (`deploy_to_adixon.sh`), jamais de tunnel CF dessus.

## Règle d’or

1. **Consignes** via l’URL publique `run_dev` (Cloudflare local).
2. **Modifs uniquement en LOCAL** (`accor/`).
3. **Déploiement Adixon** avec le script (pas d’édition manuelle sur le VPS).
4. **Source de vérité code = local.**  
   Sur le serveur on ne touche pas à `src/`, `static/`, `templates/` à la main.

Cela évite les conflits de version entre ta machine et `adixon@178.62.220.14`.

## Commande

```bash
cd accor
./scripts/deploy_to_adixon.sh           # code + front + restart PM2
./scripts/deploy_to_adixon.sh --deps    # si pyproject / requirements changent
./scripts/deploy_to_adixon.sh --data    # si les Excel/JSON data changent
./scripts/deploy_to_adixon.sh --models  # si les modèles .pkl changent
./scripts/deploy_to_adixon.sh --all     # tout
./scripts/deploy_to_adixon.sh --dry-run # simulation
```

## Ce qui est synchronisé

| Local | Serveur `/var/www/rod-ia/` |
|-------|----------------------------|
| `src/accor/` | ✓ |
| `static/` | ✓ |
| `templates/` | ✓ |
| `run_user.py`, `run_admin.py` | ✓ |
| `pyproject.toml`, `requirements.txt` | ✓ |

## Ce qui n’est **pas** écrasé (sauf flag)

| Sur le serveur | Raison |
|----------------|--------|
| `data/` | données runtime prod (`--data` pour forcer) |
| `models/` | modèles déployés (`--models` pour forcer) |
| `.venv/` | env Python serveur (`--deps` réinstalle) |
| `ecosystem.config.js` | ports PM2 / env prod |

## Après chaque demande de modification

L’agent (ou toi) doit :

1. Appliquer le patch **en local**
2. Vérifier si besoin en lab (`run_admin` / `run_user` local)
3. Lancer `./scripts/deploy_to_adixon.sh` (éventuellement avec flags)
4. Contrôler :
   - https://rod-ia.adixon-dev.fr/
   - https://rod-ia.adixon-dev.fr/studio/

## Lab (tunnels Cloudflare) ≠ Adixon

| Environnement | Rôle |
|---------------|------|
| Local + watchdog + Cloudflare | travail avec l’agent, tests |
| Adixon (VPS client) | prod client, toujours = dernier deploy local |

Le watchdog **ne déploie pas** sur Adixon. Seul `deploy_to_adixon.sh` le fait.
