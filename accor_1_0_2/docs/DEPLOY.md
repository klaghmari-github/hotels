# Plan de déploiement — Accor ROD (app user / simulateur directeur)

> **Statut** : plan de préparation uniquement.  
> **Ne pas exécuter** ce document comme un runbook « live » sans validation go/no-go (section 13).  
> Aucun secret (mot de passe sudo, clés privées) ne doit figurer dans ce fichier ni dans le dépôt.

| Champ | Valeur |
|-------|--------|
| Cible | `https://rod-ia.adixon-dev.fr` |
| Serveur | VPS DigitalOcean — `178.62.220.14` |
| SSH | `adixon@178.62.220.14` (clé publique déjà installée) |
| App déployée | **user only** (`run_user.py` → `accor.user.app`) |
| Remplace | placeholder Python PM2 `rod-ia` sur le port **8000** |
| Mode livraison | **packages / archives versionnées** (+ data/models séparés) |

---

## 1. Objectif & non-objectifs

### Objectif

Remplacer le placeholder HTTP « Hello » géré par PM2 sur `127.0.0.1:8000` par l’application Flask **simulateur directeur (user)** Accor ROD, derrière le reverse-proxy Apache + SSL déjà en place, de façon **reproductible** via archives versionnées.

### Non-objectifs (hors périmètre de ce plan)

| Exclu | Raison |
|-------|--------|
| Exécution immédiate du déploiement | Document de préparation uniquement |
| Déploiement de l’**admin** (`run_admin.py` :5055) | Vhost prod = user-only |
| `run_dev` / watchdog / tunnels Cloudflare | Outils de dev local |
| `git clone` live sur le serveur | Préférence client : packages versionnés |
| `rsync` chaotique du monorepo | Risque de pollution (dev_console, caches, secrets) |
| Modification Apache SSL / DNS | Déjà opérationnels |
| Commit de secrets dans le repo | Interdit |

---

## 2. Compréhension de l’infra client (validée SSH)

Inspection réalisée sur le VPS. Synthèse factuelle.

### 2.1 Machine

| Item | Constat |
|------|---------|
| Hostname | `accor-ia` |
| OS | Ubuntu, kernel `6.8.0-136-generic` x86_64 |
| RAM | **~1,9 GiB** |
| Swap | **0** → risque OOM (pandas / xgboost / Flask) |
| Disque | 58 G total, ~3,5 G utilisés, **~54 G libres** |
| CPU | 2 vCPU |
| Compte app | `adixon` (groupe sudo) |
| Sudo | **mot de passe requis** (pas de `NOPASSWD`) — fourni hors doc |

### 2.2 Réseau / reverse-proxy Apache

| Item | Constat |
|------|---------|
| Apache | 2.4.58 |
| Site enabled | `rod-ia.adipos-dev.fr.conf` (**nom fichier** `adipos` vs domaine `adixon` — cosmétique) |
| `ServerName` | `rod-ia.adixon-dev.fr` |
| SSL | Let’s Encrypt : `/etc/letsencrypt/live/adixon-dev.fr/{fullchain,privkey}.pem` |
| Proxy | `ProxyPass /` → `http://127.0.0.1:8000/` (`ProxyPreserveHost On`) |
| Modules | `proxy`, `proxy_http`, `ssl`, `headers` |
| HTTP :80 | redirect 302 → HTTPS |
| Santé | HTTPS public **200** ; HTTP local `:8000` **200** (placeholder) |

### 2.3 Process management (PM2)

| Item | Constat |
|------|---------|
| PM2 | v7.0.3 via nvm Node **v22.23.1** |
| Binaire | `/home/adixon/.nvm/versions/node/v22.23.1/bin/pm2` |
| Survivance reboot | unit systemd `pm2-adixon.service` (**active**) |
| App | name `rod-ia`, cwd `/var/www/rod-ia`, script `server.py` |
| Interpréteur actuel | `/usr/bin/python3` (système) |
| Port | **8000** |
| Logs | `/var/log/rod-ia/rod-ia.{out,error}.log` |
| Contenu actuel | uniquement `server.py` (Hello HTTPServer) + `ecosystem.config.js` |

