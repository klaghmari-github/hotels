#!/usr/bin/env bash
# Commit + push si le dépôt hotels a des changements.
# Safe pour une boucle 10 min : ne fait rien si working tree clean.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Ne pas committer des artefacts purement locaux/runtime (logs, pids)
EXCLUDE=(
  'accor/data/dev_console/*.pid'
  'accor/data/dev_console/*.log'
  'accor/data/dev_console/chat.jsonl'
  '**/__pycache__/**'
  '**/*.pyc'
)

status="$(git status --porcelain 2>/dev/null || true)"
if [[ -z "${status// }" ]]; then
  echo "[gitpush] rien à committer ($(date -Iseconds))"
  exit 0
fi

# stage all (respecte .gitignore)
git add -A

# drop staged pure noise if still present
for pat in "${EXCLUDE[@]}"; do
  git reset -q -- "$pat" 2>/dev/null || true
done

# re-check after unstage noise
if git diff --cached --quiet 2>/dev/null; then
  echo "[gitpush] seuls des fichiers bruit — skip ($(date -Iseconds))"
  exit 0
fi

MSG="${GITPUSH_MSG:-checkpoint: $(date -Iseconds)}"
git commit -m "$MSG" || {
  echo "[gitpush] commit vide / refusé"
  exit 0
}

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
# origin = gitlab, github = github (comme historique du projet)
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
