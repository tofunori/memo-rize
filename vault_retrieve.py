#!/usr/bin/env python3
"""
vault_retrieve.py — UserPromptSubmit hook, active retrieval.

Input stdin : JSON from Claude Code {"prompt": "...", "session_id": "...", ...}
Output      : text injected into Claude context (relevant notes)
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# Load config from same directory as this script
sys.path.insert(0, str(Path(__file__).parent))
try:
    from config import (
        VAULT_NOTES_DIR, QDRANT_PATH, ENV_FILE, LOG_FILE,
        RETRIEVE_SCORE_THRESHOLD as SCORE_THRESHOLD,
        RETRIEVE_TOP_K as TOP_K,
        MIN_QUERY_LENGTH,
    )
    VAULT_NOTES_DIR = Path(VAULT_NOTES_DIR)
    QDRANT_PATH = Path(QDRANT_PATH)
    ENV_FILE = Path(ENV_FILE)
    LOG_FILE = Path(LOG_FILE)
except ImportError:
    print("ERROR: config.py not found. Copy config.example.py to config.py and edit paths.", file=sys.stderr)
    sys.exit(0)

COLLECTION = "vault_notes"
TODAY = date.today().isoformat()
MAX_SECONDARY = 3  # Max connected notes via graph traversal


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


def parse_wiki_links(note_path: Path) -> list:
    """Extract [[links]] from the ## Links section (resolvable slugs only)."""
    try:
        text = note_path.read_text(encoding="utf-8")
        match = re.search(r'## (?:Links|Connexions)\s*(.*?)(?=\n##|\Z)', text, re.DOTALL)
        if not match:
            return []
        section = match.group(1)
        links = re.findall(r'\[\[([^\]]+)\]\]', section)
        # Keep only resolvable slugs: no spaces AND < 60 chars
        return [l.strip() for l in links if len(l.strip()) < 60 and ' ' not in l.strip()]
    except Exception:
        return []


def get_connected_notes(primary_ids: list, max_secondary: int = MAX_SECONDARY) -> list:
    """Returns connected notes (1 graph level) via wiki-links in ## Links section."""
    seen = set(primary_ids)
    connected = []
    for note_id in primary_ids:
        note_path = VAULT_NOTES_DIR / f"{note_id}.md"
        if not note_path.exists():
            continue
        links = parse_wiki_links(note_path)
        for link_id in links:
            if link_id in seen:
                continue
            linked_path = VAULT_NOTES_DIR / f"{link_id}.md"
            if linked_path.exists():
                seen.add(link_id)
                text = linked_path.read_text(encoding="utf-8")[:400]
                desc_m = re.search(r'^description:\s*(.+)$', text, re.MULTILINE)
                type_m = re.search(r'^type:\s*(.+)$', text, re.MULTILINE)
                connected.append({
                    "note_id": link_id,
                    "description": desc_m.group(1).strip() if desc_m else link_id,
                    "type": type_m.group(1).strip() if type_m else "?",
                })
            if len(connected) >= max_secondary:
                break
        if len(connected) >= max_secondary:
            break
    return connected


def main():
    # Read stdin
    try:
        raw = sys.stdin.read().strip()
        data = json.loads(raw) if raw else {}
    except Exception:
        sys.exit(0)

    query = data.get("prompt", "").strip()

    # Guard: message too short
    if len(query) < MIN_QUERY_LENGTH:
        sys.exit(0)

    # Guard: Qdrant index not built yet
    if not QDRANT_PATH.exists():
        sys.exit(0)

    # Guard: COHERE_API_KEY missing
    env = load_env_file()
    api_key = env.get("COHERE_API_KEY") or os.environ.get("COHERE_API_KEY", "")
    if not api_key or api_key.startswith("<"):
        sys.exit(0)

    # Runtime imports (fail silently if packages missing)
    try:
        import cohere
        from qdrant_client import QdrantClient
    except ImportError:
        sys.exit(0)

    try:
        co = cohere.ClientV2(api_key)
        qd = QdrantClient(path=str(QDRANT_PATH))

        # Check collection exists
        existing = {c.name for c in qd.get_collections().collections}
        if COLLECTION not in existing:
            sys.exit(0)

        # Embed query (input_type="search_query" — optimized for retrieval)
        resp = co.embed(
            model="embed-multilingual-v3.0",
            texts=[query[:512]],
            input_type="search_query",
            embedding_types=["float"],
        )
        query_emb = resp.embeddings.float_[0]

        # HNSW search in Qdrant
        response = qd.query_points(
            collection_name=COLLECTION,
            query=query_emb,
            limit=TOP_K,
            score_threshold=SCORE_THRESHOLD,
        )
        results = response.points

        if not results:
            sys.exit(0)

        # Output injected into Claude context
        primary_ids = [r.payload['note_id'] for r in results]
        lines = ["=== Relevant vault notes ==="]
        for r in results:
            p = r.payload
            score_pct = int(r.score * 100)
            lines.append(
                f"[[{p['note_id']}]] ({p.get('type', '?')}, {score_pct}%) — {p.get('description', '')}"
            )

        # Graph traversal: connected notes via ## Links section
        connected = get_connected_notes(primary_ids)
        if connected:
            lines.append("\n=== Connected notes (graph) ===")
            for c in connected:
                lines.append(f"[[{c['note_id']}]] ({c['type']}) — {c['description']}")

        print("\n".join(lines))

        log(f"RETRIEVE query={len(query)}c → {len(results)} notes + {len(connected)} graph (threshold {SCORE_THRESHOLD})")

    except Exception as e:
        log(f"RETRIEVE error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
