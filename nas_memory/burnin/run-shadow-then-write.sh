#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="$ROOT_DIR/.venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

ENV_FILE="${MEMORY_ENV_FILE:-$ROOT_DIR/.env}"
API_URL="${MEMORY_API_URL:-http://127.0.0.1:8876}"
BASE_OUT="${MEMORY_BURNIN_OUT_ROOT:-$ROOT_DIR/state/burnin}"
RUN_TAG="${RUN_TAG:-prod-rollout-$(date -u +%Y%m%d-%H%M%S)}"
RUN_ROOT="$BASE_OUT/$RUN_TAG"
SHADOW_ROOT="$RUN_ROOT/shadow24"
WRITE_ROOT="$RUN_ROOT/write72"
LOG_DIR="$RUN_ROOT/logs"
mkdir -p "$SHADOW_ROOT" "$WRITE_ROOT" "$LOG_DIR"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_DIR/rollout.log"
}

set_env_key() {
  local key="$1"
  local value="$2"
  "$PYTHON_BIN" - "$ENV_FILE" "$key" "$value" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = []
if env_path.exists():
    lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
out = []
found = False
for line in lines:
    raw = line.strip()
    if raw.startswith(f"{key}="):
        out.append(f"{key}={value}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"{key}={value}")
env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

restart_services() {
  systemctl --user restart memory-api.service memory-worker.service
  sleep 2
}

latest_run_dir() {
  local root="$1"
  find "$root" -mindepth 1 -maxdepth 1 -type d -print | sort | tail -n 1
}

wait_for_collector() {
  local duration_hours="$1"
  local out_root="$2"
  local label="$3"
  local log_file="$LOG_DIR/${label}.log"

  log "start collector label=$label duration_h=$duration_hours out_root=$out_root"
  "$PYTHON_BIN" nas_memory/burnin/collector.py \
    --duration-hours "$duration_hours" \
    --mode mixed \
    --gate strict \
    --api-url "$API_URL" \
    --out-root "$out_root" \
    >"$log_file" 2>&1

  local run_dir
  run_dir="$(latest_run_dir "$out_root")"
  if [ -z "$run_dir" ]; then
    log "collector produced no run_dir label=$label"
    return 2
  fi
  log "collector finished label=$label run_dir=$run_dir"
  printf '%s\n' "$run_dir"
}

check_gate() {
  local run_dir="$1"
  "$PYTHON_BIN" - "$run_dir/passfail.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("missing-passfail")
    sys.exit(2)
data = json.loads(path.read_text(encoding="utf-8"))
ok = bool(data.get("overall_pass", False))
print("pass" if ok else "fail")
sys.exit(0 if ok else 1)
PY
}

log "run_tag=$RUN_TAG env_file=$ENV_FILE api_url=$API_URL"

log "phase=shadow set MEMORY_RELATION_WRITE=false"
set_env_key "MEMORY_RELATION_ENABLE" "true"
set_env_key "MEMORY_RELATION_WRITE" "false"
restart_services

SHADOW_RUN_DIR="$(wait_for_collector 24 "$SHADOW_ROOT" "shadow24")"
SHADOW_GATE="$(check_gate "$SHADOW_RUN_DIR" || true)"
log "phase=shadow gate=$SHADOW_GATE run_dir=$SHADOW_RUN_DIR"

if [ "$SHADOW_GATE" != "pass" ]; then
  log "shadow gate failed; keeping MEMORY_RELATION_WRITE=false and stopping rollout"
  exit 3
fi

log "phase=write enable MEMORY_RELATION_WRITE=true"
set_env_key "MEMORY_RELATION_WRITE" "true"
restart_services

WRITE_RUN_DIR="$(wait_for_collector 72 "$WRITE_ROOT" "write72")"
WRITE_GATE="$(check_gate "$WRITE_RUN_DIR" || true)"
log "phase=write gate=$WRITE_GATE run_dir=$WRITE_RUN_DIR"

log "build manual audit sample (40 edges)"
"$PYTHON_BIN" nas_memory/burnin/audit_relations_sample.py \
  --db-path "$ROOT_DIR/state/memory_queue.db" \
  --out-dir "$WRITE_RUN_DIR" \
  --sample-size 40 \
  >"$LOG_DIR/relation-audit.log" 2>&1 || true

log "rollout complete; write_gate=$WRITE_GATE"
