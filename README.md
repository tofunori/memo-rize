# claude-vault-memory

**Supermemory for Claude Code** — semantic vector index of your notes, active retrieval on every message, intelligent deduplication, and real-time proactive memory.

## Architecture

```
Session start
  └─ SessionStart → vault_retrieve.py
       └─ embed(message) via Cohere API
       └─ HNSW search in local Qdrant → top-3 notes (score > 0.60)
       └─ output → injected into Claude context

During session (v3 — real-time proactive memory)
  └─ Claude detects a durable fact
       └─ vault_add_note(note_id, content)   # writes note to vault
       └─ vault_embed.py --note {note_id}    # indexes in Qdrant immediately
       └─ note retrievable in the next session

End of session (safety net)
  └─ Stop → enqueue.py (< 100ms)

Background worker (launchd WatchPaths)
  └─ process_queue.py
       └─ LLM extraction → 0-5 atomic facts
       └─ check_semantic_dup() — Qdrant dedup (score > 0.85 → EXTENDS)
       └─ writes markdown notes
       └─ individual upsert in Qdrant via vault_embed.py
```

## Versions

| Version | Feature |
|---------|---------|
| v1 | Semantic retrieval at session start |
| v2 | Graph traversal + unlimited extraction |
| v3 | **Real-time proactive memory** — Claude saves facts immediately during session |

## Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Embeddings | Cohere `embed-multilingual-v3.0` | Multilingual (FR/EN), 1024 dims |
| Vector DB | Qdrant **local mode** (disk) | Zero server, HNSW, incremental |
| LLM extraction | Fireworks kimi-k2 | Maximum quality, latency irrelevant |
| Note format | Markdown + YAML frontmatter | Obsidian-compatible, Zettelkasten |

## v3 — Real-time Proactive Memory

The key addition in v3 is a proactive memory pattern inspired by [Supermemory.ai](https://supermemory.ai): Claude saves durable facts **during the session**, without waiting for the end-of-session extraction pass.

### What triggers proactive saving

- A technical decision made (config established, threshold validated, tool chosen)
- A solution found (working command, bug resolved)
- A workflow established (confirmed steps, functional pipeline)
- A fact learned about infrastructure (NAS, scripts, models, APIs)

### What does NOT trigger saving

- Casual conversation, questions/answers without a conclusion
- Intermediate debugging steps without resolution
- Reformulations or clarifications

### How it works

Add this section to your `CLAUDE.md`:

```markdown
**Proactive memory (Supermemory pattern):** without waiting for an explicit request,
save immediately when you identify something clearly durable:
- A technical decision made (config established, threshold validated, tool chosen)
- A solution found (working command, bug resolved)
- A workflow established (confirmed steps, functional pipeline)
- A fact learned about infrastructure (NAS, scripts, models, APIs)

Process:
1. Call `vault_add_note(note_id, content)` — complete atomic note (frontmatter + body + Links)
2. Run `Bash: python3 /path/to/vault_embed.py --note {note_id}`
3. Confirm in one line: "→ saved: [[note_id]]"

Do not interrupt the workflow. Save silently, confirm briefly.
Do NOT save: casual chat, intermediate steps, debugging without resolution.
```

### Why vault_embed_if_note.sh is not enough

The PostToolUse hook `vault_embed_if_note.sh` only triggers on native Write/Edit tool calls — not on MCP `vault_add_note`. That's why `vault_embed.py --note {id}` must be called explicitly after each `vault_add_note`.

## Installation

### Prerequisites

- Python 3.10+
- Cohere API key (free up to 1000 calls/month): [dashboard.cohere.com](https://dashboard.cohere.com/api-keys)
- Claude Code configured with hooks

### Steps

```bash
# 1. Clone
git clone https://github.com/yourname/claude-vault-memory
cd claude-vault-memory

# 2. Copy config
cp config.example.py config.py
# → Edit config.py with your paths

# 3. Run interactive install
bash install.sh
```

### Manual configuration

Edit `config.py` (never committed):

```python
VAULT_NOTES_DIR = "/home/yourname/notes"
QDRANT_PATH = "/home/yourname/.claude/hooks/vault_qdrant"
ENV_FILE = "/home/yourname/.claude/hooks/.env"
```

Add to your `.env`:
```
COHERE_API_KEY=<your-key>
```

### Claude Code settings.json

Add to `~/.claude/settings.json`:

```json
"UserPromptSubmit": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "python3 /path/to/hooks/vault_retrieve.py"
      }
    ]
  }
],
"Stop": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 /path/to/hooks/enqueue.py"
      }
    ]
  }
]
```

### launchd (macOS) — background worker

```bash
# Copy and adapt the plist
cp launchd/com.example.vault-queue-worker.plist \
   ~/Library/LaunchAgents/com.yourname.vault-queue-worker.plist

# Edit paths in the plist, then load
launchctl load ~/Library/LaunchAgents/com.yourname.vault-queue-worker.plist
```

## Usage

### Initial index build

```bash
python3 vault_embed.py
# → EMBED_INDEX upserted: 119 notes → /path/to/vault_qdrant
```

### Test retrieval

```bash
echo '{"prompt":"MODIS albedo quality threshold decision glacier"}' | python3 vault_retrieve.py
# → === Relevant vault notes ===
# → [[decision-qa-threshold]] (decision, 78%) — MODIS albedo QA threshold...
```

### Incremental update

```bash
# After modifying a note
python3 vault_embed.py --note my-modified-note

# Multiple notes
python3 vault_embed.py --notes note-a note-b note-c
```

## Note format

Each markdown note must have a YAML frontmatter:

```markdown
---
description: Short description (~150 chars)
type: concept|context|argument|decision|method|result|module|section
created: 2026-02-20
confidence: experimental|confirmed
---

# The note argues that X does Y

Note body...

## Links

- [[related-note]]
```

## Configurable thresholds

In `config.py`:

| Parameter | Default | Role |
|-----------|---------|------|
| `RETRIEVE_SCORE_THRESHOLD` | 0.60 | Min score to surface a note |
| `RETRIEVE_TOP_K` | 3 | Max number of notes returned |
| `DEDUP_THRESHOLD` | 0.85 | Min score to detect a duplicate |
| `MIN_QUERY_LENGTH` | 20 | Min message length (chars) |

## Logs

All events are logged in `auto_remember.log`:

```
[2026-02-20] EMBED_INDEX upserted: 119 notes
[2026-02-20] RETRIEVE query=45c → 2 notes (threshold 0.6)
[2026-02-20] DEDUP: new-note → EXTENDS:existing-note
[2026-02-20] ENQUEUED session=abc123 turns=12
[2026-02-20] NEW      my-new-note
```

## License

MIT
