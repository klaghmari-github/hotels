#!/usr/bin/env bash
# =============================================================================
# Déploiement local → serveur Adixon (prod client)
# =============================================================================
#
# Règle de travail :
#   1. Toute modification se fait d'abord en LOCAL (workspace accor/)
#   2. Ensuite on synchronise vers Adixon avec CE script
#   3. La source de vérité code = local ; le serveur n'est pas édité à la main
#
# Usage :
#   ./scripts/deploy_to_adixon.sh              # code + static + templates
#   ./scripts/deploy_to_adixon.sh --deps       # + pip install -e . sur le serveur
#   ./scripts/deploy_to_adixon.sh --data       # + package data runtime
#   ./scripts/deploy_to_adixon.sh --models     # + models final + intermédiaire
#   ./scripts/deploy_to_adixon.sh --init-models     # force init CLI après deploy (défaut: auto)
#   ./scripts/deploy_to_adixon.sh --no-init-models  # ne lance pas l'init CLI (admin le fait au boot)
#   ./scripts/deploy_to_adixon.sh --all             # code + deps + data + models + init
#   ./scripts/deploy_to_adixon.sh --dry-run         # affiche sans copier
#
# Ne touche JAMAIS (sauf flags explicites) :
#   .venv/  data/  models/  logs PM2
# Sync aussi ecosystem.config.js (watch .py + ACCOR_RELOAD=0)
#
# Cible : adixon@178.62.220.14:/var/www/rod-ia
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${ADIXON_HOST:-adixon@178.62.220.14}"
REMOTE="${ADIXON_REMOTE:-/var/www/rod-ia}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=20)
RSYNC=(rsync -az --delete --human-readable)
PM2_PATH='export PATH="$HOME/.nvm/versions/node/v22.23.1/bin:$PATH"'

DO_DEPS=0
DO_DATA=0
DO_MODELS=0
# Par défaut : après deploy, assure inter+final par solution s'ils manquent
DO_INIT_MODELS=1
DRY=0

for arg in "$@"; do
  case "$arg" in
    --deps) DO_DEPS=1 ;;
    --data) DO_DATA=1 ;;
    --models) DO_MODELS=1 ;;
    --init-models) DO_INIT_MODELS=1 ;;
    --no-init-models) DO_INIT_MODELS=0 ;;
    --all) DO_DEPS=1; DO_DATA=1; DO_MODELS=1; DO_INIT_MODELS=1 ;;
    --dry-run) DRY=1; RSYNC+=( --dry-run -v ) ;;
    -h|--help)
      sed -n '2,34p' "$0"
      exit 0
      ;;
    *)
      echo "Option inconnue: $arg" >&2
      exit 2
      ;;
  esac
done

log() { printf '── %s\n' "$*"; }

cd "$ROOT"

log "Source  : $ROOT"
log "Cible   : $HOST:$REMOTE"
log "Flags   : deps=$DO_DEPS data=$DO_DATA models=$DO_MODELS init_models=$DO_INIT_MODELS dry=$DRY"

# Connexion
"${SSH[@]}" "$HOST" "test -d $REMOTE && echo ok_remote" >/dev/null

GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo nogit)"
BUILT_AT="$(date -Iseconds)"
VERSION_LINE="deployed_at=${BUILT_AT}
git_sha=${GIT_SHA}
host_local=$(hostname 2>/dev/null || echo local)
source=local-sync
"

sync_tree() {
  local src="$1"
  local dest="$2"
  shift 2
  log "rsync $src → $dest"
  if [[ "$DRY" -eq 1 ]]; then
    "${RSYNC[@]}" "$@" "$src" "${HOST}:${dest}"
  else
    "${RSYNC[@]}" "$@" "$src" "${HOST}:${dest}"
  fi
}

# --- Code package (sans data/models/venv) ---
log "Sync code Python (src/accor)"
sync_tree "src/accor/" "$REMOTE/src/accor/" \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.egg-info/' \
  --exclude '.pytest_cache/'

log "Sync static/"
sync_tree "static/" "$REMOTE/static/" \
  --exclude '__pycache__/'

log "Sync templates/"
sync_tree "templates/" "$REMOTE/templates/"

log "Sync entrypoints + deps meta"
for f in run_user.py run_admin.py pyproject.toml requirements.txt ecosystem.config.js; do
  if [[ -f "$f" ]]; then
    if [[ "$DRY" -eq 1 ]]; then
      echo "  (dry) $f"
    else
      scp -o BatchMode=yes -q "$f" "${HOST}:${REMOTE}/$f"
    fi
  fi
