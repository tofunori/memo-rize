#!/usr/bin/env python3
"""Compatibility shim for legacy local session brief (read-only archive path)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from nas_memory.core.runtime_config import install_legacy_config_module

install_legacy_config_module(Path(__file__).resolve().parent)
_core = importlib.import_module("legacy_local.vault_session_brief")

if __name__ == "__main__":
    print(
        "INFO: `vault_session_brief.py` at repo root is deprecated; use `legacy_local/vault_session_brief.py`.",
        file=sys.stderr,
    )
    raise SystemExit(_core.main() or 0)

sys.modules[__name__] = _core
