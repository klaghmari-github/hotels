#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
GESTION="$(cd "$ROOT/.." && pwd)"
LOGDIR="$GESTION/logs/web_console"
for f in api.pid worker.pid tunnel.pid; do
  if [[ -f "$LOGDIR/$f" ]]; then
    pid="$(cat "$LOGDIR/$f" || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "stopped $f pid $pid"
    fi
    rm -f "$LOGDIR/$f"
  fi
done
echo "web_console stopped"
