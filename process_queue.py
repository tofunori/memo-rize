#!/usr/bin/env python3
"""
process_queue.py — Async worker for auto_remember.
Processes tickets dropped by enqueue.py.
Triggered by launchd WatchPaths on the queue directory.
Uses Fireworks (kimi-k2) — latency doesn't matter here, quality does.
"""

import json
import os
import re
import subprocess
import sys
import traceback
from datetime import date
from pathlib import Path

# Load config from same directory as this script
sys.path.insert(0, str(Path(__file__).parent))
try:
    from config import (
        VAULT_NOTES_DIR, LOG_FILE, ENV_FILE, QUEUE_DIR, QDRANT_PATH,
        DEDUP_THRESHOLD, FIREWORKS_BASE_URL, FIREWORKS_MODEL,
    )
    VAULT_NOTES_DIR = Path(VAULT_NOTES_DIR)
    LOG_FILE = Path(LOG_FILE)
    ENV_FILE = Path(ENV_FILE)
    QUEUE_DIR = Path(QUEUE_DIR)
    QDRANT_PATH = Path(QDRANT_PATH)
    HOOKS_DIR = Path(ENV_FILE).parent
except ImportError:
    print("ERROR: config.py not found. Copy config.example.py to config.py and edit paths.", file=sys.stderr)
    sys.exit(1)

PROCESSED_DIR = QUEUE_DIR / "processed"
COLLECTION = "vault_notes"

TODAY = date.today().isoformat()


def log(msg: str):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{TODAY}] {msg}\n")
    except Exception:
        pass


def load_env_file() -> dict:
    env = {}
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def get_embed_clients():
    """Returns (cohere.ClientV2, QdrantClient) or (None, None) if unavailable."""
    try:
        import cohere
        from qdrant_client import QdrantClient
    except ImportError:
        return None, None

    env = load_env_file()
    api_key = env.get("COHERE_API_KEY") or os.environ.get("COHERE_API_KEY", "")
    if not api_key or api_key.startswith("<"):
        return None, None
    if not QDRANT_PATH.exists():
        return None, None

    try:
        co = cohere.ClientV2(api_key)
        qd = QdrantClient(path=str(QDRANT_PATH))
        existing = {c.name for c in qd.get_collections().collections}
        if COLLECTION not in existing:
            return None, None
        return co, qd
    except Exception as e:
        log(f"EMBED clients error: {e}")
        return None, None


def check_semantic_dup(content: str) -> tuple[bool, str]:
    """Returns (True, target_id) if similar content already exists in Qdrant."""
    try:
        co, qd = get_embed_clients()
        if co is None:
            return False, ""
        resp = co.embed(
            model="embed-multilingual-v3.0",
            texts=[content[:500]],
            input_type="search_query",
            embedding_types=["float"],
        )
        response = qd.query_points(
            collection_name=COLLECTION,
            query=resp.embeddings.float_[0],
            limit=1,
            score_threshold=DEDUP_THRESHOLD,
        )
        if response.points:
            return True, response.points[0].payload.get("note_id", "")
    except Exception as e:
        log(f"DEDUP error: {e}")
    return False, ""


