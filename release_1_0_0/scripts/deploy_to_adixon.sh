#!/usr/bin/env bash
# =============================================================================
# Déploiement release_1_0_0 → serveur Adixon (prod client)
# =============================================================================
#
# Règle de travail :
#   1. Toute modification se fait d'abord en LOCAL (release_1_0_0/)
#   2. Ensuite on synchronise vers Adixon avec CE script
#   3. La source de vérité code = local ; le serveur n'est pas édité à la main
#   4. Ne PAS lancer ce script sans consigne explicite (« déploie sur Adixon »)
#
# Usage (depuis release_1_0_0/) :
#   ./scripts/deploy_to_adixon.sh              # code + static + doc + scripts + PM2
#   ./scripts/deploy_to_adixon.sh --deps       # + pip install -r requirements.txt
#   ./scripts/deploy_to_adixon.sh --data       # + data/files (input/output, hors _raw_sources)
#   ./scripts/deploy_to_adixon.sh --duckdb     # + data/duckdb (main.duckdb)
#   ./scripts/deploy_to_adixon.sh --models     # + models/ (super + legacy)
#   ./scripts/deploy_to_adixon.sh --raw        # + data/files/input/_raw_sources
#   ./scripts/deploy_to_adixon.sh --auth       # + data/auth (secrets / comptes)
#   ./scripts/deploy_to_adixon.sh --all        # code + deps + data + duckdb + models
#   ./scripts/deploy_to_adixon.sh --dry-run    # affiche sans copier ni restart
#
# Ne touche JAMAIS par défaut :
#   .venv/  data/  models/  data/auth/  logs PM2
#
# Cible : adixon@178.62.220.14:/var/www/rod-ia
# Public : https://rod-ia.adixon-dev.fr  (user /admin ; /studio → redirect)
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
DO_DUCKDB=0
DO_MODELS=0
DO_RAW=0
DO_AUTH=0
DRY=0

for arg in "$@"; do
  case "$arg" in
    --deps) DO_DEPS=1 ;;
    --data) DO_DATA=1 ;;
    --duckdb) DO_DUCKDB=1 ;;
    --models) DO_MODELS=1 ;;
    --raw) DO_RAW=1 ;;
    --auth) DO_AUTH=1 ;;
    --all) DO_DEPS=1; DO_DATA=1; DO_DUCKDB=1; DO_MODELS=1 ;;
    --dry-run) DRY=1; RSYNC+=( --dry-run -v ) ;;
    -h|--help)
      sed -n '2,40p' "$0"
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
log "Flags   : deps=$DO_DEPS data=$DO_DATA duckdb=$DO_DUCKDB models=$DO_MODELS raw=$DO_RAW auth=$DO_AUTH dry=$DRY"

# Connexion
"${SSH[@]}" "$HOST" "test -d $REMOTE && echo ok_remote" >/dev/null

GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null \
  || git -C "$(dirname "$ROOT")" rev-parse --short HEAD 2>/dev/null \
  || echo nogit)"
BUILT_AT="$(date -Iseconds)"
VERSION_LINE="release=1.0.0
package=release_1_0_0
deployed_at=${BUILT_AT}
git_sha=${GIT_SHA}
host_local=$(hostname 2>/dev/null || echo local)
source=local-sync
user=/user
admin=/admin
legacy_studio=/studio → redirect /admin
"

sync_tree() {
  local src="$1"
  local dest="$2"
  shift 2
  log "rsync $src → $dest"
  "${RSYNC[@]}" "$@" "$src" "${HOST}:${dest}"
}

scp_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    return 0
  fi
  if [[ "$DRY" -eq 1 ]]; then
    echo "  (dry) $f"
  else
    scp -o BatchMode=yes -q "$f" "${HOST}:${REMOTE}/$f"
  fi
}

# --- Code Python ---
log "Sync src/"
sync_tree "src/" "$REMOTE/src/" \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.egg-info/' \
  --exclude '.pytest_cache/'

log "Sync pipeline/"
sync_tree "pipeline/" "$REMOTE/pipeline/" \
  --exclude '__pycache__/'

# --- Assets / docs ---
if [[ -d static ]]; then
  log "Sync static/"
  sync_tree "static/" "$REMOTE/static/" \
    --exclude '__pycache__/'
fi

if [[ -d doc ]]; then
  log "Sync doc/"
  sync_tree "doc/" "$REMOTE/doc/" \
    --exclude '__pycache__/'
fi

log "Sync scripts/"
if [[ -d scripts ]]; then
  sync_tree "scripts/" "$REMOTE/scripts/" \
    --exclude '__pycache__/' \
    --exclude '*.pyc'
  # s'assurer que le deploy script reste exécutable côté serveur
  if [[ "$DRY" -eq 0 ]]; then
    "${SSH[@]}" "$HOST" "chmod +x ${REMOTE}/scripts/*.sh 2>/dev/null || true"
    "${SSH[@]}" "$HOST" "chmod +x ${REMOTE}/scripts/studio_redirect.py 2>/dev/null || true"
  fi
