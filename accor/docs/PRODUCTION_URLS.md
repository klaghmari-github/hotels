# Accor ROD — URLs (client + console dev)

Deux contextes distincts :

1. **Production client** — VPS DigitalOcean (stable, PM2 + Apache SSL)
2. **Console agent / lab** — machine de dev + tunnels Cloudflare gratuits  
   (watchdog permanent : `run_dev` + admin + user + consignes)

Les URL Cloudflare **changent** si les tunnels redémarrent.  
Source de vérité live : en-tête de [`accor/README.md`](../README.md)  
(`run_dev url`, `run_admin url`, `run_user url`).

---

## A. Production client (serveur `accor-ia`)

| Application | Rôle | URL |
|-------------|------|-----|
| **User** | Simulateur directeur | **https://rod-ia.adixon-dev.fr/** |
| **Admin** | Data & Model Studio | **https://rod-ia.adixon-dev.fr/studio/** |

- Host : `178.62.220.14` · SSH `adixon@…`
- PM2 : `rod-ia-user` (:8000), `rod-ia-admin` (:8001, préfixe `/studio`)
- README serveur : `/var/www/rod-ia/README.md`

```bash
ssh adixon@178.62.220.14
export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH"
pm2 status && pm2 restart all
```

---

## B. Console de communication avec l’agent (tunnels gratuits)

| Service | Port local | Rôle |
|---------|------------|------|
| **run_dev** | 5500 | Chat / consignes vers Grok (`/api/chat`) |
| **run_admin** | 5055 | Studio admin (lab) |
| **run_user** | 5056 | Simulateur user (lab) |

Maintien **permanent** : `scripts/dev_watchdog.py` (ne pas tuer).  
Intervalle 60 s : health-check, restart si DOWN, re-expose Cloudflare, maj README.

```bash
# Démarrage (une fois)
cd accor
nohup python3 scripts/dev_watchdog.py >> /tmp/accor-dev-watchdog.log 2>&1 &
echo $! > data/dev_console/watchdog.pid
```

### Consignes à distance

1. **Chat web** sur l’URL publique `run_dev` (console Grok Dev)
2. **Watchdog inbox** dans le README :

```text
## Watchdog inbox
watchdog> status
watchdog> restart dev
watchdog> reexpose all
watchdog> note: message libre pour l’agent
```

Logs : `/tmp/accor-dev-watchdog.log`, `/tmp/accor-run-dev.log`

---

## C. Séparation des responsabilités

| | Client (prod) | Lab / agent |
|--|---------------|-------------|
| But | Démo / usage métier | Travailler avec Grok à distance |
| Infra | DO + Apache SSL | Cloudflare quick tunnels |
| Données | copie déployée | workspace local `accor/` |
| Ne pas confondre | ne pas y brancher le watchdog | ne pas y mettre le client final |