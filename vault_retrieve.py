#!/usr/bin/env python3
"""Compatibility shim for the canonical NAS-first core entrypoint."""

from __future__ import annotations

import importlib
import sys

_core = importlib.import_module("nas_memory.core.vault_retrieve")


if __name__ == "__main__":
    print(
        "INFO: `vault_retrieve.py` at repo root is deprecated; use `nas_memory/core/vault_retrieve.py`.",
        file=sys.stderr,
    )
    raise SystemExit(_core.main() or 0)

sys.modules[__name__] = _core
