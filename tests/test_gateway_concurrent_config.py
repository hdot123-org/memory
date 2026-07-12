#!/usr/bin/env python3
"""Tests for gateway thread-safe config access.

Verifies:
- get_config() returns correct values after load_adapter_config
- get_config_dict() returns a safe copy
- Concurrent reads don't crash
- Concurrent load_adapter_config + reads don't crash
"""
from __future__ import annotations

import importlib
import os
import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


def _clear_gateway_modules() -> None:
    for name in list(sys.modules.keys()):
        if name.startswith("memory_core.tools.memory_hook"):
            if "integrity" in name:
                continue  # Preserve integrity modules to avoid stale refs
            del sys.modules[name]


def _reload_gateway(**env_overrides: str) -> Any:
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in (
            "MEMORY_HOOK_ADAPTER",
            "MEMORY_HOOK_FORCE",
            "WORKBOT_FORCE_HOOK",
            "MEMORY_ARTIFACT_PROJECT_ISOLATION",
        )
    }
    clean_env["MEMORY_HOOK_ADAPTER"] = "default"
    clean_env.update(env_overrides)
    _clear_gateway_modules()
    with patch.dict(os.environ, clean_env, clear=True):
        gw = importlib.import_module("memory_core.tools.memory_hook_gateway")
        return gw


class TestGetConfig:
    """get_config() reads from _adapter_config."""

    def test_get_config_returns_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gw = _reload_gateway()
        # Default adapter should inject some known keys
        val = gw.get_config("DEFAULT_PROJECT_SCOPE")
        assert val is not None or gw._adapter_config.get("DEFAULT_PROJECT_SCOPE") is None

    def test_get_config_default_for_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gw = _reload_gateway()
        val = gw.get_config("__NONEXISTENT_KEY__", "fallback")
        assert val == "fallback"

    def test_get_config_dict_returns_copy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gw = _reload_gateway()
        d = gw.get_config_dict()
        assert isinstance(d, dict)
        # Mutating the copy should not affect the original
        d["__test_key__"] = "mutated"
        assert gw._adapter_config.get("__test_key__") is None


class TestConcurrentConfigAccess:
    """Concurrent reads + writes should not crash."""

    def test_concurrent_reads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gw = _reload_gateway()
        errors: list[Exception] = []

        def reader(idx: int) -> None:
            try:
                for _ in range(50):
                    _ = gw.get_config_dict()
                    _ = gw.get_config("DEFAULT_PROJECT_SCOPE")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent read errors: {errors}"

    def test_concurrent_read_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gw = _reload_gateway()
        errors: list[Exception] = []
        profile = gw._adapter_config.copy()

        def writer() -> None:
            try:
                for _ in range(20):
                    gw.load_adapter_config(profile)
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(50):
                    _ = gw.get_config_dict()
                    _ = gw.get_config("DEFAULT_PROJECT_SCOPE")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent read/write errors: {errors}"
