#!/usr/bin/env bash
# Build production Docker images for backend and frontend.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

VERSION="${DHRUVA_VERSION:-latest}"

echo "==> Building dhruva/backend:$VERSION"
docker build -t "dhruva/backend:$VERSION" -f backend/Dockerfile backend

echo "==> Building dhruva/frontend:$VERSION"
docker build -t "dhruva/frontend:$VERSION" -f frontend/Dockerfile frontend

echo "==> Done. Images:"
docker images | grep -E "dhruva/(backend|frontend)" | head -4