### 2.4 Python serveur — lacunes critiques

| Item | Constat | Action requise |
|------|---------|----------------|
| Python | 3.12.3 système | OK (≥ 3.10) |
| `pip` | **absent** (`python3 -m pip` échoue) | Installer |
| `python3-venv` | **non installé** (dpkg *un*) | Installer |
| `build-essential` | présent | OK (compil xgboost si besoin) |
| `libgomp1` | présent | OK (OpenMP / xgboost) |

Commande OS prévue (sudo + mot de passe interactif) :

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
```

---

## 3. Architecture cible

```
Internet
   │
   ▼
Apache 2.4 (HTTPS :443, ServerName rod-ia.adixon-dev.fr)
   │  ProxyPass / → http://127.0.0.1:8000/
   │  SSL Let's Encrypt (adixon-dev.fr)
   ▼
127.0.0.1:8000  ← bind loopback uniquement (recommandé)
   │
   ▼
PM2 app « rod-ia »
   │  interpreter = /var/www/rod-ia/.venv/bin/python
   │  script      = run_user.py
   │  env         = ACCOR_HOST, ACCOR_PORT, PYTHONUNBUFFERED
   ▼
Flask user (accor.user.app) — simulateur directeur
   │
   ├── data/     (Excel/JSON + logos marques)
   ├── models/   (final + intermédiaire stacking)
   ├── static/   templates/
   └── src/accor/