fi

# --- Entrypoints + meta ---
log "Sync entrypoints + deps meta"
for f in run.py main.py requirements.txt ecosystem.config.js README.md RELEASE.txt; do
  scp_file "$f"
done

# RELEASE stamp (écrase avec git_sha + date de ce deploy)
if [[ "$DRY" -eq 0 ]]; then
  printf '%s' "$VERSION_LINE" | "${SSH[@]}" "$HOST" "cat > ${REMOTE}/RELEASE.txt"
fi

# --- Data (optionnel) ---
if [[ "$DO_DATA" -eq 1 ]]; then
  log "Sync data/files (hors _raw_sources, hors auth)"
  # input + output + marques éventuels sous data/
  if [[ -d data/files ]]; then
    EXCLUDE_RAW=(--exclude '_raw_sources/')
    if [[ "$DO_RAW" -eq 1 ]]; then
      EXCLUDE_RAW=()
      log "  (inclut _raw_sources — volume important)"
    fi
    sync_tree "data/files/" "$REMOTE/data/files/" \
      --exclude '__pycache__/' \
      --exclude '*.pid' \
      --exclude '*.log' \
      "${EXCLUDE_RAW[@]}"
  fi
  if [[ -d data/marques ]]; then
    sync_tree "data/marques/" "$REMOTE/data/marques/"
  fi
fi

if [[ "$DO_RAW" -eq 1 && "$DO_DATA" -eq 0 ]]; then
  log "Sync data/files/input/_raw_sources/ uniquement"
  if [[ -d data/files/input/_raw_sources ]]; then
    sync_tree "data/files/input/_raw_sources/" "$REMOTE/data/files/input/_raw_sources/"
  fi
fi

if [[ "$DO_DUCKDB" -eq 1 ]]; then
  log "Sync data/duckdb/"
  if [[ -d data/duckdb ]]; then
    sync_tree "data/duckdb/" "$REMOTE/data/duckdb/" \
      --exclude '*.wal' \
      --exclude 'workers/*'
  fi
fi

if [[ "$DO_AUTH" -eq 1 ]]; then
  log "Sync data/auth/ (secrets — usage conscient)"
  if [[ -d data/auth ]]; then
    sync_tree "data/auth/" "$REMOTE/data/auth/"
  fi
fi

# --- Models (optionnel) ---
if [[ "$DO_MODELS" -eq 1 ]]; then
  log "Sync models/"
  if [[ -d models ]]; then
    sync_tree "models/" "$REMOTE/models/" \
      --exclude '__pycache__/'
  fi
fi

# --- Deps Python (optionnel) ---
if [[ "$DO_DEPS" -eq 1 && "$DRY" -eq 0 ]]; then
  log "pip install -r requirements.txt sur le serveur"
  "${SSH[@]}" "$HOST" "bash -lc '
    set -e
    cd ${REMOTE}
    if [[ ! -d .venv ]]; then
      python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -q --upgrade pip wheel
    pip install -q -r requirements.txt
    python -c \"from pathlib import Path; import sys; sys.path.insert(0, \\\".\\\"); from src.pipeline.paths import Paths; p=Paths(\\\".\\\").ensure(); print(\\\"ok\\\", p.root, p.input.exists(), p.models_super.exists())\"
  '"
fi

# --- Restart / reload PM2 (sauf dry-run) ---
if [[ "$DRY" -eq 0 ]]; then
  log "Reload PM2 (rod-ia-user :8000 + rod-ia-admin studio_redirect :8001)"
  "${SSH[@]}" "$HOST" "bash -lc '
    set -e
    ${PM2_PATH}
    cd ${REMOTE}
    mkdir -p /var/log/rod-ia data/files/input data/files/output data/duckdb/main models/super
    if [[ -f ecosystem.config.js ]]; then
      pm2 startOrReload ecosystem.config.js --update-env
    else
      pm2 restart rod-ia-user rod-ia-admin || pm2 restart all
    fi
    pm2 save || true
    sleep 2
    pm2 status
  '"

  log "Smoke HTTPS"
  code_user=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://rod-ia.adixon-dev.fr/ || echo fail)
  code_admin=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://rod-ia.adixon-dev.fr/admin || echo fail)
  code_studio=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 https://rod-ia.adixon-dev.fr/studio/ || echo fail)
  echo "  user   https://rod-ia.adixon-dev.fr/        → $code_user"
  echo "  admin  https://rod-ia.adixon-dev.fr/admin   → $code_admin"
  echo "  studio https://rod-ia.adixon-dev.fr/studio/ → $code_studio (redirect → /admin)"
fi

log "Terminé · git_sha=$GIT_SHA · $BUILT_AT"
echo
echo "Rappel : éditer uniquement en local (release_1_0_0/), puis relancer ce script."
echo "Par défaut : PAS de deploy sans consigne explicite."
echo "Premier install complet : ./scripts/deploy_to_adixon.sh --all"
