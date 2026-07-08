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

# shellcheck disable=SC1091
source "$VENV/bin/activate"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -f "$ROOT/rod_ia/artifacts/model.joblib" ]]; then
  if [[ -f "$ROOT/data/processed/dataset_meta.json" ]]; then
    echo "[run] model.joblib absent — entraînement automatique..."
    python -m rod_ia.pipelines.train_model
  else
    echo "[run] model.joblib et dataset absents — exécutez ./init.sh" >&2
    exit 1
  fi
fi

echo "[run] ROD-IA → http://${HOST}:${PORT}"
echo "[run] Docs code → http://${HOST}:${PORT}/docs"
echo "[run] Ctrl+C pour arrêter"

exec python -c "
from rod_ia.api.app_factory import run
run(mode='user', host='${HOST}', port=${PORT}, open_browser=False)
"