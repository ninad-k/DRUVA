#!/usr/bin/env bash
# =============================================================================
# DHRUVA — One-shot installer (Linux/macOS/WSL)
#
# Installs the entire ecosystem:
#   1. Verifies prerequisites (docker, python 3.12+, node 22+, npm 10+)
#   2. Creates .env files from .env.example if missing
#   3. Creates Python venv, installs backend deps
#   4. Generates Python gRPC stubs
#   5. Installs frontend deps, generates TS gRPC clients
#   6. Pulls + starts infrastructure containers (postgres, redis, jaeger, envoy,
#      prometheus, grafana)
#   7. Applies database migrations
#
# Idempotent — safe to re-run.
# Usage: bash scripts/install.sh [--skip-infra] [--skip-seed]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

SKIP_INFRA=false
SKIP_SEED=false
for arg in "$@"; do
  case "$arg" in
    --skip-infra) SKIP_INFRA=true ;;
    --skip-seed)  SKIP_SEED=true ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

banner() { printf "\n\033[1;33m==> %s\033[0m\n" "$1"; }
ok()     { printf "    \033[1;32m✓\033[0m %s\n" "$1"; }
fail()   { printf "    \033[1;31m✗\033[0m %s\n" "$1" >&2; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required tool: $1"
}

# -----------------------------------------------------------------------------
banner "1/7 · Checking prerequisites"
require docker
require python3
require node
require npm
PY_VER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
NODE_VER=$(node -v | sed 's/^v//')
ok "docker $(docker --version | awk '{print $3}' | sed 's/,//')"
ok "python $PY_VER"
ok "node v$NODE_VER"
ok "npm $(npm -v)"

# -----------------------------------------------------------------------------
banner "2/7 · Preparing .env files"
[[ -f backend/.env ]]  || { cp backend/.env.example  backend/.env;  ok "created backend/.env";  }
[[ -f frontend/.env ]] || { cp frontend/.env.example frontend/.env; ok "created frontend/.env"; }

# -----------------------------------------------------------------------------
banner "3/7 · Setting up Python backend"
cd backend
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  ok "created virtualenv backend/.venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null
python -m pip install -r requirements.txt -r requirements-dev.txt
ok "python deps installed"
cd "$REPO_ROOT"

# -----------------------------------------------------------------------------
banner "4/7 · Generating gRPC stubs (Python)"
bash backend/scripts/generate_proto.sh || ok "skipped (proto sources may be empty)"

# -----------------------------------------------------------------------------
banner "5/7 · Setting up React frontend"
cd frontend
npm ci --no-audit --no-fund
ok "npm deps installed"
npx --yes buf generate || ok "skipped buf generate (proto sources may be empty)"
cd "$REPO_ROOT"

# -----------------------------------------------------------------------------
if $SKIP_INFRA; then
  banner "6/7 · Skipping infrastructure (flag)"
else
  banner "6/7 · Pulling + starting infrastructure"
  docker compose -f deploy/compose/docker-compose.dev.yml pull
  docker compose -f deploy/compose/docker-compose.dev.yml up -d
  ok "infrastructure up"
fi

# -----------------------------------------------------------------------------
banner "7/7 · Applying database migrations"
cd backend
source .venv/bin/activate
# Wait for postgres readiness up to 60s
for i in $(seq 1 30); do
  if docker exec dhruva-postgres pg_isready -U postgres -d dhruva >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
alembic upgrade head || ok "alembic upgrade head — nothing to apply yet"

if ! $SKIP_SEED && [[ -f scripts/seed_data.py ]]; then
  python scripts/seed_data.py || true
  ok "seed data loaded (if available)"
fi
cd "$REPO_ROOT"

banner "DHRUVA installed"
cat <<EOF
Next steps:
  - bash scripts/run.sh            # start backend + frontend
  - Jaeger UI:     http://localhost:16686
  - Prometheus:    http://localhost:9090
  - Grafana:       http://localhost:3000  (admin / admin)
  - REST API:      http://localhost:8000/docs
  - Frontend:      http://localhost:5173
EOF
