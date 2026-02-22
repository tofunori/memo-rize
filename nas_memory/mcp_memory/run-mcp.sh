#!/bin/bash
set -euo pipefail
cd /volume1/Services/mcp/memory

# Optional local MCP env first.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Fallback to shared memory env if needed.
if [ -f /volume1/Services/memory/.env ]; then
  set -a
  # shellcheck disable=SC1091
  source /volume1/Services/memory/.env
  set +a
fi

# Safe defaults for local hosted memory runtime.
export MEMORY_API_URL="${MEMORY_API_URL:-http://127.0.0.1:8876}"
exec /volume1/Services/mcp/ragdoc/ragdoc-env-new/bin/python3 src/server.py
