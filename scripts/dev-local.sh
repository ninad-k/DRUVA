#!/usr/bin/env bash
# =============================================================================
# DHRUVA — Docker-free dev infrastructure for macOS (Homebrew).
#
# Installs/starts PostgreSQL 18 + TimescaleDB and Redis as Homebrew services,
# creates the `dhruva` role/database from backend/.env, applies migrations and
# seeds the admin + demo users. Idempotent; safe to re-run.
#
# Usage: bash scripts/dev-local.sh [--skip-seed]
# Then:  bash scripts/run.sh --no-docker
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

SKIP_SEED=false
for arg in "$@"; do
  case "$arg" in
    --skip-seed) SKIP_SEED=true ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

banner() { printf "\n\033[1;33m==> %s\033[0m\n" "$1"; }
ok()     { printf "    \033[1;32m✓\033[0m %s\n" "$1"; }
fail()   { printf "    \033[1;31m✗\033[0m %s\n" "$1" >&2; exit 1; }

command -v brew >/dev/null 2>&1 || fail "Homebrew is required (https://brew.sh)"

PG_FORMULA="postgresql@18"
PG_PREFIX="$(brew --prefix)/opt/${PG_FORMULA}"
PG_DATA="$(brew --prefix)/var/${PG_FORMULA}"
PSQL="${PG_PREFIX}/bin/psql"

banner "1/5 · Installing packages"
brew list --formula "$PG_FORMULA" >/dev/null 2>&1 || brew install "$PG_FORMULA"
brew list --formula redis >/dev/null 2>&1 || brew install redis
if ! brew list --formula timescaledb >/dev/null 2>&1; then
  brew tap timescale/tap
  brew install timescale/tap/timescaledb
  # Copies the extension into the Postgres lib/share dirs.
  timescaledb_move.sh
fi
ok "postgresql@18, timescaledb, redis installed"

banner "2/5 · Enabling TimescaleDB"
if ! grep -qE "^shared_preload_libraries\s*=.*timescaledb" "$PG_DATA/postgresql.conf"; then
  if grep -qE "^#?shared_preload_libraries" "$PG_DATA/postgresql.conf"; then
    sed -i '' -E "s/^#?shared_preload_libraries\s*=.*/shared_preload_libraries = 'timescaledb'/" "$PG_DATA/postgresql.conf"
  else
    echo "shared_preload_libraries = 'timescaledb'" >> "$PG_DATA/postgresql.conf"
  fi
  ok "added timescaledb to shared_preload_libraries"
fi

banner "3/5 · Starting services"
brew services start "$PG_FORMULA" >/dev/null
brew services restart "$PG_FORMULA" >/dev/null   # pick up shared_preload_libraries
brew services start redis >/dev/null
for _ in $(seq 1 30); do
  "$PG_PREFIX/bin/pg_isready" -q && break
  sleep 1
done
"$PG_PREFIX/bin/pg_isready" -q || fail "Postgres did not become ready"
ok "postgres and redis running"

banner "4/5 · Creating role + database"
[[ -f backend/.env ]] || { cp backend/.env.example backend/.env; ok "created backend/.env"; }
DB_URL="$(grep -E '^DHRUVA_DB_URL=' backend/.env | cut -d= -f2-)"
DB_USER="$(echo "$DB_URL" | sed -E 's#.*://([^:]+):.*#\1#')"
DB_PASS="$(echo "$DB_URL" | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')"
DB_NAME="$(echo "$DB_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
"$PSQL" -d postgres -q -v ON_ERROR_STOP=1 -c \
  "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}') THEN CREATE ROLE \"${DB_USER}\" LOGIN SUPERUSER PASSWORD '${DB_PASS}'; END IF; END \$\$;"
"$PSQL" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || "$PSQL" -d postgres -q -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${DB_USER}\""
ok "database ${DB_NAME} ready"

banner "5/5 · Migrating + seeding"
(
  cd backend
  # shellcheck disable=SC1091
  source .venv/bin/activate
  alembic upgrade head
  if ! $SKIP_SEED; then
    python scripts/seed_data.py
    python -m app.scripts.seed_demo
  fi
)
ok "done — start the app with: bash scripts/run.sh --no-docker"
