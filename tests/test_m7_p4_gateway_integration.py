#!/usr/bin/env python3
"""M7-P4 gateway -> core -> system_context integration tests.

Covers the full call chain:
  gateway.build_context_package -> core.build_context_package_core -> system_context
alongside scope validation and force-hook env behavior.
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
# Repo-root setup
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
    """Reload the gateway module under a clean env.

    Strips MEMORY_HOOK_ADAPTER / MEMORY_HOOK_FORCE / WORKBOT_FORCE_HOOK
    before applying *env_overrides*, then re-imports the gateway so that
    module-level constants are recomputed.
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


def _build_minimal_payload(cwd: str | None = None) -> dict[str, Any]:
    """Return a minimal payload dict suitable for build_context_package."""
    payload: dict[str, Any] = {"session_id": "test-session-001"}
    if cwd is not None:
        payload["cwd"] = cwd
    return payload


# ---------------------------------------------------------------------------
# TestGatewayCoreIntegration
# ---------------------------------------------------------------------------

class TestGatewayCoreIntegration:
    """Verify the gateway -> core -> system_context chain produces correct output."""

    def test_full_chain_produces_system_context(self) -> None:
        """build_context_package returns system_context with expected keys."""
        gw = _reload_gateway()

        # Build a payload pointing inside the repo so discover_cwd finds a valid cwd
        payload = _build_minimal_payload(cwd=str(gw.REPO_ROOT / "workspace" / "tools"))
        package = gw.build_context_package("codex", "start", payload)

        assert "system_context" in package, "package must contain system_context"
        sc = package["system_context"]
        assert isinstance(sc, dict)

        # The system_context must carry policy_pack, scope, and schema_version
        assert "policy_pack" in sc, "system_context must contain policy_pack"
        assert "scope" in sc or "project_scope" in package, (
            "system_context or package must carry scope"
        )
        # schema_version lives at the top-level package in build_context_package_core
        assert "schema_version" in package, "package must contain schema_version"

    def test_registration_phase_from_policy_pack(self) -> None:
        """Verify registration_phase is extracted correctly from the loaded policy pack."""
        from workspace.tools.memory_hook_core import registration_phase_from_policy_pack

        # Normal case: policy_pack contains registration_phase
        pack_with_phase = {
            "policies": {"registration_phase": "enforced"},
        }
        assert registration_phase_from_policy_pack(pack_with_phase) == "enforced"

        # Missing policies key -> default
        assert registration_phase_from_policy_pack({}) == "declared-not-enforced"

        # Empty phase string -> default
        pack_empty_phase = {"policies": {"registration_phase": ""}}
        assert registration_phase_from_policy_pack(pack_empty_phase) == "declared-not-enforced"

        # Non-dict policies -> default
        pack_bad_policies = {"policies": "not-a-dict"}
        assert registration_phase_from_policy_pack(pack_bad_policies) == "declared-not-enforced"

        # Custom default
        assert (
            registration_phase_from_policy_pack({}, default_phase="custom-default")
            == "custom-default"
        )

    def test_context_package_contains_allowed_paths(self) -> None:
        """Verify allowed_reads and allowed_writes are non-empty."""
        gw = _reload_gateway()

        payload = _build_minimal_payload(cwd=str(gw.REPO_ROOT / "workspace" / "tools"))
        package = gw.build_context_package("codex", "start", payload)

        assert "allowed_reads" in package, "package must contain allowed_reads"
        assert "allowed_writes" in package, "package must contain allowed_writes"

        reads = package["allowed_reads"]
        writes = package["allowed_writes"]

        assert isinstance(reads, list), "allowed_reads must be a list"
        assert len(reads) > 0, "allowed_reads must be non-empty"

        # allowed_writes comes from write_targets_fn -> dict
        assert isinstance(writes, dict), "allowed_writes must be a dict"
        assert len(writes) > 0, "allowed_writes must be non-empty"


# ---------------------------------------------------------------------------
# TestScopeValidation
# ---------------------------------------------------------------------------

class TestScopeValidation:
    """Verify scope validation in PolicyRegistryImpl.get_policy_pack."""

    def test_supported_scope_works(self) -> None:
        """Scope 'workbot' produces a valid policy pack without raising."""
        gw = _reload_gateway()

        # The gateway wires a PolicyRegistryImpl with allowed_scopes from
        # POLICY_ALLOWED_SCOPES.  'workbot' must be in that set.
        pack = gw._get_policy_pack_via_registry("workbot")
        assert isinstance(pack, dict)
        assert pack["scope"] == "workbot"
        assert "policies" in pack
        assert "schema_version" in pack

    def test_empty_allowed_scopes_allows_any(self) -> None:
        """If allowed_scopes is empty set, get_policy_pack should not raise for any scope."""
        from workspace.tools.memory_hook_impls import PolicyRegistryImpl

        registry = PolicyRegistryImpl(allowed_scopes=set())

        # With an empty allowed_scopes set, any scope should be accepted
        pack = registry.get_policy_pack("any-arbitrary-scope")
        assert isinstance(pack, dict)
        assert pack["scope"] == "any-arbitrary-scope"
        assert "policies" in pack


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------

class TestEndToEnd:
    """End-to-end tests for cwd resolution and force-hook env behavior."""

    def test_cwd_resolution_matches_project_scope(self) -> None:
        """Calling with cwd pointing to workspace resolves correct scope."""
        gw = _reload_gateway()

        # Payload cwd inside the workbot workspace
        workspace_tools = gw.REPO_ROOT / "workspace" / "tools"
        payload = _build_minimal_payload(cwd=str(workspace_tools))

        cwd = gw._discover_cwd(payload)
        scope = gw.determine_project_scope(cwd)

        # The scope should resolve to 'workbot' when cwd is under REPO_ROOT
        assert scope == "workbot", (
            f"Expected scope 'workbot' for cwd inside repo, got '{scope}'"
        )

    def test_force_hook_env_overrides_noop(self) -> None:
        """MEMORY_HOOK_FORCE=1 changes should_noop behavior to return False."""
        gw = _reload_gateway()

        # Without force: if neither env cwd nor payload cwd is inside the repo,
        # should_noop returns True.
        payload_outside = _build_minimal_payload(cwd="/tmp/outside-repo")

        # Ensure no PWD inside repo
        clean_env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("MEMORY_HOOK_FORCE", "WORKBOT_FORCE_HOOK", "PWD")
        }
        clean_env["PWD"] = "/tmp/outside-repo"

        with patch.dict(os.environ, clean_env, clear=True):
            # Reload to pick up the clean env
            _clear_gateway_cache()
            gw_clean = importlib.import_module("workspace.tools.memory_hook_gateway")
            assert gw_clean._should_noop_for_external_context(payload_outside) is True

        # With MEMORY_HOOK_FORCE=1, should_noop must return False regardless
        with patch.dict(os.environ, {**clean_env, "MEMORY_HOOK_FORCE": "1"}, clear=True):
            _clear_gateway_cache()
            gw_force = importlib.import_module("workspace.tools.memory_hook_gateway")
            assert gw_force._should_noop_for_external_context(payload_outside) is False
