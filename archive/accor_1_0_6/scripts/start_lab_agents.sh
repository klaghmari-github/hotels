#!/usr/bin/env bash
# Démarre / maintient :
#   1) watchdog (run_dev + admin + user + tunnels Cloudflare + consignes)
#   2) boucle gitpush toutes les 10 min s'il y a des changements
#   3) sync liens.html
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOTELS="$(cd "$ROOT/.." && pwd)"
STATE="$ROOT/data/dev_console"
LOG_DIR="${TMPDIR:-/tmp}/accor-lab-agents"
mkdir -p "$STATE" "$LOG_DIR"

export ACCOR_DEV_YOLO="${ACCOR_DEV_YOLO:-1}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3

# ── liens.html ──────────────────────────────────────────────────────────────
"$PY" "$ROOT/scripts/sync_liens_html.py" || true

# ── watchdog consignes + services ──────────────────────────────────────────
WD_PID_FILE="$STATE/watchdog.pid"
start_watchdog() {
  if [[ -f "$WD_PID_FILE" ]]; then
    old="$(cat "$WD_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
      echo "watchdog déjà UP pid=$old"
      return 0
    fi
  fi
  echo "démarrage watchdog…"
  nohup "$PY" "$ROOT/scripts/dev_watchdog.py" \
    >> /tmp/accor-dev-watchdog.log 2>&1 &
  echo $! > "$WD_PID_FILE"
  echo "watchdog pid=$(cat "$WD_PID_FILE")"
}

# ── gitpush loop 10 min ─────────────────────────────────────────────────────
GP_PID_FILE="$STATE/gitpush_loop.pid"
start_gitpush_loop() {
  if [[ -f "$GP_PID_FILE" ]]; then
    old="$(cat "$GP_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
      echo "gitpush_loop déjà UP pid=$old"
      return 0
    fi
  fi
  echo "démarrage gitpush_loop (10 min)…"
  nohup bash -c '
    ROOT="'"$ROOT"'"
    HOTELS="'"$HOTELS"'"
    LOG="'"$LOG_DIR"'/gitpush_loop.log"
    while true; do
      {
        echo "==== $(date -Iseconds) gitpush check ===="
        # sync liens avant push si tunnels ont bougé
        "'"$PY"'" "'"$ROOT"'/scripts/sync_liens_html.py" 2>&1 || true
        if [[ -x "'"$HOTELS"'/gitpush.sh" ]]; then
          bash "'"$HOTELS"'/gitpush.sh" 2>&1 || true
        else
          echo "gitpush.sh manquant"
        fi
      } >> "$LOG" 2>&1
      sleep 600
    done
  ' >> "$LOG_DIR/gitpush_loop.wrapper.log" 2>&1 &
  echo $! > "$GP_PID_FILE"
  echo "gitpush_loop pid=$(cat "$GP_PID_FILE")"
}

start_watchdog
start_gitpush_loop

echo
echo "=== URLs ==="
for n in dev admin user; do
  f="$STATE/tunnel_${n}.url"
  if [[ -f "$f" ]]; then
    echo "  $n: $(cat "$f")"
  else
    echo "  $n: (tunnel pas encore écrit — attendre ~30s le watchdog)"
  fi
done
echo "  liens.html: $ROOT/liens.html"
echo "  consignes Cloudflare = tunnel_dev.url"
echo
echo "Logs:"
echo "  watchdog : /tmp/accor-dev-watchdog.log"
echo "  gitpush  : $LOG_DIR/gitpush_loop.log"