```

### Principes

1. **Apache** reste le seul point d’entrée public (TLS + reverse-proxy).
2. **Flask** écoute en **loopback** (`127.0.0.1:8000`) — ne pas exposer 8000 sur `0.0.0.0` en prod.
3. **Admin** non déployé / non proxifié sur ce vhost.
4. Chemins runtime résolus via `accor.data_io` :
   - `PACKAGE_DIR` = `src/accor/`
   - `PROJECT_ROOT` = `PACKAGE_DIR.parent.parent` → **racine `/var/www/rod-ia`**
   - Donc `data/`, `models/`, `static/`, `templates/` **doivent** être frères de `src/` sous `/var/www/rod-ia/`.

### Layout prod obligatoire

```text
/var/www/rod-ia/
├── src/accor/…              # code package
├── data/                    # runtime data (séparé du package code)
├── models/                  # modèles ML (séparé)
├── static/
├── templates/
├── run_user.py
├── pyproject.toml
├── requirements.txt
├── .venv/                   # créé sur le serveur
├── ecosystem.config.js      # PM2
└── RELEASE.txt              # version / checksums (recommandé)
```

---

## 4. Inventaire requis

### 4.1 Code applicatif (package versionné)

| Élément | Rôle |
|---------|------|
| `src/accor/` | Package Python |
| `run_user.py` | Entrée process PM2 |
| `pyproject.toml` | Métadonnées + deps + entry points |
| `requirements.txt` | Fallback install |
| `static/`, `templates/` | Assets UI user (+ shared) |
| `ecosystem.config.js` | Config PM2 (généré ou fourni dans le package) |

### 4.2 Data runtime (tarball séparé, ~31 Mo)

**Critiques user (MVP)** :

| Fichier / dossier | Usage |
|-------------------|--------|
| `hotel_data.xlsx` | Fiches hôtels, autocomplete, contexte |
| `hotel_brand_data.xlsx` | Marques / logos UI |
| `model_data.xlsx` + `model_data_meta.json` | Agrégats, défauts, features IA |
| `rod_reference.json` | Concepts, coûts, pivots ROD |
| `concept_pilote.xlsx` | Moyennes pilote étape 1 |
| `hotel_sales_data.xlsx` | Historique ventes (contexte) |
| `marques/**` | PNG logos par catégorie |

**Utile / enrichissement (recommandé MVP+)** :

| Fichier | Usage |
|---------|--------|
| `hotel_weather_data.xlsx` | Enrichissement météo |
| `hotel_holidays_data.xlsx` | Calendrier / fériés |
| `hotel_proximity_data.xlsx` | Proximité commerces |
| `hotel_sales_raw_data.xlsx` | Raw caisse (si rebuild sales) |
| `couts.xlsx` | Barèmes coûts (complément ref) |

**À exclure du runtime prod** :

- `data/dev_console/` (logs/pid/tunnels locaux)
- caches, fichiers temporaires de dev

### 4.3 Models (tarball séparé)

L’IA directeur (`user.services.director`) charge le **modèle final** (stacking) et l’**intermédiaire** référencé.

État local de référence (à la rédaction) :

| Chemin | Rôle |
|--------|------|
| `models/final/last_trained.json` | Pointeur top final (`xgb_final_gs_008`) |
| `models/final/design/xgb_final_gs_008/` | Bundle final (`model.pkl`, `config.json`) |
| `models/design/xgb_sales_1_gs_003/` | Intermédiaire stacking (`intermediate_model_id`) |
| `models/deploy/` | Optionnel (~6 Mo) — bundle « deploy » si utilisé ailleurs |
| Autres `design/*` | Non nécessaires au MVP user si non référencés |

**Minimum viable models** :

```text
models/
  final/
    last_trained.json
    design/xgb_final_gs_008/{model.pkl,config.json}
  design/
    xgb_sales_1_gs_003/{model.pkl,config.json}   # id lu dans config final
```

> Vérifier toujours `intermediate_model_id` dans le `config.json` du top final avant packaging.

### 4.4 Paquets OS serveur

```bash
sudo apt install -y python3-venv python3-pip
# déjà présents : build-essential, libgomp1
```

### 4.5 Dépendances Python (pyproject / requirements)

```
flask>=3.0
pandas>=2.0
openpyxl>=3.1
numpy>=1.24
requests>=2.31
meteostat>=1.6
scikit-learn>=1.3
xgboost>=2.0
```

Install recommandée sur le serveur :

```bash
pip install -r requirements.txt && pip install -e .
# ou
pip install -e .
```

---

## 5. Contenu des packages (manifestes)

Stratégie : **2 (ou 3) archives** + checksums SHA256. Jamais data/models dans le tarball code.

### 5.1 Package code — `accor-rod-user-<version>.tar.gz`

Exemple : `accor-rod-user-1.0.0.tar.gz`

**Include** :

```text
run_user.py
pyproject.toml
requirements.txt
src/accor/          # sans __pycache__, sans *.pyc
static/             # css/js/img user + shared (+ admin assets inoffensifs si présents)
templates/          # au minimum templates/user/ + partials nécessaires
ecosystem.config.js # template prod (voir §8)
RELEASE.txt         # version, date, git sha optionnel, liste checksums data/models
```

**Exclude** :

```text
.git/
.gitignore
data/                 # → package runtime séparé
models/               # → package runtime séparé
.venv/
**/__pycache__/
**/*.pyc
**/*.egg-info/
data/dev_console/
bin/cloudflared
scripts/dev_watchdog.py
scripts/expose_public.sh
run_admin.py          # optionnel : peut rester dans le tarball mais non lancé
run_dev.py
docs/                 # optionnel
README.md             # optionnel
*.log
.pytest_cache/
.mypy_cache/
```

### 5.2 Package data — `accor-rod-runtime-data-<YYYYMMDD>.tar.gz`

Racine d’extraction = `data/` sous `PROJECT_ROOT`.

**Include (MVP)** : fichiers listés §4.2 critiques + `marques/`.  
**Exclude** : `dev_console/`, fichiers `*~`, `.DS_Store`.

### 5.3 Package models — `accor-rod-runtime-models-<YYYYMMDD>.tar.gz`

Racine d’extraction = `models/` sous `PROJECT_ROOT`.

**Include (MVP)** : final top + intermédiaire stacking + `last_trained.json`.  
**Option** : archive unique `accor-rod-runtime-data-models-<date>.tar.gz` si plus simple pour le client.

### 5.4 Checksums

Pour chaque archive :

```bash
sha256sum accor-rod-user-1.0.0.tar.gz > accor-rod-user-1.0.0.tar.gz.sha256
sha256sum accor-rod-runtime-data-YYYYMMDD.tar.gz > accor-rod-runtime-data-YYYYMMDD.tar.gz.sha256
sha256sum accor-rod-runtime-models-YYYYMMDD.tar.gz > accor-rod-runtime-models-YYYYMMDD.tar.gz.sha256
```

Livrer les `.sha256` avec les archives (upload scp / partage sécurisé).

---

## 6. Procédure de build package (machine locale)

À exécuter depuis la racine projet `accor/` (workspace de build), **pas sur le VPS**.

### 6.1 Pré-requis build

- Arborescence complète locale (code + data + models validés)
- `tar`, `sha256sum`, bash
- Version sémantique décidée (ex. `1.0.0`)

### 6.2 Script prévu : `scripts/build_release_package.sh`

À créer avant le premier déploiement réel (hors scope d’exécution de ce plan). Comportement attendu :

```bash
./scripts/build_release_package.sh 1.0.0
# → dist/accor-rod-user-1.0.0.tar.gz
# → dist/accor-rod-runtime-data-YYYYMMDD.tar.gz
# → dist/accor-rod-runtime-models-YYYYMMDD.tar.gz
# → dist/*.sha256
# → dist/RELEASE-1.0.0.txt
```

### 6.3 Commandes manuelles de référence (sans script)

```bash
cd /media/laghmari/ssd-data/dev/hotels/accor
VERSION=1.0.0
DATE=$(date +%Y%m%d)
mkdir -p dist/staging-code

