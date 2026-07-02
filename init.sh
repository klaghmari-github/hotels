#!/usr/bin/env bash
# init.sh — CONSTRUIT tout (extraction Excel, targets, modèle, évaluation).
# run.sh ne fait que consommer les artefacts produits ici.
# Les tests unitaires sont dans test.sh (pas lancés ici).
#
# Usage:
#   ./init.sh
#   ./init.sh --skip-train
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

SKIP_TRAIN=0

for arg in "$@"; do
  case "$arg" in
    --skip-train) SKIP_TRAIN=1 ;;
    -h|--help)
      echo "Usage: ./init.sh [--skip-train]"
      echo "Tests unitaires : ./test.sh"
      exit 0
      ;;
    *)
      echo "Option inconnue: $arg" >&2
      exit 1
      ;;
  esac
done

log()  { printf '\033[1;34m[init]\033[0m %s\n' "$*"; }

log "Racine: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 introuvable" >&2
  exit 1
fi

VENV="$ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
  log "Création .venv"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip wheel setuptools -q
python -m pip install -r "$ROOT/requirements.txt" -q

for dir in "$ROOT/data/reference" "$ROOT/data/processed" "$ROOT/rod_ia/artifacts" "$ROOT/rod_ia/feature_store/hotels"; do
  mkdir -p "$dir"
done

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

log "Pipeline init: extraction Excel + targets + feature store pivots"
TRAIN_FLAG=""
if [[ "$SKIP_TRAIN" -eq 1 ]]; then
  TRAIN_FLAG="--skip-train"
fi
python -m rod_ia.pipelines.run_init $TRAIN_FLAG

log "Génération documentation code web"
python "$ROOT/scripts/generate_code_docs.py"

log "Smoke test API (rapide)"
python - <<'PY'
from rod_ia.api.app_factory import create_app
app = create_app()
client = app.test_client()
assert client.get("/health").status_code == 200
sim = client.post("/api/simulate", json={
    "identity": {"hotel_name": "Ibis budget Nice", "city": "Nice"},
    "operating": {"nb_chambres": 129, "taux_occupation": 0.8, "guests_per_chambre": 1.7},
})
assert sim.status_code == 200, sim.data
print("API OK")
PY

log "Init terminé. Lancer l'app: ./run.sh"
log "Tests unitaires: ./test.sh"
log "Documentation: http://127.0.0.1:5000/docs"