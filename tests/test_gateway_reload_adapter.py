#!/usr/bin/env python3
"""Tests for reload_adapter() function in memory_hook_gateway.

Verifies:
- reload_adapter with explicit name updates _ADAPTER_NAME
- reload_adapter from env var updates _ADAPTER_NAME
- reload_adapter with unknown name raises KeyError
- reload_adapter updates _adapter_config content
- Test isolation: restores default after each test
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Repo root setup
# ---------------------------------------------------------------------------

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import memory_core.tools.memory_hook_gateway as gw  # noqa: E402

# ---------------------------------------------------------------------------
# Fixture: ensure clean state after each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_default_adapter() -> None:
    """After each test, fully reload gateway with 'default' adapter.

    Must clear both sys.modules AND the parent package's __dict__ so
    that subsequent test modules (like batch3) that clear sys.modules
    and re-import get a fresh module object.
    """
    yield
    # Clear sys.modules and parent package cache.
    for name in list(sys.modules.keys()):
        if name.startswith("memory_core.tools.memory_hook"):
            del sys.modules[name]
    parent = sys.modules.get("memory_core.tools")
    if parent is not None:
        parent.__dict__.pop("memory_hook_gateway", None)
    # Re-import with default adapter.
    clean_env = {
        k: v for k, v in os.environ.items()
        if k not in ("MEMORY_HOOK_ADAPTER", "MEMORY_HOOK_FORCE", "WORKBOT_FORCE_HOOK")
    }
    with patch.dict("os.environ", clean_env, clear=True):
        os.environ.pop("MEMORY_HOOK_ADAPTER", None)
        os.environ.pop("MEMORY_HOOK_FORCE", None)
        os.environ.pop("WORKBOT_FORCE_HOOK", None)
        importlib.import_module("memory_core.tools.memory_hook_gateway")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reload_adapter_with_explicit_name() -> None:
    """Passing adapter_name='default' explicitly should update _ADAPTER_NAME."""
    # First switch to workbot to make the assertion meaningful.
    gw.reload_adapter("workbot")
    assert gw._ADAPTER_NAME == "workbot"

    # Now reload with explicit "default".
    gw.reload_adapter("default")
    assert gw._ADAPTER_NAME == "default"


def test_reload_adapter_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling reload_adapter() without args should read MEMORY_HOOK_ADAPTER env var."""
    # First ensure we're on default.
    gw.reload_adapter("default")
    assert gw._ADAPTER_NAME == "default"

    # Set env var and reload without argument.
    monkeypatch.setenv("MEMORY_HOOK_ADAPTER", "workbot")
    gw.reload_adapter()
    assert gw._ADAPTER_NAME == "workbot"


def test_reload_adapter_unknown_raises() -> None:
    """Passing a non-existent adapter name should raise KeyError."""
    with pytest.raises(KeyError, match="unknown adapter"):
        gw.reload_adapter("nonexistent_adapter_xyz")


def test_reload_adapter_updates_adapter_config() -> None:
    """Reload between adapters should change _adapter_config content."""
    # Record the DEFAULT_PROJECT_SCOPE from the current adapter.
    gw.reload_adapter("default")
    default_scope = gw._adapter_config.get("DEFAULT_PROJECT_SCOPE")

    # Switch to workbot.
    gw.reload_adapter("workbot")
    workbot_scope = gw._adapter_config.get("DEFAULT_PROJECT_SCOPE")

    # The scopes must differ between default and workbot profiles.
    assert default_scope != workbot_scope, (
        f"Expected different DEFAULT_PROJECT_SCOPE, got default={default_scope}, workbot={workbot_scope}"
    )

    # Switch back to default and verify it changed back.
    gw.reload_adapter("default")
    assert gw._adapter_config.get("DEFAULT_PROJECT_SCOPE") == default_scope
