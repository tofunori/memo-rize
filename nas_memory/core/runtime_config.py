from __future__ import annotations

import importlib.util
import os
import types
from pathlib import Path


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str) -> int:
    return int(value.strip())


def _parse_float(value: str) -> float:
    return float(value.strip())


def _load_config_file(config_path: Path) -> types.ModuleType | None:
    if not config_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("memory_core_config_file", config_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _env_aliases(default_env_name: str) -> tuple[str, ...]:
    # Preserve historical names and allow MEMORY_* aliases.
    aliases = [default_env_name]
    if not default_env_name.startswith("MEMORY_"):
        aliases.append(f"MEMORY_{default_env_name}")
    return tuple(aliases)


def _env_get(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value != "":
            return value
    return None


def build_legacy_config_module(repo_root: Path | str) -> types.ModuleType:
    repo_root = Path(repo_root).resolve()
    memory_root = Path(os.environ.get("MEMORY_ROOT", str(repo_root / ".memory_runtime")))
    default_state = memory_root / "state"

    defaults: dict[str, object] = {
        "VAULT_NOTES_DIR": str(memory_root / "notes"),
        "QDRANT_PATH": str(memory_root / "vault_qdrant"),
        "ENV_FILE": str(memory_root / ".env"),
        "QUEUE_DIR": str(memory_root / "queue"),
        "LOG_FILE": str(default_state / "legacy_memory.log"),
        "GRAPH_CACHE_PATH": str(memory_root / "vault_graph_cache.json"),
        "BM25_INDEX_PATH": str(memory_root / "vault_bm25_index.json"),
        "SOURCE_CHUNKS_DIR": str(memory_root / "notes" / "_sources"),
        "FORGET_ARCHIVE_DIR": str(memory_root / "notes" / "_archived"),
        "VOYAGE_EMBED_MODEL": "voyage-4-large",
        "EMBED_DIM": 1024,
        "EMBED_BATCH_SIZE": 128,
        "CLAUDE_EXTRACT_MODEL": "claude-sonnet-4-6",
        "RETRIEVE_SCORE_THRESHOLD": 0.60,
        "RETRIEVE_TOP_K": 3,
        "DEDUP_THRESHOLD": 0.85,
        "MIN_QUERY_LENGTH": 20,
        "MIN_TURNS": 3,
        "MIN_NEW_TURNS": 10,
        "MAX_SECONDARY": 5,
        "MAX_BACKLINKS_PER_NOTE": 3,
        "BFS_DEPTH": 2,
        "BM25_ENABLED": True,
        "RRF_K": 60,
        "BM25_TOP_K": 10,
        "VECTOR_TOP_K": 10,
        "RRF_FINAL_TOP_K": 3,
        "CONFIDENCE_BOOST": 1.2,
        "DECAY_ENABLED": True,
        "DECAY_HALF_LIFE_DAYS": 90,
        "DECAY_FLOOR": 0.3,
        "MAX_CODE_BLOCK_CHARS": 500,
        "RERANK_ENABLED": True,
        "RERANK_MODEL": "rerank-2",
        "RERANK_CANDIDATES": 10,
        "VALIDATION_ENABLED": True,
        "SOURCE_CHUNKS_ENABLED": True,
        "SOURCE_CHUNK_MAX_CHARS": 2000,
        "SOURCE_INJECT_MAX_CHARS": 800,
        "REFLECT_MIN_NOTES": 30,
        "REFLECT_CLUSTER_THRESHOLD": 0.82,
        "REFLECT_STALE_DAYS": 180,
        "FORGET_DEFAULT_TTL_DAYS": {},
    }

    config_path = Path(os.environ.get("MEMORY_CORE_CONFIG", repo_root / "config.py"))
    file_module = _load_config_file(config_path)
    if file_module is not None:
        for key in list(defaults.keys()):
            if hasattr(file_module, key):
                defaults[key] = getattr(file_module, key)

    env_casts: dict[str, object] = {
        "EMBED_DIM": _parse_int,
        "EMBED_BATCH_SIZE": _parse_int,
        "RETRIEVE_TOP_K": _parse_int,
        "MIN_QUERY_LENGTH": _parse_int,
        "MIN_TURNS": _parse_int,
        "MIN_NEW_TURNS": _parse_int,
        "MAX_SECONDARY": _parse_int,
        "MAX_BACKLINKS_PER_NOTE": _parse_int,
        "BFS_DEPTH": _parse_int,
        "RRF_K": _parse_int,
        "BM25_TOP_K": _parse_int,
        "VECTOR_TOP_K": _parse_int,
        "RRF_FINAL_TOP_K": _parse_int,
        "MAX_CODE_BLOCK_CHARS": _parse_int,
        "RERANK_CANDIDATES": _parse_int,
        "SOURCE_CHUNK_MAX_CHARS": _parse_int,
        "SOURCE_INJECT_MAX_CHARS": _parse_int,
        "REFLECT_MIN_NOTES": _parse_int,
        "REFLECT_STALE_DAYS": _parse_int,
        "RETRIEVE_SCORE_THRESHOLD": _parse_float,
        "DEDUP_THRESHOLD": _parse_float,
        "CONFIDENCE_BOOST": _parse_float,
        "DECAY_HALF_LIFE_DAYS": _parse_float,
        "DECAY_FLOOR": _parse_float,
        "REFLECT_CLUSTER_THRESHOLD": _parse_float,
        "BM25_ENABLED": _parse_bool,
        "DECAY_ENABLED": _parse_bool,
        "RERANK_ENABLED": _parse_bool,
        "VALIDATION_ENABLED": _parse_bool,
        "SOURCE_CHUNKS_ENABLED": _parse_bool,
    }

    for key in list(defaults.keys()):
        env_names = _env_aliases(key)
        raw_value = _env_get(*env_names)
        if raw_value is None:
            continue
        caster = env_casts.get(key)
        if caster is None:
            defaults[key] = raw_value
            continue
        try:
            defaults[key] = caster(raw_value)  # type: ignore[misc]
        except Exception:
            # Keep previously resolved value if env is malformed.
            pass

    module = types.ModuleType("config")
    module.__file__ = str(config_path) if config_path.exists() else "<memory-runtime-config>"
    module.__dict__.update(defaults)
    return module


def install_legacy_config_module(repo_root: Path | str) -> types.ModuleType:
    import sys

    existing = sys.modules.get("config")
    if existing is not None and getattr(existing, "__memory_runtime__", False):
        return existing

    module = build_legacy_config_module(repo_root)
    setattr(module, "__memory_runtime__", True)
    sys.modules["config"] = module
    return module