# --- CODE ---
rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.egg-info' \
  src/accor/ dist/staging-code/src/accor/

rsync -a static/ templates/ dist/staging-code/
cp run_user.py pyproject.toml requirements.txt dist/staging-code/

# ecosystem prod (si généré ici ; sinon copier template §8)
# cp path/to/ecosystem.config.js dist/staging-code/

printf 'version=%s\nbuilt_at=%s\napp=accor-rod-user\n' \
  "$VERSION" "$(date -Iseconds)" > dist/staging-code/RELEASE.txt

tar -C dist/staging-code -czf "dist/accor-rod-user-${VERSION}.tar.gz" .
sha256sum "dist/accor-rod-user-${VERSION}.tar.gz" \
  | tee "dist/accor-rod-user-${VERSION}.tar.gz.sha256"

# --- DATA ---
tar -C data -czf "dist/accor-rod-runtime-data-${DATE}.tar.gz" \
  --exclude 'dev_console' \
  --exclude '__pycache__' \
  hotel_data.xlsx \
  hotel_brand_data.xlsx \
  model_data.xlsx \
  model_data_meta.json \
  rod_reference.json \
  concept_pilote.xlsx \
  hotel_sales_data.xlsx \
  hotel_weather_data.xlsx \
  hotel_holidays_data.xlsx \
  hotel_proximity_data.xlsx \
  couts.xlsx \
  marques
sha256sum "dist/accor-rod-runtime-data-${DATE}.tar.gz" \
  | tee "dist/accor-rod-runtime-data-${DATE}.tar.gz.sha256"

# --- MODELS (MVP : final top + intermédiaire) ---
# Ajuster les slugs selon last_trained.json + config intermediate_model_id
tar -C models -czf "dist/accor-rod-runtime-models-${DATE}.tar.gz" \
  final/last_trained.json \
  final/design/xgb_final_gs_008 \
  design/xgb_sales_1_gs_003
sha256sum "dist/accor-rod-runtime-models-${DATE}.tar.gz" \
  | tee "dist/accor-rod-runtime-models-${DATE}.tar.gz.sha256"
```

### 6.4 Transfert vers le serveur

```bash
# depuis la machine de build
scp dist/accor-rod-user-1.0.0.tar.gz \
    dist/accor-rod-user-1.0.0.tar.gz.sha256 \
    dist/accor-rod-runtime-data-YYYYMMDD.tar.gz \
    dist/accor-rod-runtime-data-YYYYMMDD.tar.gz.sha256 \
    dist/accor-rod-runtime-models-YYYYMMDD.tar.gz \
    dist/accor-rod-runtime-models-YYYYMMDD.tar.gz.sha256 \
    adixon@178.62.220.14:~/releases/
