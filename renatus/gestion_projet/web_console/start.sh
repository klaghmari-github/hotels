#!/usr/bin/env bash
# Demarre API + worker + tunnel Cloudflare (gestion only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
GESTION="$(cd "$ROOT/.." && pwd)"
VENV_PY="${VENV_PY:-$GESTION/../.venv/bin/python}"
if [[ ! -x "$VENV_PY" ]]; then
  VENV_PY="$(command -v python3)"
fi
CLOUDFLARED="${CLOUDFLARED:-$ROOT/cloudflared}"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
INTERVAL="${INTERVAL:-60}"
LOGDIR="$GESTION/logs/web_console"
mkdir -p "$LOGDIR" "$GESTION/agentic/web_console"

export GESTION_DIR="$GESTION"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[web_console] gestion=$GESTION port=$PORT"

# stop previous if same pid files
for f in api.pid worker.pid tunnel.pid; do
  if [[ -f "$LOGDIR/$f" ]]; then
    old="$(cat "$LOGDIR/$f" || true)"
    if [[ -n "$old" ]] && kill -0 "$old" 2>/dev/null; then
      kill "$old" 2>/dev/null || true
      sleep 0.5
    fi
    rm -f "$LOGDIR/$f"
  fi
done

# API
nohup "$VENV_PY" -m uvicorn app:app --app-dir "$ROOT" --host "$HOST" --port "$PORT" \
  >"$LOGDIR/api.log" 2>&1 &
echo $! >"$LOGDIR/api.pid"
echo "[web_console] api pid $(cat "$LOGDIR/api.pid")"

# Worker (statut 1 min + inscription CSV)
nohup "$VENV_PY" "$ROOT/worker.py" --interval "$INTERVAL" --gestion-dir "$GESTION" \
  >"$LOGDIR/worker.log" 2>&1 &
echo $! >"$LOGDIR/worker.pid"
echo "[web_console] worker pid $(cat "$LOGDIR/worker.pid")"

sleep 1
if ! curl -sf "http://$HOST:$PORT/api/health" >/dev/null; then
  echo "[web_console] ERREUR: API non joignable — voir $LOGDIR/api.log"
  tail -20 "$LOGDIR/api.log" || true
  exit 1
fi

# Tunnel Cloudflare (URL ephemere trycloudflare.com)
URL_FILE="$LOGDIR/public_url.txt"
rm -f "$URL_FILE"
nohup "$CLOUDFLARED" tunnel --url "http://$HOST:$PORT" --no-autoupdate \
  >"$LOGDIR/tunnel.log" 2>&1 &
echo $! >"$LOGDIR/tunnel.pid"
echo "[web_console] tunnel pid $(cat "$LOGDIR/tunnel.pid") — attente URL…"

# Extraire l URL publique (jusqu a ~30s)
for i in $(seq 1 30); do
  if grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOGDIR/tunnel.log" 2>/dev/null | head -1 >"$URL_FILE.tmp"; then
    if [[ -s "$URL_FILE.tmp" ]]; then
      mv "$URL_FILE.tmp" "$URL_FILE"
      break
    fi
  fi
  sleep 1
done

if [[ -f "$URL_FILE" && -s "$URL_FILE" ]]; then
  URL="$(cat "$URL_FILE")"
  echo ""
  echo "=============================================="
  echo "  Console gestion en ligne :"
  echo "  $URL"
  echo "=============================================="
  echo "$URL" >"$GESTION/agentic/web_console/PUBLIC_URL.txt"
else
  echo "[web_console] URL tunnel non detectee — voir $LOGDIR/tunnel.log"
  tail -30 "$LOGDIR/tunnel.log" || true
  exit 1
fi
