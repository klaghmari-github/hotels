#!/usr/bin/env bash
# Expose admin (5055), user (5056) et/ou run_dev (5500) sur Internet via
# tunnel Cloudflare (ou ngrok), sans ouvrir de ports sur la box.
#
# Prérequis :
#   - bin/cloudflared (téléchargé dans le projet) ou cloudflared/ngrok sur PATH
#   - apps déjà lancées en local
#
# Usage :
#   ./scripts/expose_public.sh              # admin + user
#   ./scripts/expose_public.sh admin
#   ./scripts/expose_public.sh user
#   ./scripts/expose_public.sh dev          # console Grok / run_dev :5500
#   ./scripts/expose_public.sh all          # admin + user + dev
#   ./scripts/expose_public.sh status       # URLs enregistrées
#
# Les URL https://….trycloudflare.com sont écrites dans
#   data/dev_console/tunnel_<name>.url
# et affichées en fin de démarrage. Un quick tunnel change d'URL à chaque
# redémarrage du process cloudflared.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${ROOT}/data/dev_console"
LOG_DIR="${TMPDIR:-/tmp}/accor-tunnels"
ADMIN_PORT="${ACCOR_ADMIN_PORT:-5055}"
USER_PORT="${ACCOR_USER_PORT:-5056}"
DEV_PORT="${ACCOR_DEV_PORT:-5500}"
TARGET="${1:-both}"

mkdir -p "$STATE_DIR" "$LOG_DIR"

# Préférer le binaire local du projet
resolve_cf() {
  if [[ -x "${ROOT}/bin/cloudflared" ]]; then
    echo "${ROOT}/bin/cloudflared"
    return 0
  fi
  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
    return 0
  fi
  return 1
}

have() { command -v "$1" >/dev/null 2>&1; }

CF_BIN=""
if CF_BIN="$(resolve_cf)"; then
  :
else
  CF_BIN=""
fi

start_one() {
  local name="$1"
  local port="$2"
  local log="${LOG_DIR}/${name}.log"
  local pidf="${LOG_DIR}/${name}.pid"
  local urlf="${STATE_DIR}/tunnel_${name}.url"

  # déjà up ?
  if [[ -f "$pidf" ]]; then
    local old
    old="$(cat "$pidf" 2>/dev/null || true)"
    if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
      local existing
      existing="$(cat "$urlf" 2>/dev/null || true)"
      if [[ -n "$existing" ]]; then
        echo "── $name déjà exposé (pid=$old) : $existing"
        return 0
      fi
    fi
  fi

  echo "── Tunnel $name → http://127.0.0.1:${port}"
  if [[ -n "$CF_BIN" ]]; then
    echo "   outil : cloudflared ($CF_BIN)"
    : >"$log"
    nohup "$CF_BIN" tunnel --url "http://127.0.0.1:${port}" >"$log" 2>&1 &
    echo $! >"$pidf"
  elif have ngrok; then
    echo "   outil : ngrok"
    : >"$log"
    nohup ngrok http "$port" --log=stdout >"$log" 2>&1 &
    echo $! >"$pidf"
  else
    echo "Erreur : ni cloudflared ni ngrok."
    echo "  Placez cloudflared dans ${ROOT}/bin/cloudflared"
    echo "  ou : https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
    exit 1
  fi

  local url=""
  for _ in $(seq 1 40); do
    sleep 0.5
    if [[ -n "$CF_BIN" ]]; then
      url="$(grep -oE 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "$log" 2>/dev/null | head -1 || true)"
    else
      # ngrok local API
      url="$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
        | grep -oE 'https://[a-zA-Z0-9.-]+\.ngrok[^"]*' | head -1 || true)"
    fi
    if [[ -n "$url" ]]; then
      echo "$url" >"$urlf"
      echo "   ✅ public : $url"
      return 0
    fi
    if ! kill -0 "$(cat "$pidf")" 2>/dev/null; then
      echo "   ❌ process tunnel mort — voir $log"
      tail -20 "$log" || true
      return 1
    fi
  done
  echo "   ⚠ timeout URL (process encore up) — voir $log"
  return 1
}

show_status() {
  echo "Tunnels enregistrés (${STATE_DIR}) :"
  local any=0
  for name in admin user dev; do
    local urlf="${STATE_DIR}/tunnel_${name}.url"
    local pidf="${LOG_DIR}/${name}.pid"
    local url="—"
    local alive="down"
    [[ -f "$urlf" ]] && url="$(cat "$urlf")"
    if [[ -f "$pidf" ]] && kill -0 "$(cat "$pidf")" 2>/dev/null; then
      alive="up pid=$(cat "$pidf")"
    fi
    if [[ "$url" != "—" ]] || [[ "$alive" != "down" ]]; then
      any=1
      printf "  %-6s  %-8s  %s\n" "$name" "$alive" "$url"
    fi
  done
  if [[ $any -eq 0 ]]; then
    echo "  (aucun)"
  fi
}

case "$TARGET" in
  admin) start_one admin "$ADMIN_PORT" ;;
  user)  start_one user  "$USER_PORT"  ;;
  dev)   start_one dev   "$DEV_PORT"   ;;
  both)
    start_one admin "$ADMIN_PORT"
    start_one user  "$USER_PORT"
    ;;
  all)
    start_one admin "$ADMIN_PORT"
    start_one user  "$USER_PORT"
    start_one dev   "$DEV_PORT"
    ;;
  status)
    show_status
    exit 0
    ;;
  *)
    echo "Usage: $0 [admin|user|dev|both|all|status]"
    exit 1
    ;;
esac

echo ""
show_status
echo ""
echo "Note : les quick tunnels Cloudflare changent d'URL à chaque redémarrage."
echo "       L'IP 192.168.x.x reste uniquement pour le LAN."
echo "       Arrêt : kill \$(cat ${LOG_DIR}/<name>.pid)"
