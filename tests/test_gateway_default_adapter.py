#!/usr/bin/env python3
"""Tests for gateway default adapter behavior.

Verifies that:
- Default adapter is "default" when MEMORY_HOOK_ADAPTER is unset
- workbot adapter remains selectable via env var
- Unknown adapters fail gracefully
- CLAUDE_HOOK_STATE_DIR dead code has been removed
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Repo root setup
# ---------------------------------------------------------------------------

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_gateway_modules() -> None:
    """Remove all memory_hook modules from sys.modules for clean reload."""
    for name in list(sys.modules.keys()):
        if name.startswith("memory_core.tools.memory_hook"):
            del sys.modules[name]


def _reload_gateway(**env_overrides: str) -> Any:
    """Reload gateway with specified env overrides, stripping adapter vars first."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("MEMORY_HOOK_ADAPTER", "MEMORY_HOOK_FORCE", "WORKBOT_FORCE_HOOK")
    }
    clean_env.update(env_overrides)

    _clear_gateway_modules()

    with patch.dict(os.environ, clean_env, clear=True):
        gw = importlib.import_module("memory_core.tools.memory_hook_gateway")
        return gw


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_default_adapter_is_default_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """When MEMORY_HOOK_ADAPTER is not set, _ADAPTER_NAME should be 'default'."""
    monkeypatch.delenv("MEMORY_HOOK_ADAPTER", raising=False)
    monkeypatch.delenv("MEMORY_HOOK_FORCE", raising=False)
    monkeypatch.delenv("WORKBOT_FORCE_HOOK", raising=False)
    gw = _reload_gateway()
    assert gw._ADAPTER_NAME == "default"


def test_workbot_adapter_still_usable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting MEMORY_HOOK_ADAPTER=workbot should still load the workbot adapter."""
    monkeypatch.delenv("MEMORY_HOOK_FORCE", raising=False)
    monkeypatch.delenv("WORKBOT_FORCE_HOOK", raising=False)
    gw = _reload_gateway(MEMORY_HOOK_ADAPTER="workbot")
    assert gw._ADAPTER_NAME == "workbot"
    # Registry must still contain workbot
    assert "workbot" in gw._ADAPTER_REGISTRY
    mod_path, fn_name = gw._ADAPTER_REGISTRY["workbot"]
    assert "workbot_runtime_profile" in mod_path
    assert fn_name == "build_workbot_runtime_profile"


def test_unknown_adapter_falls_back_or_errors_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting an unknown adapter name should raise KeyError on import."""
    monkeypatch.setenv("MEMORY_HOOK_ADAPTER", "nonexistent")
    monkeypatch.delenv("MEMORY_HOOK_FORCE", raising=False)
    monkeypatch.delenv("WORKBOT_FORCE_HOOK", raising=False)
    _clear_gateway_modules()
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("MEMORY_HOOK_ADAPTER", "MEMORY_HOOK_FORCE", "WORKBOT_FORCE_HOOK")
    }
    clean_env["MEMORY_HOOK_ADAPTER"] = "nonexistent"

    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises(KeyError):
            importlib.import_module("memory_core.tools.memory_hook_gateway")


def test_claude_hook_state_dir_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLAUDE_HOOK_STATE_DIR should no longer exist as a module attribute."""
    monkeypatch.delenv("MEMORY_HOOK_ADAPTER", raising=False)
    monkeypatch.delenv("MEMORY_HOOK_FORCE", raising=False)
    monkeypatch.delenv("WORKBOT_FORCE_HOOK", raising=False)
    gw = _reload_gateway()
    assert not hasattr(gw, "CLAUDE_HOOK_STATE_DIR"), (
        "CLAUDE_HOOK_STATE_DIR dead code should have been removed"
    )
