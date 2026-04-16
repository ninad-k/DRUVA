#!/usr/bin/env bash
# Run backend pytest + frontend vitest/playwright.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Backend tests"
(
  cd backend
  # shellcheck disable=SC1091
  source .venv/bin/activate
  ruff check .
  mypy app/core app/brokers || true
  pytest
)

echo "==> Frontend tests"
(
  cd frontend
  npm run lint
  npm run typecheck
  npm run test
)
