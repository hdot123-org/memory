#!/usr/bin/env python3
"""M7-P2 gateway decoupling tests.

Verifies adapter discovery, policy-class resolution, force-hook env vars,
and that the gateway no longer hardcodes workbot in adapter-discovery logic.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Repo root setup (same pattern as existing tests in this repo)
# ---------------------------------------------------------------------------

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_gateway_cache() -> None:
    """Remove all memory_hook modules from sys.modules."""
    for name in list(sys.modules.keys()):
        if name.startswith("workspace.tools.memory_hook"):
            del sys.modules[name]


def _reload_gateway(**env_overrides: str) -> Any:
    """Reload the gateway module under a clean set of env vars.

    Clears MEMORY_HOOK_ADAPTER / MEMORY_HOOK_FORCE / WORKBOT_FORCE_HOOK
    before applying *env_overrides*, then re-imports the gateway so that
    module-level constants (_ADAPTER_NAME, _ADAPTER_REGISTRY, etc.) are
    recomputed.
    """
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("MEMORY_HOOK_ADAPTER", "MEMORY_HOOK_FORCE", "WORKBOT_FORCE_HOOK")
    }
    clean_env.update(env_overrides)

    _clear_gateway_cache()

    with patch.dict(os.environ, clean_env, clear=True):
        gw = importlib.import_module("workspace.tools.memory_hook_gateway")
        return gw


# ---------------------------------------------------------------------------
# TestAdapterDiscovery
# ---------------------------------------------------------------------------


class TestAdapterDiscovery:
    """Verify adapter-discovery constants and registry behaviour."""

    def test_default_adapter_is_workbot(self) -> None:
        """Without MEMORY_HOOK_ADAPTER env var, gateway loads workbot profile."""
        gw = _reload_gateway()
        assert gw._ADAPTER_NAME == "workbot"

    def test_env_var_selects_adapter(self) -> None:
        """With MEMORY_HOOK_ADAPTER=workbot, the correct profile loads."""
        gw = _reload_gateway(MEMORY_HOOK_ADAPTER="workbot")
        assert gw._ADAPTER_NAME == "workbot"

    def test_invalid_adapter_name_raises(self) -> None:
        """With a non-existent adapter name, import should fail."""
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("MEMORY_HOOK_ADAPTER", "MEMORY_HOOK_FORCE", "WORKBOT_FORCE_HOOK")
        }
        clean_env["MEMORY_HOOK_ADAPTER"] = "nonexistent_adapter_xyz"

        _clear_gateway_cache()

        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(KeyError):
                importlib.import_module("workspace.tools.memory_hook_gateway")

    def test_adapter_registry_has_workbot(self) -> None:
        """Verify _ADAPTER_REGISTRY contains 'workbot' entry."""
        gw = _reload_gateway()
        assert "workbot" in gw._ADAPTER_REGISTRY
        mod_path, fn_name = gw._ADAPTER_REGISTRY["workbot"]
        assert "workbot_runtime_profile" in mod_path
        assert fn_name == "build_workbot_runtime_profile"


# ---------------------------------------------------------------------------
# TestPolicyClassResolution
# ---------------------------------------------------------------------------


class TestPolicyClassResolution:
    """Verify GATEWAY_POLICY_CLASS is wired through the adapter profile."""

    def test_policy_class_from_profile(self) -> None:
        """GATEWAY_POLICY_CLASS is set in the runtime profile globals."""
        gw = _reload_gateway()
        assert hasattr(gw, "GATEWAY_POLICY_CLASS")

    def test_policy_class_is_workbot_by_default(self) -> None:
        """Default policy class is WorkbotGatewayBusinessPolicy."""
        gw = _reload_gateway()
        from workspace.tools.memory_hook_adapters.workbot_policy import (
            WorkbotGatewayBusinessPolicy,
        )
        assert gw.GATEWAY_POLICY_CLASS is WorkbotGatewayBusinessPolicy

    def test_build_policy_uses_adapter_class(self) -> None:
        """_build_gateway_business_policy uses the class from profile."""
        gw = _reload_gateway()
        from workspace.tools.memory_hook_adapters.workbot_policy import (
            WorkbotGatewayBusinessPolicy,
        )
        policy = gw._build_gateway_business_policy()
        assert isinstance(policy, WorkbotGatewayBusinessPolicy)


# ---------------------------------------------------------------------------
# TestForceHookEnvVar
# ---------------------------------------------------------------------------


class TestForceHookEnvVar:
    """Verify MEMORY_HOOK_FORCE and backward-compatible WORKBOT_FORCE_HOOK."""

    def test_memory_hook_force_env_var(self) -> None:
        """MEMORY_HOOK_FORCE env var is recognized and bypasses noop."""
        gw = _reload_gateway(MEMORY_HOOK_FORCE="1")
        # should_noop_for_external_context should return False when force is set
        result = gw._should_noop_for_external_context({})
        assert result is False

    def test_backward_compat_workbot_force_hook(self) -> None:
        """WORKBOT_FORCE_HOOK still works as fallback."""
        gw = _reload_gateway(WORKBOT_FORCE_HOOK="1")
        result = gw._should_noop_for_external_context({})
        assert result is False


# ---------------------------------------------------------------------------
# TestGatewayDecoupling
# ---------------------------------------------------------------------------


class TestGatewayDecoupling:
    """Verify decoupling: no hardcoded workbot logic in adapter discovery."""

    def test_no_hardcoded_workbot_in_adapter_discovery(self) -> None:
        """Adapter discovery code does not hardcode 'workbot' in logic.

        'workbot' is allowed only as the default *name* string, not as
        conditional logic (if/elif/else branches that special-case it).
        """
        gateway_source = (
            Path(__file__).resolve().parent.parent
            / "workspace"
            / "tools"
            / "memory_hook_gateway.py"
        ).read_text(encoding="utf-8")

        # Extract the adapter-discovery block (from _ADAPTER_NAME through
        # the load_adapter_config(...) call).
        lines = gateway_source.splitlines()
        start_idx = None
        end_idx = None
        for i, line in enumerate(lines):
            if "_ADAPTER_NAME" in line and "=" in line and not line.strip().startswith("#"):
                if start_idx is None:
                    start_idx = i
            if "load_adapter_config(_adapter_profile)" in line:
                end_idx = i
                break

        assert start_idx is not None, "Could not find _ADAPTER_NAME in gateway source"
        assert end_idx is not None, "Could not find load_adapter_config in gateway source"

        discovery_block = "\n".join(lines[start_idx : end_idx + 1])

        # The block should NOT contain any conditional that checks for
        # "workbot" as a logic branch — only the default string is allowed.
        conditional_patterns = re.findall(
            r'\b(if|elif)\b.*["\']workbot["\']',
            discovery_block,
        )
        assert (
            not conditional_patterns
        ), f"Adapter discovery contains hardcoded workbot conditionals: {conditional_patterns}"