```

Répertoire recommandé côté serveur : `~/releases/` (staging avant extraction vers `/var/www/rod-ia`).

---

## 7. Procédure d’install sur le serveur (pas-à-pas)

> Toutes les commandes ci-dessous sont **à exécuter au moment du déploiement réel**, après go/no-go.  
> SSH : `ssh adixon@178.62.220.14`

### 7.0 Préparation (une fois)

```bash
# 1) Paquets Python manquants
sudo apt update
sudo apt install -y python3-venv python3-pip

# 2) (Fortement recommandé) swap 2G — RAM 1.9G sans swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h

# 3) Dossiers
mkdir -p ~/releases ~/backups
sudo mkdir -p /var/log/rod-ia
sudo chown adixon:adixon /var/log/rod-ia
```

### 7.1 Vérifier les archives

```bash
cd ~/releases
sha256sum -c accor-rod-user-1.0.0.tar.gz.sha256
sha256sum -c accor-rod-runtime-data-YYYYMMDD.tar.gz.sha256
sha256sum -c accor-rod-runtime-models-YYYYMMDD.tar.gz.sha256
```

### 7.2 Backup du placeholder

```bash
STAMP=$(date +%Y%m%d-%H%M%S)
sudo mkdir -p /var/www
sudo tar -C /var/www -czf ~/backups/rod-ia-placeholder-${STAMP}.tar.gz rod-ia
# conserver aussi une copie de ecosystem.config.js actuel
cp /var/www/rod-ia/ecosystem.config.js ~/backups/ecosystem.placeholder.${STAMP}.js
```

### 7.3 Arrêt propre de l’app PM2 actuelle

```bash
export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH"
pm2 describe rod-ia   # sanity
pm2 stop rod-ia
# ne pas delete tout de suite si on veut un rollback ultra-rapide ;
# delete juste avant le start de la nouvelle config (7.7)
```

### 7.4 Extraction code

```bash
# Vider / reconstruire le cwd (après backup !)
sudo rm -rf /var/www/rod-ia
sudo mkdir -p /var/www/rod-ia
sudo chown adixon:adixon /var/www/rod-ia

tar -xzf ~/releases/accor-rod-user-1.0.0.tar.gz -C /var/www/rod-ia
```

### 7.5 Extraction data + models

```bash
mkdir -p /var/www/rod-ia/data /var/www/rod-ia/models
tar -xzf ~/releases/accor-rod-runtime-data-YYYYMMDD.tar.gz -C /var/www/rod-ia/data
tar -xzf ~/releases/accor-rod-runtime-models-YYYYMMDD.tar.gz -C /var/www/rod-ia/models

