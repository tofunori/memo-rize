#!/usr/bin/env python3
"""Compatibility shim for legacy local reflector (read-only archive path)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from nas_memory.core.runtime_config import install_legacy_config_module

install_legacy_config_module(Path(__file__).resolve().parent)
_core = importlib.import_module("legacy_local.vault_reflect")

if __name__ == "__main__":
    print(
        "INFO: `vault_reflect.py` at repo root is deprecated; use `legacy_local/vault_reflect.py`.",
        file=sys.stderr,
    )
    raise SystemExit(_core.main() or 0)

sys.modules[__name__] = _core
