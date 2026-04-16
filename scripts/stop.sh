#!/usr/bin/env bash
# Stop DHRUVA local processes. With --all, also tears down infra containers.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "vite"                 2>/dev/null || true
echo "Stopped backend + frontend processes"

if [[ "${1:-}" == "--all" ]]; then
  docker compose -f deploy/compose/docker-compose.dev.yml down
  echo "Infrastructure stopped"
fi