# sanity layout
ls -la /var/www/rod-ia/
test -f /var/www/rod-ia/run_user.py
test -f /var/www/rod-ia/data/rod_reference.json
test -f /var/www/rod-ia/data/hotel_data.xlsx
test -f /var/www/rod-ia/models/final/last_trained.json
```

### 7.6 Environnement virtuel + deps

```bash
cd /var/www/rod-ia
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
pip install -e .
# sanity import
python -c "from accor.user.app import app; from accor.data_io import PROJECT_ROOT, DATA_DIR, MODELS_DIR; print(PROJECT_ROOT, DATA_DIR.exists(), MODELS_DIR.exists())"
deactivate
```

Attendu : `PROJECT_ROOT` = `/var/www/rod-ia`, `DATA_DIR` / `MODELS_DIR` existent.

### 7.7 PM2 — bascule vers la nouvelle app

Voir §8 pour le contenu de `ecosystem.config.js`. Puis :

```bash
export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH"
cd /var/www/rod-ia
pm2 delete rod-ia || true
pm2 start ecosystem.config.js
pm2 save
pm2 status
pm2 logs rod-ia --lines 50
```

### 7.8 Permissions / propriété

```bash
# app écrite par adixon ; pas besoin de root pour run
sudo chown -R adixon:adixon /var/www/rod-ia
# s'assurer que data reste writable si upsert hôtel (hotel_fetch)
# → user PM2 = adixon : OK si ownership correct
```

---

## 8. Configuration PM2 + env

### 8.1 `ecosystem.config.js` cible

Fichier : `/var/www/rod-ia/ecosystem.config.js`

```js
module.exports = {
  apps: [
    {
      name: "rod-ia",
      cwd: "/var/www/rod-ia",
      script: "run_user.py",
      interpreter: "/var/www/rod-ia/.venv/bin/python",
      args: "--host 127.0.0.1 --port 8000",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 20,
      min_uptime: "5s",
      max_memory_restart: "700M",
      env: {
        ACCOR_HOST: "127.0.0.1",
        ACCOR_PORT: "8000",
        PYTHONUNBUFFERED: "1",
        // PATH optionnel si besoin de binaires locaux
      },
      out_file: "/var/log/rod-ia/rod-ia.out.log",
      error_file: "/var/log/rod-ia/rod-ia.error.log",
      merge_logs: true,
      time: true,
    },
  ],
};
```

### 8.2 Points clés

| Paramètre | Valeur | Pourquoi |
|-----------|--------|----------|
| `interpreter` | `.venv/bin/python` | deps isolées (pas le python système nu) |
| `script` | `run_user.py` | entrée user (pas `server.py` placeholder) |
| `--host 127.0.0.1` | loopback | Apache proxy ; pas d’exposition directe :8000 |
| `--port 8000` | aligné ProxyPass | déjà configuré |
| `instances: 1` | mono-process | RAM limitée ; Flask dev server |
| `max_memory_restart` | ~700M | garde-fou OOM sur 2G |
| `ACCOR_*` | redondant avec args | cohérence serve_utils |

### 8.3 Survivance reboot

Déjà couverte par `pm2-adixon.service` + `pm2 save`. Après bascule :

```bash
pm2 save
systemctl --user status pm2-adixon 2>/dev/null || sudo systemctl status pm2-adixon
```

### 8.4 Phase 2 (hors MVP)

- Remplacer le serveur Flask built-in par **gunicorn** (`gunicorn -b 127.0.0.1:8000 -w 1 'accor.user.app:app'`) si stabilité / timeouts le demandent.
- Un seul worker recommandé tant que RAM ≤ 2G.

---

## 9. Vérifications post-déploiement

### 9.1 Process & ports

```bash
export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH"
pm2 status
ss -lntp | grep 8000
# attendu : python .venv … 127.0.0.1:8000
```

### 9.2 Smoke HTTP local

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
# attendu : 200 (page user, plus le Hello placeholder)

curl -sS http://127.0.0.1:8000/ | head -c 200
# doit contenir du HTML Accor / user, pas "Hello"
```

### 9.3 Smoke API user (exemples)

```bash
# adapter aux routes réelles documentées dans docs/API_USER.md
curl -sS http://127.0.0.1:8000/api/brands | head -c 400
curl -sS "http://127.0.0.1:8000/api/hotels/search?q=ibis" | head -c 400
```

### 9.4 Smoke HTTPS public

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://rod-ia.adixon-dev.fr/
# attendu : 200

curl -sSI https://rod-ia.adixon-dev.fr/ | head -n 15
```

Depuis un navigateur : ouvrir `https://rod-ia.adixon-dev.fr/` et parcourir le wizard (marque → hôtel → simulation).

### 9.5 Logs

```bash
pm2 logs rod-ia --lines 100
tail -n 100 /var/log/rod-ia/rod-ia.out.log
tail -n 100 /var/log/rod-ia/rod-ia.error.log
```

Erreurs typiques à surveiller au 1er boot :

- `ModuleNotFoundError` → venv / `pip install -e .` incomplet
- `FileNotFoundError` data/models → extraction runtime manquante / mauvais layout
- OOM / process kill → swap + `max_memory_restart`
- Import xgboost / libgomp → lib système

### 9.6 Apache (si nécessaire seulement)

