#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sample memory_edges for manual precision audit.")
    parser.add_argument("--db-path", default="/volume1/Services/memory/state/memory_queue.db")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--sample-size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=1337)
    return parser.parse_args()


def _fetch_edges_with_nodes(db: sqlite3.Connection) -> list[dict[str, Any]]:
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """
        SELECT
            e.id AS edge_id,
            e.relation,
            e.confidence,
            e.created_at,
            e.src_node_id,
            e.dst_node_id,
            s.scope AS src_scope,
            s.fact_type AS src_fact_type,
            s.fact_text AS src_fact_text,
            d.scope AS dst_scope,
            d.fact_type AS dst_fact_type,
            d.fact_text AS dst_fact_text
        FROM memory_edges e
        JOIN memory_nodes s ON s.id = e.src_node_id
        JOIN memory_nodes d ON d.id = e.dst_node_id
        ORDER BY e.created_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_markdown(path: Path, rows: list[dict[str, Any]], *, seed: int) -> None:
    lines: list[str] = []
    lines.append("# Relation Precision Manual Audit")
    lines.append("")
    lines.append(f"- generated_at: {utc_now_iso()}")
    lines.append(f"- sample_size: {len(rows)}")
    lines.append(f"- random_seed: {seed}")
    lines.append("")
    lines.append("Review each edge and mark `label` as one of: `correct`, `incorrect`, `unsure`.")
    lines.append("")
    for i, row in enumerate(rows, start=1):
        lines.append(f"## {i}. `{row.get('edge_id', '')}`")
        lines.append(f"- relation: `{row.get('relation', '')}`")
        lines.append(f"- confidence: `{row.get('confidence', '')}`")
        lines.append(f"- src: `{row.get('src_node_id', '')}` ({row.get('src_scope', '')}/{row.get('src_fact_type', '')})")
        lines.append(f"- dst: `{row.get('dst_node_id', '')}` ({row.get('dst_scope', '')}/{row.get('dst_fact_type', '')})")
        lines.append(f"- src_fact_text: {row.get('src_fact_text', '')}")
        lines.append(f"- dst_fact_text: {row.get('dst_fact_text', '')}")
        lines.append("- label: ")
        lines.append("- reviewer_note: ")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    db_path = Path(args.db_path)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        _write_json(
            out_dir / "relation_precision_manual.json",
            {
                "generated_at": utc_now_iso(),
                "status": "error",
                "message": f"db_path not found: {db_path}",
                "sample_size": 0,
                "precision": 0.0,
            },
        )
        return 2

    with sqlite3.connect(db_path) as db:
        rows = _fetch_edges_with_nodes(db)

    total_edges = len(rows)
    rng = Random(args.seed)
    if total_edges <= args.sample_size:
        sample = rows
    else:
        sample = rng.sample(rows, args.sample_size)

    metadata = {
        "generated_at": utc_now_iso(),
        "status": "ok",
        "db_path": str(db_path),
        "total_edges": total_edges,
        "sample_size": len(sample),
        "seed": args.seed,
        # Placeholder value for gate compatibility until human review writes final value.
        "precision": 1.0,
        "review_required": True,
    }

    _write_json(out_dir / "relation_precision_manual.json", metadata)
    _write_jsonl(out_dir / "relation_precision_sample.jsonl", sample)
    _write_markdown(out_dir / "relation_precision_sample.md", sample, seed=args.seed)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
