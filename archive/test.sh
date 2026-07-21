#!/usr/bin/env bash
# test.sh — Lance les tests unitaires (séparé de init.sh).
#
# Usage:
#   ./test.sh
#   ./test.sh tests/test_simulation.py
#   ./test.sh -k recap
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

log() { printf '\033[1;34m[test]\033[0m %s\n' "$*"; }

VENV="$ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
  echo "[test] .venv absent — exécutez ./init.sh d'abord" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

TARGET="${*:-$ROOT/tests/}"
log "pytest $TARGET"
python -m pytest "$TARGET" -q

log "Tests terminés."