#!/usr/bin/env bash
# run.sh — CONSOMME uniquement (serveur web + artefacts de init.sh).
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

HOST="127.0.0.1"
PORT="5000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="${2:?}"; shift 2 ;;
    --port) PORT="${2:?}"; shift 2 ;;
    -h|--help)
      echo "Usage: ./run.sh [--host ADDR] [--port PORT]"
      echo "Prérequis: ./init.sh"
      exit 0
      ;;
    *) echo "Option inconnue: $1" >&2; exit 1 ;;
  esac
done

VENV="$ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
  echo "[run] .venv absent — exécutez ./init.sh" >&2
  exit 1
fi

if [[ ! -f "$ROOT/rod_ia/artifacts/model.joblib" ]]; then
  echo "[run] model.joblib absent — exécutez ./init.sh" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[run] ROD-IA → http://${HOST}:${PORT}"
echo "[run] Docs code → http://${HOST}:${PORT}/docs"
echo "[run] Ctrl+C pour arrêter"

exec python -c "
from rod_ia.api.app_factory import create_app
app = create_app()
app.run(host='${HOST}', port=${PORT}, debug=True)
"