#!/usr/bin/env python3
"""Runtime compatibility tests for NAS-first core migration."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main as unittest_main

from nas_memory.core.runtime_config import build_legacy_config_module, install_legacy_config_module


class RuntimeConfigTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_dir.name)
        self.config_file = self.repo_root / "config.py"
        self._saved_env = {}
        self._saved_config_module = sys.modules.get("config")

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self._saved_config_module is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = self._saved_config_module
        self.temp_dir.cleanup()

    def _set_env(self, key: str, value: str | None) -> None:
        if key not in self._saved_env:
            self._saved_env[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def test_env_priority_over_file(self):
        self.config_file.write_text(
            "\n".join(
                [
                    'VAULT_NOTES_DIR = "/file/notes"',
                    'QDRANT_PATH = "/file/qdrant"',
                    "RETRIEVE_TOP_K = 9",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._set_env("MEMORY_CORE_CONFIG", str(self.config_file))
        self._set_env("VAULT_NOTES_DIR", "/env/notes")
        self._set_env("RETRIEVE_TOP_K", "5")

        module = build_legacy_config_module(self.repo_root)
        self.assertEqual(module.VAULT_NOTES_DIR, "/env/notes")
        self.assertEqual(module.QDRANT_PATH, "/file/qdrant")
        self.assertEqual(module.RETRIEVE_TOP_K, 5)

    def test_file_override_without_env(self):
        self.config_file.write_text(
            "\n".join(
                [
                    'VAULT_NOTES_DIR = "/file/notes"',
                    "BM25_ENABLED = False",
                    "EMBED_DIM = 2048",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._set_env("MEMORY_CORE_CONFIG", str(self.config_file))
        self._set_env("VAULT_NOTES_DIR", None)

        module = build_legacy_config_module(self.repo_root)
        self.assertEqual(module.VAULT_NOTES_DIR, "/file/notes")
        self.assertFalse(module.BM25_ENABLED)
        self.assertEqual(module.EMBED_DIM, 2048)

    def test_fallback_defaults_without_file(self):
        self._set_env("MEMORY_CORE_CONFIG", str(self.repo_root / "missing.py"))
        self._set_env("MEMORY_ROOT", str(self.repo_root / "memory"))

        module = build_legacy_config_module(self.repo_root)
        self.assertEqual(module.VAULT_NOTES_DIR, str(self.repo_root / "memory" / "notes"))
        self.assertEqual(module.QDRANT_PATH, str(self.repo_root / "memory" / "vault_qdrant"))
        self.assertEqual(module.RETRIEVE_TOP_K, 3)

    def test_install_legacy_config_module_registers_config(self):
        self._set_env("MEMORY_CORE_CONFIG", str(self.repo_root / "missing.py"))
        installed = install_legacy_config_module(self.repo_root)
        self.assertIn("config", sys.modules)
        self.assertIs(sys.modules["config"], installed)
        self.assertTrue(getattr(installed, "__memory_runtime__", False))


class RootShimCompatibilityTests(TestCase):
    def test_process_queue_shim_exports_core_functions(self):
        shim = importlib.import_module("process_queue")
        core = importlib.import_module("nas_memory.core.process_queue")
        self.assertIs(shim.sanitize_note_id, core.sanitize_note_id)

    def test_vault_retrieve_shim_exports_core_functions(self):
        shim = importlib.import_module("vault_retrieve")
        core = importlib.import_module("nas_memory.core.vault_retrieve")
        self.assertIs(shim.tokenize, core.tokenize)

    def test_vault_embed_shim_exports_core_functions(self):
        shim = importlib.import_module("vault_embed")
        core = importlib.import_module("nas_memory.core.vault_embed")
        self.assertIs(shim.build_graph_index, core.build_graph_index)


if __name__ == "__main__":
    unittest_main()