Pas de changement prévu. En cas de 502 :

```bash
sudo apachectl configtest
sudo systemctl status apache2
# vérifier que 8000 répond en local
```

---

## 10. Rollback

### 10.1 Rollback rapide (placeholder)

```bash
export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH"
pm2 delete rod-ia || true

# restaurer l’archive placeholder
sudo rm -rf /var/www/rod-ia
sudo tar -xzf ~/backups/rod-ia-placeholder-STAMP.tar.gz -C /var/www

# si ecosystem placeholder séparé
# cp ~/backups/ecosystem.placeholder.STAMP.js /var/www/rod-ia/ecosystem.config.js

cd /var/www/rod-ia
pm2 start ecosystem.config.js
# ou : pm2 start server.py --name rod-ia --interpreter /usr/bin/python3
pm2 save

curl -sS http://127.0.0.1:8000/
curl -sS -o /dev/null -w "%{http_code}\n" https://rod-ia.adixon-dev.fr/
```

### 10.2 Rollback vers une release précédente

Stratégie recommandée à moyen terme (blue/green simple) :

```text
/var/www/
  rod-ia -> releases/accor-rod-user-1.0.0   # symlink « current »
  releases/
    accor-rod-user-1.0.0/
    accor-rod-user-1.0.1/
```

MVP : backup tarball avant chaque mise à jour (§7.2) suffit.

### 10.3 Critères de déclenchement rollback

- HTTPS ne renvoie plus 200 après 5 min
- Erreurs fatales répétées dans `rod-ia.error.log`
- OOM en boucle (PM2 restart storm)
- Simulation métier cassée (data/models incomplets) sans fix rapide

---

## 11. Risques

| Risque | Sévérité | Mitigation |
|--------|----------|------------|
| **RAM 1,9 G sans swap** | **Haute** | Ajouter **2G swap** avant install ; `max_memory_restart` ; 1 seul process ; éviter chargements parallèles lourds |
| **pip / venv absents** | Haute | `apt install python3-venv python3-pip` en prérequis bloquant |
| **Layout `PROJECT_ROOT` incorrect** | Haute | Respecter arborescence §3 ; test import `DATA_DIR.exists()` |
| **Bind `0.0.0.0:8000`** | Moyenne | Forcer `127.0.0.1` (args + env) — le placeholder écoute actuellement toutes interfaces |
| **Data/models manquants** | Haute | Packages séparés + checklist fichiers critiques |
| **Stacking model incomplet** | Moyenne | Inclure intermédiaire `intermediate_model_id` avec le final |
| **Timeouts Apache** sur prédictions lentes | Moyenne | Monitorer ; éventuellement `ProxyTimeout` / `Timeout` Apache |
| **Écriture `hotel_data.xlsx`** (fetch hôtel inconnu) | Basse–Moy. | Ownership `adixon` ; backup data périodique |
| **Flask built-in server** | Basse (MVP) | OK pour démo ; gunicorn en phase 2 |
| **Conf Apache `adipos` vs `adixon`** | Nulle | Cosmétique |
| **Sudo password** | Process | Ne jamais le versionner ; session interactive SSH |
| **Charge mémoire pandas+xgb** au 1er predict | Moyenne | Smoke test predict après boot ; swap |

---

## 12. Infos manquantes / questions au client

1. **Swap** : OK pour créer un fichier swap 2G sur le VPS ?
2. **Data de prod** : les copies locales actuelles (`data/`, `models/`) sont-elles validées pour le MVP public, ou un jeu « client » spécifique doit être fourni ?
3. **Timeouts** : faut-il allonger les timeouts Apache (`ProxyTimeout`) pour les appels de simulation / prédiction IA ?
4. **Mises à jour** : fréquence attendue et responsable du packaging (équipe dev vs client) ?
5. **Monitoring** : alerte simple (uptime HTTPS / PM2) souhaitée, ou smoke manuel suffit pour le MVP ?
6. **Écriture runtime** : autoriser l’upsert d’hôtels scrapés dans `hotel_data.xlsx` en prod, ou mode lecture seule ?
7. **Fenêtre de bascule** : créneau et contact de validation fonctionnelle post-déploiement ?
8. **Admin** : confirmation explicite que l’admin ne doit **pas** être exposé sur ce vhost (recommandé).

