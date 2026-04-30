#!/usr/bin/env python3
"""Tests for PolicyRegistry delegation and interface-based core configuration.

Covers:
- PolicyRegistryImpl delegation stubs (8 tests)
- CoreConfig interface fields: policy_registry, path_utils, uses_interfaces (7 tests)
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from memory_core.tools.memory_hook_config import CoreConfig
from memory_core.tools.memory_hook_impls import PathUtilsImpl, PolicyRegistryImpl
from memory_core.tools.memory_hook_interfaces import PathUtils, PolicyRegistry


# ------------------------------------------------------------------
# Mock gateway module (injected into sys.modules so that
# PolicyRegistryImpl's delegation imports succeed)
# ------------------------------------------------------------------

_GATEWAY_FUNCS: dict[str, Any] = {
    "validate_project_map_files": lambda: [],
    "validate_unique_legal_system_contract": lambda: [],
    "governance_frozen_tuple_blocker_errors": lambda: [],
    "event_contract_blocker_errors": lambda: [],
    "git_registration_probe": lambda _e, _p: {},
    "truth_basis_for_scope": lambda _s: {},
    "decision_refs_for_scope": lambda _s: [],
    "lesson_refs_for_scope": lambda _s: [],
    "docs_refs_for_scope": lambda _s: [],
}


@pytest.fixture(autouse=True, scope="function")
def _inject_mock_gateway():
    """Inject a stub ``memory_hook_gateway`` module so delegation imports work."""
    mod = ModuleType("memory_hook_gateway")
    for name, func in _GATEWAY_FUNCS.items():
        setattr(mod, name, func)
    sys.modules["memory_hook_gateway"] = mod
    yield
    # Cleanup: remove mock to avoid polluting other tests
    sys.modules.pop("memory_hook_gateway", None)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def registry() -> PolicyRegistryImpl:
    """Minimal PolicyRegistryImpl with no policy-pack on disk."""
    return PolicyRegistryImpl()


@pytest.fixture
def base_config_kwargs() -> dict:
    """Minimal keyword arguments required to construct a CoreConfig."""
    return {
        "host": "codex",
        "event": "hook-test",
        "payload": {},
        "cwd": Path("/tmp"),
        "project_scope": "test-project",
        "workspace_root": Path("/tmp"),
        "repo_root": Path("/tmp"),
        "required_canonical": [],
        "project_canonical": {},
        "project_runtime_root": {},
        "global_canonical": [],
        "project_map_governance": Path("/tmp/governance.md"),
        "event_log": Path("/tmp/event.log"),
        "legality_source_policy": "test",
        "registration_commit_policy": "test",
        "registration_commit_phase": "test",
        "project_map_refs": [],
        "extract_excerpt_fn": lambda _p: [],
        "now_iso_fn": lambda: "2024-01-01T00:00:00",
        "write_targets_fn": lambda: {},
        "validate_project_map_fn": lambda: [],
        "validate_unique_legal_system_contract_fn": lambda: [],
        "policy_validate_fn": lambda _ctx: [],
        "get_policy_pack_fn": lambda _s: {},
        "governance_frozen_tuple_errors_fn": lambda: [],
        "event_contract_blocker_errors_fn": lambda: [],
        "git_registration_probe_fn": lambda _e, _p: {},
        "truth_basis_for_scope_fn": lambda _s: {},
        "decision_refs_for_scope_fn": lambda _s: [],
        "lesson_refs_for_scope_fn": lambda _s: [],
        "docs_refs_for_scope_fn": lambda _s: [],
        "hook_contract_path": Path("/tmp/contract.md"),
        "surface_id": "test-surface",
        "workspace_id": "test-workspace",
    }


# ==================================================================
# TestPolicyRegistryDelegation — 8 tests
# ==================================================================


class TestPolicyRegistryDelegation:
    """Verify PolicyRegistryImpl delegation methods return correct types."""

    def test_validate_project_map_returns_list(
        self, registry: PolicyRegistryImpl
    ) -> None:
        result = registry.validate_project_map()
        assert isinstance(result, list)

    def test_validate_legal_contract_returns_list(
        self, registry: PolicyRegistryImpl
    ) -> None:
        result = registry.validate_unique_legal_system_contract()
        assert isinstance(result, list)

    def test_governance_errors_returns_list(
        self, registry: PolicyRegistryImpl
    ) -> None:
        result = registry.governance_frozen_tuple_errors()
        assert isinstance(result, list)

    def test_event_contract_errors_returns_list(
        self, registry: PolicyRegistryImpl
    ) -> None:
        result = registry.event_contract_blocker_errors()
        assert isinstance(result, list)

    def test_git_registration_probe_returns_dict(
        self, registry: PolicyRegistryImpl
    ) -> None:
        result = registry.git_registration_probe("test-event", {"key": "value"})
        assert isinstance(result, dict)

    def test_truth_basis_returns_dict(
        self, registry: PolicyRegistryImpl
    ) -> None:
        result = registry.truth_basis_for_scope("test-scope")
        assert isinstance(result, dict)

    def test_scope_refs_return_lists(
        self, registry: PolicyRegistryImpl
    ) -> None:
        """decision, lesson, and docs refs must all return lists."""
        assert isinstance(registry.decision_refs_for_scope("scope"), list)
        assert isinstance(registry.lesson_refs_for_scope("scope"), list)
        assert isinstance(registry.docs_refs_for_scope("scope"), list)

    def test_is_instance_of_policy_registry(
        self, registry: PolicyRegistryImpl
    ) -> None:
        assert isinstance(registry, PolicyRegistry)


# ==================================================================
# TestInterfaceCoreConfig — 7 tests
# ==================================================================


class TestInterfaceCoreConfig:
    """Verify CoreConfig accepts and correctly handles interface fields."""

    def test_config_accepts_policy_registry(
        self, base_config_kwargs: dict, registry: PolicyRegistryImpl
    ) -> None:
        config = CoreConfig(**base_config_kwargs, policy_registry=registry)
        assert config.policy_registry is registry

    def test_config_accepts_path_utils(
        self, base_config_kwargs: dict
    ) -> None:
        pu = PathUtilsImpl(Path("/tmp"))
        config = CoreConfig(**base_config_kwargs, path_utils=pu)
        assert config.path_utils is pu
        assert isinstance(config.path_utils, PathUtils)

    def test_uses_interfaces_true_when_both_set(
        self, base_config_kwargs: dict, registry: PolicyRegistryImpl
    ) -> None:
        pu = PathUtilsImpl(Path("/tmp"))
        config = CoreConfig(
            **base_config_kwargs,
            policy_registry=registry,
            path_utils=pu,
        )
        assert config.uses_interfaces is True

    def test_uses_interfaces_false_when_either_missing(
        self, base_config_kwargs: dict, registry: PolicyRegistryImpl
    ) -> None:
        pu = PathUtilsImpl(Path("/tmp"))

        # Only path_utils set
        config_a = CoreConfig(**base_config_kwargs, path_utils=pu)
        assert config_a.uses_interfaces is False

        # Only policy_registry set
        config_b = CoreConfig(**base_config_kwargs, policy_registry=registry)
        assert config_b.uses_interfaces is False

    def test_both_default_to_none(self, base_config_kwargs: dict) -> None:
        config = CoreConfig(**base_config_kwargs)
        assert config.policy_registry is None
        assert config.path_utils is None

    def test_from_gateway_kwargs_accepts_interfaces(
        self, base_config_kwargs: dict, registry: PolicyRegistryImpl
    ) -> None:
        pu = PathUtilsImpl(Path("/tmp"))
        config = CoreConfig.from_gateway_kwargs(
            **base_config_kwargs,
            policy_registry=registry,
            path_utils=pu,
        )
        assert config.policy_registry is registry
        assert config.path_utils is pu
        assert config.uses_interfaces is True

    def test_build_from_config_with_interfaces(
        self, base_config_kwargs: dict, registry: PolicyRegistryImpl
    ) -> None:
        """Verify to_gateway_kwargs carries interface objects through."""
        pu = PathUtilsImpl(Path("/tmp"))
        config = CoreConfig(
            **base_config_kwargs,
            policy_registry=registry,
            path_utils=pu,
        )

        gw = config.to_gateway_kwargs()
        assert isinstance(gw, dict)
        assert isinstance(gw.get("policy_registry"), PolicyRegistryImpl)
        assert isinstance(gw.get("path_utils"), PathUtilsImpl)