done

log "Sync scripts/"
if [[ -d scripts ]]; then
  sync_tree "scripts/" "$REMOTE/scripts/" \
    --exclude '__pycache__/' \
    --exclude '*.pyc'
fi

# RELEASE stamp
if [[ "$DRY" -eq 0 ]]; then
  printf '%s' "$VERSION_LINE" | "${SSH[@]}" "$HOST" "cat > ${REMOTE}/RELEASE.txt"
fi

# --- Data (optionnel) ---
if [[ "$DO_DATA" -eq 1 ]]; then
  log "Sync data/ (runtime, hors dev_console)"
  sync_tree "data/" "$REMOTE/data/" \
    --exclude 'dev_console/' \
    --exclude '__pycache__/' \
    --exclude '*.pid' \
    --exclude '*.log' \
    --exclude 'tunnel_*.url'
fi

# --- Models (optionnel, MVP final + intermédiaire) ---
if [[ "$DO_MODELS" -eq 1 ]]; then
  log "Sync models (final top + intermédiaire si présents)"
  # sync structure minimale
  if [[ -d models/final ]]; then
    sync_tree "models/final/" "$REMOTE/models/final/" \
      --exclude '__pycache__/'
  fi
  if [[ -d models/design ]]; then
    # n'envoie que les design référencés si last_trained existe, sinon tout design/
    sync_tree "models/design/" "$REMOTE/models/design/" \
      --exclude '__pycache__/'
  fi
  if [[ -d models/deploy ]]; then
    sync_tree "models/deploy/" "$REMOTE/models/deploy/"
  fi
fi

# --- Deps Python (optionnel) ---
if [[ "$DO_DEPS" -eq 1 && "$DRY" -eq 0 ]]; then
  log "pip install -e . sur le serveur"
  "${SSH[@]}" "$HOST" "bash -lc '
    set -e
    cd ${REMOTE}
    source .venv/bin/activate
    pip install -q -r requirements.txt
    pip install -q -e .
    python -c \"from accor.data_io import PROJECT_ROOT, DATA_DIR; print(PROJECT_ROOT, DATA_DIR.exists())\"
  '"
fi

# --- Restart / reload PM2 (sauf dry-run) ---
if [[ "$DRY" -eq 0 ]]; then
  log "Reload PM2 (user + admin, watch backend .py)"
  "${SSH[@]}" "$HOST" "bash -lc '
    set -e
    ${PM2_PATH}
    cd ${REMOTE}
    mkdir -p /var/log/rod-ia
    # Recharge la conf (watch + env ACCOR_RELOAD=0) puis redémarre
    if [[ -f ecosystem.config.js ]]; then
      pm2 startOrReload ecosystem.config.js --update-env
    else
      pm2 restart rod-ia-user rod-ia-admin || pm2 restart all
    fi
    pm2 save || true
    sleep 2
    pm2 status
  '"

  # Admin démarre spawn_ensure_if_missing() : entraîne si manquant.
  # --init-models force un run CLI dédié (log /var/log/rod-ia/init_models.log).
  if [[ "$DO_INIT_MODELS" -eq 1 ]]; then
    log "Init modèles solution manquants sur le serveur (background)"
    "${SSH[@]}" "$HOST" "bash -lc '
      set -e
      cd ${REMOTE}
      source .venv/bin/activate
      mkdir -p /var/log/rod-ia
      # status d abord
      python -m accor.init_solution_models --status || true
      nohup python -m accor.init_solution_models \
        >> /var/log/rod-ia/init_models.log 2>&1 &
      echo \"init_models pid=\$! → /var/log/rod-ia/init_models.log\"
    '"
  else
    log "Init modèles : auto au démarrage admin si manquants (ou --init-models)"
  fi

  log "Smoke HTTPS"
  code_user=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://rod-ia.adixon-dev.fr/ || echo fail)
  code_admin=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://rod-ia.adixon-dev.fr/studio/ || echo fail)
  echo "  user  https://rod-ia.adixon-dev.fr/        → $code_user"
  echo "  admin https://rod-ia.adixon-dev.fr/studio/ → $code_admin"
fi

log "Terminé · git_sha=$GIT_SHA · $BUILT_AT"
echo
echo "Rappel : éditer uniquement en local, puis relancer ce script pour Adixon."
echo "Modèles solution manquants → entraînés auto (admin) ou via --init-models."