---

## 13. Checklist go / no-go avant déploiement réel

### Bloquant (no-go si non coché)

- [ ] Accès SSH `adixon@178.62.220.14` validé + sudo password disponible **hors repo**
- [ ] `python3-venv` + `python3-pip` installables (apt OK)
- [ ] Archives code + data + models construites et **checksums SHA256** vérifiés
- [ ] Layout package testé localement (`PROJECT_ROOT` / imports)
- [ ] Fichiers data critiques présents (liste §4.2)
- [ ] Modèle final + intermédiaire stacking présents et cohérents
- [ ] Backup placeholder planifié (`~/backups/…`)
- [ ] Client a validé l’URL publique et le scope **user-only**
- [ ] Procédure rollback (§10) relue et archives backup OK

### Fortement recommandé

- [ ] Swap 2G activé (ou RAM upgradée)
- [ ] Smoke script local (import + `curl` routes) prêt
- [ ] Contact client dispo pendant la bascule
- [ ] Note de version `RELEASE.txt` dans le package

### Go technique minimal

| # | Contrôle | OK ? |
|---|----------|------|
| 1 | HTTPS placeholder encore 200 (baseline) | |
| 2 | Packages transférés dans `~/releases/` | |
| 3 | Checksums OK | |
| 4 | OS deps installées | |
| 5 | Extraction + venv + `pip install -e .` OK | |
| 6 | PM2 start sans restart loop 2 min | |
| 7 | `curl 127.0.0.1:8000` = UI user | |
| 8 | `curl https://rod-ia.adixon-dev.fr` = 200 UI user | |
| 9 | Parcours wizard navigateur (1 hôtel test) | |
| 10 | Logs propres (pas d’exception fatale) | |

---

## Annexe A — Variables d’environnement

| Variable | Prod recommandée | Défaut code |
|----------|------------------|-------------|
| `ACCOR_HOST` | `127.0.0.1` | `0.0.0.0` |
| `ACCOR_PORT` | `8000` | (port CLI : 5056 user) |
| `PYTHONUNBUFFERED` | `1` | — |

Priorité d’écoute : args CLI (`--host` / `--port`) passés par PM2 ; env en filet de sécurité via `serve_utils`.

---

## Annexe B — Stratégie de releases futures

1. Build local → `dist/accor-rod-user-X.Y.Z.tar.gz` (+ data/models si changés).
2. Upload `~/releases/`.
3. Backup `/var/www/rod-ia` → `~/backups/`.
4. Extract over (ou symlink `current`).
5. `pip install -e .` dans le venv existant (ou recreate venv si deps changent).
6. `pm2 restart rod-ia` (ou delete+start si ecosystem change).
7. Smoke §9 + `pm2 save`.

Versionner **toujours** le code ; ne republier data/models que s’ils évoluent.

---

## Annexe C — Références internes

| Doc | Contenu |
|-----|---------|
| [API_USER.md](API_USER.md) | Routes Flask user |
| [DATA.md](DATA.md) | Fichiers data & models |
| [ROD_RULES.md](ROD_RULES.md) | Règles métier simulation |
| [MODULES.md](MODULES.md) | Modules Python |
| [README.md](README.md) | Index docs |
| `src/accor/data_io.py` | `PROJECT_ROOT`, `DATA_DIR`, `MODELS_DIR` |
| `src/accor/serve_utils.py` | host/port env |
| `run_user.py` | Entrée process |

---

## Annexe D — Rappel sécurité

- Ne pas stocker le mot de passe sudo dans git, tickets publics, ni ce fichier.
- Clés SSH privées hors dépôt.
- Logs PM2 peuvent contenir des traces métier : restreindre la lecture si besoin.
- Port 8000 : loopback uniquement derrière Apache.

---

*Document généré pour la préparation de déploiement Accor ROD user — plan only.*
