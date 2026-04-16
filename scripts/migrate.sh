#!/usr/bin/env bash
# Apply or create database migrations.
#   bash scripts/migrate.sh                       # upgrade head
#   bash scripts/migrate.sh --create "add users"  # autogenerate new revision
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate

if [[ "${1:-}" == "--create" ]]; then
  MSG="${2:-revision}"
  alembic revision --autogenerate -m "$MSG"
else
  alembic upgrade head
fi
