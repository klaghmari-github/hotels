#!/usr/bin/env bash
# Commit + push si le dépôt hotels a des changements utiles.
# Boucle 10 min safe : skip si clean ; n'ajoute jamais les gros artefacts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Jamais versionner (même si un add -A les reprendrait)
BLOCK=(
  'accor/duckdb'
  'accor/base.duckdb'
  'accor/bin/cloudflared'
  'accor/data/dev_console'
)

status="$(git status --porcelain 2>/dev/null || true)"
if [[ -z "${status// }" ]]; then
  echo "[gitpush] rien à committer ($(date -Iseconds))"
  exit 0
fi

git add -A

# Déstager les chemins bloqués + bruit runtime
for p in "${BLOCK[@]}"; do
  git reset -q -- "$p" 2>/dev/null || true
  git rm -r --cached -f --ignore-unmatch "$p" 2>/dev/null || true
done
# wildcards duckdb
while IFS= read -r f; do
  [[ -n "$f" ]] || continue
  git reset -q -- "$f" 2>/dev/null || true
done < <(git diff --cached --name-only | grep -E '\.duckdb(\.wal)?$|/duckdb/' || true)

# Refus explicite si un blob > 80 Mo est encore stagé
big=0
while IFS= read -r f; do
  [[ -f "$f" ]] || continue
  sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [[ "$sz" -gt 80000000 ]]; then
    echo "[gitpush] REFUS fichier trop gros stagé: $f ($sz bytes) — unstage"
    git reset -q -- "$f" 2>/dev/null || true
    big=1
  fi
done < <(git diff --cached --name-only --diff-filter=ACMR || true)

if git diff --cached --quiet 2>/dev/null; then
  echo "[gitpush] rien d'utile à committer (bruit/runtime only) ($(date -Iseconds))"
  exit 0
fi

MSG="${GITPUSH_MSG:-checkpoint: $(date -Iseconds)}"
if ! git commit -m "$MSG"; then
  echo "[gitpush] commit vide / refusé"
  exit 0
fi

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
ok=0
if git remote get-url origin >/dev/null 2>&1; then
  if git push -u origin "HEAD:refs/heads/${branch}" 2>&1; then
    echo "[gitpush] origin OK"
    ok=1
  else
    echo "[gitpush] origin FAIL"
  fi
fi
if git remote get-url github >/dev/null 2>&1; then
  if git push -u github "HEAD:refs/heads/${branch}" 2>&1; then
    echo "[gitpush] github OK"
    ok=1
  else
    echo "[gitpush] github FAIL"
  fi
fi
if [[ "$ok" -eq 0 ]]; then
  echo "[gitpush] aucun remote pushé" >&2
  exit 1
fi
echo "[gitpush] done $(date -Iseconds)"