def upsert_note_async(note_id: str):
    """Runs vault_embed.py in background to upsert a note into Qdrant."""
    try:
        script = str(HOOKS_DIR / "vault_embed.py")
        subprocess.Popen(
            ["python3", script, "--note", note_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log(f"EMBED async upsert launched: {note_id}")
    except Exception as e:
        log(f"EMBED async upsert error: {e}")


def extract_conversation(jsonl_path: str, max_chars: int = 40000) -> tuple[str, int]:
    turns = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    if event.get("type") not in ("user", "assistant"):
                        continue
                    msg = event.get("message", {})
                    role = msg.get("role", event.get("type", "unknown"))
                    content = msg.get("content", "")

                    if isinstance(content, str) and content.strip():
                        turns.append(f"{role.upper()}: {content[:2000]}")
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    turns.append(f"{role.upper()}: {text[:2000]}")
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        log(f"Error reading transcript: {e}")

    return "\n\n".join(turns)[:max_chars], len(turns)


def get_existing_notes_summary(notes_dir: Path, limit: int = 80) -> str:
    lines = []
    try:
        for f in sorted(notes_dir.glob("*.md")):
            if f.name.startswith(".") or f.name.startswith("_"):
                continue
            try:
                text = f.read_text(encoding="utf-8")[:400]
                desc_m = re.search(r'^description:\s*(.+)$', text, re.MULTILINE)
                title_m = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
                if desc_m:
                    lines.append(f"- {f.stem}: {desc_m.group(1)[:100]}")
                elif title_m:
                    lines.append(f"- {f.stem}: {title_m.group(1)[:100]}")
                else:
                    lines.append(f"- {f.stem}")
            except Exception:
                lines.append(f"- {f.stem}")
            if len(lines) >= limit:
                break
    except Exception as e:
        log(f"Error listing notes: {e}")
    return "\n".join(lines)


def extract_facts_with_llm(conversation: str, existing_notes: str) -> list:
    try:
        from openai import OpenAI
    except ImportError:
        log("openai package not installed, skipping")
        return []

    env = load_env_file()
    api_key = env.get("FIREWORKS_API_KEY") or os.environ.get("FIREWORKS_API_KEY")
    if not api_key:
        log("FIREWORKS_API_KEY missing, skipping")
        return []

    client = OpenAI(api_key=api_key, base_url=FIREWORKS_BASE_URL)

    prompt = f"""You are a personal memory agent for the owner of this knowledge vault.

Extract 0-15 DURABLE atomic facts from this Claude Code session.

STRICT RULES:
- Capture everything durable: technical decisions, system configs, solutions to problems, discovered preferences, established workflows, insights about any project, learned facts, configured tools
- Domain doesn't matter: thesis, NAS, scripts, courses, infrastructure, etc.
- Ignore: temporary debugging without resolution, casual conversation, reformulations without new content, intermediate steps
- Title = testable proposition ("X does Y" — not a generic label)
- Maximum 15 notes. Zero if nothing truly durable.

RELATION TYPES:
- NEW: entirely new fact, absent from existing notes
- UPDATES:<note_id>: replaces existing info (e.g. threshold changed, value corrected)
- EXTENDS:<note_id>: adds detail without replacing (e.g. extra detail on existing method)

Existing notes in the vault:
{existing_notes}

RESPONSE FORMAT — JSON array only, no surrounding text:
[
  {{
    "note_id": "kebab-case-slug",
    "relation": "NEW",
    "documentDate": "{TODAY}",
    "eventDate": null,
    "content": "---\\ndescription: [~150 chars, mechanism or scope]\\ntype: decision|result|method|concept|context|argument|module\\ncreated: {TODAY}\\nconfidence: experimental\\n---\\n\\n# Title as a proposition\\n\\nNote body...\\n\\n## Links\\n\\n- [[related-note]]"
  }}
]

For EXTENDS, "content" is the text to append (not a full note).
For UPDATES, "content" is the complete revised note.

If zero memorable notes: []

SESSION CONVERSATION:
{conversation}"""

    raw = ""
    try:
        response = client.chat.completions.create(
            model=FIREWORKS_MODEL,
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.choices[0].message.content.strip()
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)

        log(f"LLM response ({len(raw)} chars): {raw[:300]}")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []

    except json.JSONDecodeError as e:
        log(f"Invalid JSON from LLM: {e} — raw: {raw[:300]}")
        return []
    except Exception as e:
        log(f"Fireworks API error: {e}")
        return []


def write_note(note_id: str, content: str, relation: str):
    notes_dir = VAULT_NOTES_DIR

    if relation.startswith("UPDATES:"):
        target_id = relation.split(":", 1)[1].strip()
        target_path = notes_dir / f"{target_id}.md"
        if target_path.exists():
            target_path.write_text(content, encoding="utf-8")
            log(f"UPDATED  {target_id}")
            return
        log(f"UPDATES target not found ({target_id}), creating as NEW {note_id}")

    elif relation.startswith("EXTENDS:"):
        target_id = relation.split(":", 1)[1].strip()
        target_path = notes_dir / f"{target_id}.md"
        if target_path.exists():
            existing = target_path.read_text(encoding="utf-8")
            extension = f"\n\n---\n*Auto-extension {TODAY}:*\n\n{content}"
            target_path.write_text(existing + extension, encoding="utf-8")
            log(f"EXTENDED {target_id}")
            return
        log(f"EXTENDS target not found ({target_id}), creating as NEW {note_id}")

    note_path = notes_dir / f"{note_id}.md"
    note_path.write_text(content, encoding="utf-8")
    log(f"NEW      {note_id}")


def process_ticket(ticket_path: Path):
    try:
        ticket = json.loads(ticket_path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Error reading ticket {ticket_path.name}: {e}")
        return

    session_id = ticket.get("session_id", "unknown")
    transcript_path = ticket.get("transcript_path", "")

    log(f"--- PROCESSING session={session_id[:8]}")

    if not VAULT_NOTES_DIR.exists():
        log(f"Vault not found: {VAULT_NOTES_DIR}, skipping")
        return

    if not transcript_path or not Path(transcript_path).exists():
        log(f"Transcript not found: {transcript_path}, skipping")
        _archive(ticket_path, session_id)
        return

    conversation, turn_count = extract_conversation(transcript_path)
    log(f"Conversation: {turn_count} turns, {len(conversation)} chars")

    existing_notes = get_existing_notes_summary(VAULT_NOTES_DIR)
    facts = extract_facts_with_llm(conversation, existing_notes)

    if not facts:
        log("No memorable facts extracted")
        _archive(ticket_path, session_id)
        return

    log(f"Facts extracted: {len(facts)}")
    written = 0
    for fact in facts:
        try:
            note_id = fact.get("note_id", "").strip()
            relation = fact.get("relation", "NEW")
            content = fact.get("content", "").strip()
            if not note_id or not content:
                log(f"Invalid fact ignored: {fact}")
                continue

            # Semantic dedup: only for NEW facts
            if relation == "NEW":
                is_dup, target_id = check_semantic_dup(content)
                if is_dup and target_id:
                    relation = f"EXTENDS:{target_id}"
                    log(f"DEDUP: {note_id} → EXTENDS:{target_id}")

            write_note(note_id, content, relation)
            written += 1

            # Incremental upsert into Qdrant after writing
            actual_id = note_id
            if relation.startswith("UPDATES:"):
                actual_id = relation.split(":", 1)[1].strip()
            elif relation.startswith("EXTENDS:"):
                actual_id = relation.split(":", 1)[1].strip()
            upsert_note_async(actual_id)

        except Exception as e:
            log(f"Error writing {fact.get('note_id', '?')}: {e}")

    log(f"Notes written: {written}/{len(facts)}")
    _archive(ticket_path, session_id)


def _archive(ticket_path: Path, session_id: str):
    try:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        dest = PROCESSED_DIR / ticket_path.name
        ticket_path.rename(dest)
        log(f"ARCHIVED session={session_id[:8]}")
    except Exception as e:
        log(f"Archive error: {e}")


def main():
    try:
        tickets = [
            f for f in QUEUE_DIR.glob("*.json")
            if f.is_file() and f.parent == QUEUE_DIR
        ]

        if not tickets:
            log("Queue empty, nothing to process")
            sys.exit(0)

        log(f"=== process_queue: {len(tickets)} ticket(s) to process")

        for ticket_path in sorted(tickets, key=lambda f: f.stat().st_mtime):
            session_id = ticket_path.stem
            if (PROCESSED_DIR / ticket_path.name).exists():
                log(f"SKIP (already processed) session={session_id[:8]}")
                ticket_path.unlink(missing_ok=True)
                continue
            process_ticket(ticket_path)

        log("=== process_queue: done")

    except Exception as e:
        log(f"Fatal error in process_queue: {e}\n{traceback.format_exc()}")

    sys.exit(0)


if __name__ == "__main__":
    main()
