#!/usr/bin/env bash
# =============================================================================
# DHRUVA — Start the whole stack locally.
#
# - Ensures dev infra is up (idempotent).
# - Launches backend (uvicorn) + frontend (vite) in parallel.
# - Logs are prefixed so a single terminal is enough.
# - Ctrl+C stops both; infra is left running (use `stop.sh --all` to tear down).
#
# Usage: bash scripts/run.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

banner() { printf "\n\033[1;33m==> %s\033[0m\n" "$1"; }

banner "Ensuring dev infrastructure is up"
docker compose -f deploy/compose/docker-compose.dev.yml up -d

banner "Starting backend (uvicorn) on :8000 and frontend (vite) on :5173"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo
  banner "Shutting down"
  [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

# Backend
(
  cd backend
  # shellcheck disable=SC1091
  source .venv/bin/activate
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
) 2>&1 | sed -u 's/^/[backend]  /' &
BACKEND_PID=$!

# Frontend
(
  cd frontend
  exec npm run dev
) 2>&1 | sed -u 's/^/[frontend] /' &
FRONTEND_PID=$!

wait
