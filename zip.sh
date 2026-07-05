#!/usr/bin/env bash
# zip.sh — archive le projet (hors .venv et .pytest_cache).
#
# Usage:
#   ./zip.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ! command -v zip >/dev/null 2>&1; then
  echo "zip introuvable — installez le paquet zip" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d%H%M%S)"
ARCHIVE="${ROOT}/${STAMP}.zip"

zip -r "$ARCHIVE" . \
  -x ".venv/*" \
  -x ".venv/**" \
  -x ".pytest_cache/*" \
  -x ".pytest_cache/**" \
  -x "${STAMP}.zip"

printf 'Archive créée : %s\n' "$ARCHIVE"