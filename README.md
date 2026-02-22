# Memo-Rize: A Computational Memory Layer for Multi-Agent Systems

Memo-Rize is a unified hosted memory backend for agent workflows.
It supports **Claude Code**, **Codex**, and **OpenClaw** through one API and one write pipeline.

This project is **host-agnostic**: run it on a NAS, VM, bare-metal Linux host, or any machine that can run Python services.

## What Memo-Rize solves

Most agent setups fragment memory across tools, sessions, and machines.
Memo-Rize centralizes memory so all agents can:

- retrieve shared context (`/retrieve`),
- enqueue memory events (`/events`),
- consolidate durable memory with a single writer,
- inspect and govern memory through admin endpoints and graph UI.

## Design principles

- **Single source of truth**: one hosted memory runtime.
- **Single writer**: worker lock + queued writes to avoid corruption.
- **Fail-open for tasks**: if memory is down, agents can continue their main task.
- **Hybrid retrieval**: lexical + vector + rerank flow.
- **Auditable governance**: versioning, forget/restore, relation compaction, graph inspection.

## High-level architecture

```text
Agents (Claude / Codex / OpenClaw)
  -> POST /retrieve, POST /events
  -> memory-api (FastAPI)
  -> SQLite WAL queue
  -> memory-worker (single writer)
  -> core pipeline (retrieve/embed/consolidate)
  -> notes + indexes + graph cache + memory nodes/edges
```

## Repository layout

- `nas_memory/`: hosted runtime (API, worker, DB schema, security, graph UI, burn-in, systemd units).
- `nas_memory/core/`: canonical core scripts.
  - `nas_memory/core/vault_retrieve.py`
  - `nas_memory/core/process_queue.py`
  - `nas_memory/core/vault_embed.py`
  - `nas_memory/core/runtime_config.py`
- `vault_retrieve.py`, `process_queue.py`, `vault_embed.py`: backward-compatible root shims.
- `legacy_local/`: archived local-only pipeline (read-only reference).
- `tests/`: root compatibility/core tests.
- `nas_memory/tests/`: runtime/admin/relation tests.

## Public API (stable)

- `POST /retrieve`
- `POST /events`
- `GET /health`
- `POST /admin/reindex`
- `GET /admin/graph`
- `GET /admin/graph/ui`

Admin memory governance endpoints:

- `POST /admin/memory/forget`
- `POST /admin/memory/restore`
- `POST /admin/memory/upsert`
- `GET /admin/profile`
- `POST /admin/profile/compact`
- `POST /admin/relations/compact`
- `GET /admin/relations/stats`

Auth: `Authorization: Bearer <MEMORY_API_TOKEN>`.

## Event model (`POST /events`)

Supported `event_type` values:

- `turn`
- `session_stop`
- `note_add`
- `memory_forget`
- `memory_restore`
- `memory_upsert`
- `profile_compact`
- `relation_compact`

Core validations:

- `session_stop` requires `payload.conversation_text`
- `note_add` requires `payload.note_id` and `payload.note_content`

## Quick start (hosted runtime)

```bash
git clone <your-repo-url> memo-rize
cd memo-rize

python3 -m venv .venv
source .venv/bin/activate
pip install -r nas_memory/requirements.txt
```

Set required environment variable:

```bash
export MEMORY_API_TOKEN="<strong-random-token>"
```

Optional (recommended) variables:

- `MEMORY_API_HOST` (default `0.0.0.0`)
- `MEMORY_API_PORT` (default `8766`)
- `MEMORY_ROOT` (runtime root path)
- `MEMORY_CORE_CONFIG` (optional file override path)
- relation/profile tuning flags (see `nas_memory/README.md`)

## Run services

```bash
./nas_memory/run-api.sh
```

```bash
./nas_memory/run-worker.sh
```

## systemd (production)

```bash
mkdir -p ~/.config/systemd/user
cp nas_memory/systemd/memory-api.service ~/.config/systemd/user/
cp nas_memory/systemd/memory-worker.service ~/.config/systemd/user/
cp nas_memory/systemd/memory-profile-compact.service ~/.config/systemd/user/
cp nas_memory/systemd/memory-profile-compact.timer ~/.config/systemd/user/
cp nas_memory/systemd/memory-relation-compact.service ~/.config/systemd/user/
cp nas_memory/systemd/memory-relation-compact.timer ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now memory-api.service memory-worker.service
systemctl --user enable --now memory-profile-compact.timer memory-relation-compact.timer
```

## Agent integrations

### Claude Code

Use thin hooks that only call hosted endpoints:

- retrieve hook -> `POST /retrieve`
- stop hook -> `POST /events` (`session_stop`)

### Codex

Use MCP bridge in `nas_memory/mcp_memory/`.
Example `~/.codex/config.toml` entry:

```toml
[mcp_servers.memory]
type = "stdio"
command = "ssh"
args = ["<host-alias>", "bash '/path/to/memo-rize/nas_memory/mcp_memory/run-mcp.sh'"]
```

### OpenClaw

Configure plugin/hooks to call:

- `POST /retrieve`
- `POST /events`

## Operations and observability

Health check:

```bash
curl -sS -H "Authorization: Bearer $MEMORY_API_TOKEN" \
  "http://127.0.0.1:${MEMORY_API_PORT:-8766}/health"
```

Graph UI:

```bash
open "http://127.0.0.1:${MEMORY_API_PORT:-8766}/admin/graph/ui?token=$MEMORY_API_TOKEN"
```

Relation compaction stats:

```bash
curl -sS -H "Authorization: Bearer $MEMORY_API_TOKEN" \
  "http://127.0.0.1:${MEMORY_API_PORT:-8766}/admin/relations/stats"
```

## Burn-in and rollout tools

Burn-in toolkit lives in `nas_memory/burnin/`.

- Pre-flight: `--duration-hours 0.5`
- Strict run: `--duration-hours 72 --mode mixed --gate strict`
- Orchestrated rollout: `run-shadow-then-write.sh` (24h shadow -> 72h write)

See full operational details in `nas_memory/burnin/README.md`.

## Testing

Run core compatibility tests:

```bash
python3 -m unittest tests.test_runtime_compat tests.test_core
```

Run runtime test suite:

```bash
python3 -m unittest discover nas_memory/tests
```

## Compatibility and migration notes

- Root scripts are retained as shims for backward compatibility.
- Canonical core paths are now under `nas_memory/core/`.
- `legacy_local/` remains archive-only and is not the recommended production path.

## Additional documentation

- Hosted runtime guide: `nas_memory/README.md`
- Burn-in guide: `nas_memory/burnin/README.md`
- Legacy archive: `legacy_local/README.md`
