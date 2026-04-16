#!/usr/bin/env bash
# Generate Python gRPC stubs from proto/ into app/api/grpc/_generated/
# Usage: bash backend/scripts/generate_proto.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROTO_DIR="$REPO_ROOT/proto"
OUT_DIR="$REPO_ROOT/backend/app/api/grpc/_generated"

mkdir -p "$OUT_DIR"
touch "$OUT_DIR/__init__.py"

python -m grpc_tools.protoc \
    --proto_path="$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    --pyi_out="$OUT_DIR" \
    $(find "$PROTO_DIR" -name "*.proto")

echo "gRPC Python stubs written to $OUT_DIR"
