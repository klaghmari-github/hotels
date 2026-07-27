#!/usr/bin/env bash
# Expose admin (5055) et/ou user (5056) sur Internet via tunnel,
# sans ouvrir de ports sur la box.
#
# Prérequis : un des outils suivants
#   - cloudflared  https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
#   - ngrok        https://ngrok.com/download
#
# Usage :
#   ./scripts/expose_public.sh           # les deux (admin + user)
#   ./scripts/expose_public.sh admin     # admin seulement
#   ./scripts/expose_public.sh user      # user seulement
#
# Les apps doivent déjà tourner en local (run_admin / run_user).

set -euo pipefail

TARGET="${1:-both}"
ADMIN_PORT="${ACCOR_ADMIN_PORT:-5055}"
USER_PORT="${ACCOR_USER_PORT:-5056}"

have() { command -v "$1" >/dev/null 2>&1; }

tunnel_one() {
  local name="$1"
  local port="$2"
  echo ""
  echo "── Tunnel $name → http://127.0.0.1:$port ──"
  if have cloudflared; then
    echo "Outil : cloudflared (quick tunnel)"
    exec cloudflared tunnel --url "http://127.0.0.1:${port}"
  elif have ngrok; then
    echo "Outil : ngrok"
    exec ngrok http "$port"
  else
    echo "Erreur : ni cloudflared ni ngrok n'est installé."
    echo "  sudo apt install cloudflared   # ou télécharger depuis Cloudflare"
    echo "  # ou : https://ngrok.com/download"
    exit 1
  fi
}

case "$TARGET" in
  admin)
    tunnel_one "admin" "$ADMIN_PORT"
    ;;
  user)
    tunnel_one "user" "$USER_PORT"
    ;;
  both)
    if ! have cloudflared && ! have ngrok; then
      echo "Erreur : ni cloudflared ni ngrok n'est installé."
      exit 1
    fi
    echo "Lancement de 2 tunnels (admin :$ADMIN_PORT + user :$USER_PORT)."
    echo "Chaque tunnel affiche une URL https publique."
    if have cloudflared; then
      cloudflared tunnel --url "http://127.0.0.1:${ADMIN_PORT}" &
      PID1=$!
      cloudflared tunnel --url "http://127.0.0.1:${USER_PORT}" &
      PID2=$!
      trap 'kill $PID1 $PID2 2>/dev/null || true' EXIT INT TERM
      wait
    else
      echo "ngrok ne gère qu'un tunnel gratuit à la fois."
      echo "Relance avec : $0 admin   ou   $0 user"
      exit 1
    fi
    ;;
  *)
    echo "Usage: $0 [admin|user|both]"
    exit 1
    ;;
esac
