"""Tests for neutral_policy module.

These tests verify the NeutralGatewayBusinessPolicy class behavior,
following the testing style of test_workbot_adapter_deprecation.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def mock_config():
    """Create a mock GatewayBusinessPolicyConfig for testing."""
    from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyConfig

    repo_root = Path("/tmp/test_repo")
    workspace_root = Path("/tmp/test_repo/memory_core")

    return GatewayBusinessPolicyConfig(
        repo_root=repo_root,
        workspace_root=workspace_root,
        project_map_root=workspace_root / "memory" / "kb" / "global" / "project-map",
        project_map_files=[
            workspace_root / "memory" / "kb" / "global" / "project-map" / "INDEX.md",
            workspace_root / "memory" / "kb" / "global" / "project-map" / "legal-core-map.md",
            workspace_root / "memory" / "kb" / "global" / "project-map" / "ingestion-registry-map.md",
        ],
        project_map_governance=workspace_root / "memory" / "kb" / "global" / "project-map-governance.md",
        truth_model=workspace_root / "memory" / "kb" / "global" / "workbot-truth-model.md",
        global_canonical=[
            workspace_root / "memory" / "kb" / "global" / "workbot-memory-system.md",
            workspace_root / "memory" / "kb" / "global" / "workbot-hook-contract.md",
        ],
        authority_allowed_paths={
            workspace_root / "memory" / "kb" / "global" / "workbot-truth-model.md",
        },
        lower_evidence_roots=[
            workspace_root / "memory" / "docs",
        ],
        legal_core_markers=["active-legal"],
        required_registry_scopes=["incoming-raw"],
        project_canonical={
            "AEdu": workspace_root / "memory" / "kb" / "projects" / "AEdu.md",
        },
        project_runtime_root={
            "AEdu": workspace_root / "projects" / "AEdu",
        },
        project_doc_refs={
            "AEdu": [workspace_root / "memory" / "docs" / "research" / "projects" / "AEdu" / "INDEX.md"],
        },
        default_decision_refs=[
            workspace_root / "memory" / "kb" / "decisions" / "INDEX.md",
        ],
        project_decision_refs={
            "AEdu": [workspace_root / "memory" / "kb" / "decisions" / "AEdu-001.md"],
        },
        default_lesson_refs=[
            workspace_root / "memory" / "kb" / "lessons" / "INDEX.md",
        ],
        project_lesson_refs={
            "AEdu": [workspace_root / "memory" / "kb" / "lessons" / "AEdu-lesson-001.md"],
        },
        governance_frozen_tuple_files=[
            workspace_root / "memory" / "kb" / "global" / "workbot-policy-pack.json",
        ],
        event_contract_files={
            "upstream_standard": workspace_root / "memory" / "kb" / "global" / "event-contract-upstream-standard.md",
            "upstream_mapping": workspace_root / "memory" / "kb" / "global" / "event-contract-upstream-mapping.md",
            "formal_contract": workspace_root / "memory" / "kb" / "global" / "event-contract-formal-contract.md",
            "upstream_samples": workspace_root / "memory" / "kb" / "global" / "event-contract-upstream-samples.json",
            "downstream_samples": workspace_root / "memory" / "kb" / "global" / "event-contract-downstream-samples.json",
        },
        frozen_tuple_expected={"expected_marker"},
        frozen_tuple_legacy_markers={"legacy_marker"},
        formal_source_types={"cli", "api"},
        formal_event_types={"session-start", "prompt-submit"},
        formal_event_statuses={"ok", "degraded", "error"},
        formal_field_keys={"host", "event", "timestamp"},
        legacy_field_keys={"old_host", "old_event"},
        required_canonical=[
            workspace_root / "INDEX.md",
        ],
        workspace_index_path=workspace_root / "INDEX.md",
        docs_index_path=workspace_root / "memory" / "docs" / "INDEX.md",
        overview_doc_path=workspace_root / "memory" / "docs" / "记忆系统全景文档.md",
        global_index_path=workspace_root / "memory" / "kb" / "global" / "INDEX.md",
        hook_contract_path=workspace_root / "memory" / "kb" / "global" / "workbot-hook-contract.md",
        default_project_scope="default",
        scope_match_hints={
            "AEdu": [workspace_root / "projects" / "AEdu"],
        },
        read_text_if_exists_fn=lambda p: p.read_text(encoding="utf-8") if p.exists() else "",
    )


class TestNeutralGatewayBusinessPolicy:
    """Tests for NeutralGatewayBusinessPolicy class."""

    def test_policy_can_be_instantiated_with_config(self, mock_config):
        """Test that NeutralGatewayBusinessPolicy can be instantiated with a config."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        assert policy is not None
        assert isinstance(policy, NeutralGatewayBusinessPolicy)

    def test_policy_can_be_instantiated_with_scope_config_path(self, mock_config, tmp_path):
        """Test that NeutralGatewayBusinessPolicy can be instantiated with scope_config_path."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        scope_config = tmp_path / "scope_config.json"
        scope_config.write_text('{"project_canonical": {}}')

        policy = NeutralGatewayBusinessPolicy(
            config=mock_config,
            scope_config_path=scope_config,
        )

        assert policy is not None

    def test_policy_inherits_from_gateway_business_policy_impl(self, mock_config):
        """Test that NeutralGatewayBusinessPolicy inherits from GatewayBusinessPolicyImpl."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )
        from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyImpl

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        assert isinstance(policy, GatewayBusinessPolicyImpl)

    def test_policy_has_config_attribute(self, mock_config):
        """Test that policy stores the config."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        # Access internal _config attribute
        assert policy._config is mock_config

    def test_policy_has_scope_config_path_attribute(self, mock_config, tmp_path):
        """Test that policy stores scope_config_path."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        scope_config = tmp_path / "scope_config.json"
        scope_config.write_text('{"project_canonical": {}}')

        policy = NeutralGatewayBusinessPolicy(
            config=mock_config,
            scope_config_path=scope_config,
        )

        assert policy._scope_config_path == scope_config

    def test_policy_without_scope_config_path_uses_env(self, mock_config, monkeypatch, tmp_path):
        """Test that policy reads scope_config_path from environment when not provided."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        scope_config = tmp_path / "env_scope_config.json"
        scope_config.write_text('{"project_canonical": {}}')
        monkeypatch.setenv("MEMORY_HOOK_SCOPE_CONFIG_PATH", str(scope_config))

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        assert policy._scope_config_path == scope_config

    def test_policy_without_scope_config_path_or_env(self, mock_config, monkeypatch):
        """Test that policy handles missing scope_config_path gracefully."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        monkeypatch.delenv("MEMORY_HOOK_SCOPE_CONFIG_PATH", raising=False)

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        assert policy._scope_config_path is None

    def test_policy_can_access_inherited_methods(self, mock_config):
        """Test that policy can access inherited methods from GatewayBusinessPolicyImpl."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        # Test that inherited methods are accessible
        assert hasattr(policy, "determine_project_scope")
        assert hasattr(policy, "get_project_canonical")
        assert hasattr(policy, "get_global_canonical")

    def test_policy_determine_project_scope_works(self, mock_config, tmp_path):
        """Test that inherited determine_project_scope method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        # Create a test path under AEdu scope
        test_path = Path("/tmp/test_repo/memory_core/projects/AEdu/subdir")

        scope = policy.determine_project_scope(test_path)

        # Should return AEdu based on scope_match_hints
        assert scope == "AEdu"

    def test_policy_get_project_canonical_works(self, mock_config):
        """Test that inherited get_project_canonical method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        canonical = policy.get_project_canonical()

        assert isinstance(canonical, dict)
        assert "AEdu" in canonical

    def test_policy_get_global_canonical_works(self, mock_config):
        """Test that inherited get_global_canonical method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        global_canonical = policy.get_global_canonical()

        assert isinstance(global_canonical, list)
        assert len(global_canonical) == 2

    def test_policy_get_required_canonical_works(self, mock_config):
        """Test that inherited get_required_canonical method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        required = policy.get_required_canonical()

        assert isinstance(required, list)

    def test_policy_get_project_runtime_root_works(self, mock_config):
        """Test that inherited get_project_runtime_root method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        runtime_roots = policy.get_project_runtime_root()

        assert isinstance(runtime_roots, dict)
        assert "AEdu" in runtime_roots

    def test_policy_project_map_refs_works(self, mock_config):
        """Test that inherited project_map_refs method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        refs = policy.project_map_refs()

        assert isinstance(refs, list)
        assert len(refs) == 3

    def test_policy_truth_basis_for_scope_works(self, mock_config):
        """Test that inherited truth_basis_for_scope method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        truth_basis = policy.truth_basis_for_scope("AEdu")

        assert isinstance(truth_basis, dict)
        assert "policy" in truth_basis
        assert truth_basis["policy"] == "source-authority-evidence-conflict"

    def test_policy_decision_refs_for_scope_works(self, mock_config):
        """Test that inherited decision_refs_for_scope method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        refs = policy.decision_refs_for_scope("AEdu")

        assert isinstance(refs, list)

    def test_policy_lesson_refs_for_scope_works(self, mock_config):
        """Test that inherited lesson_refs_for_scope method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        refs = policy.lesson_refs_for_scope("AEdu")

        assert isinstance(refs, list)

    def test_policy_docs_refs_for_scope_works(self, mock_config):
        """Test that inherited docs_refs_for_scope method works."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        refs = policy.docs_refs_for_scope("AEdu")

        assert isinstance(refs, list)


class TestNeutralPolicyVsWorkbotPolicy:
    """Comparison tests between neutral_policy and workbot_policy behavior."""

    def test_both_policies_inherit_from_same_base(self):
        """Test that both NeutralGatewayBusinessPolicy and WorkbotGatewayBusinessPolicy inherit from GatewayBusinessPolicyImpl."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )
        from memory_core.tools.memory_hook_adapters.workbot_policy import (
            WorkbotGatewayBusinessPolicy,
        )
        from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyImpl

        assert issubclass(NeutralGatewayBusinessPolicy, GatewayBusinessPolicyImpl)
        assert issubclass(WorkbotGatewayBusinessPolicy, NeutralGatewayBusinessPolicy)
        assert issubclass(WorkbotGatewayBusinessPolicy, GatewayBusinessPolicyImpl)

    def test_neutral_policy_is_base_class_for_workbot(self):
        """Test that NeutralGatewayBusinessPolicy is the base class for WorkbotGatewayBusinessPolicy."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )
        from memory_core.tools.memory_hook_adapters.workbot_policy import (
            WorkbotGatewayBusinessPolicy,
        )

        # Workbot extends Neutral
        assert NeutralGatewayBusinessPolicy in WorkbotGatewayBusinessPolicy.__mro__

    def test_neutral_policy_has_no_policy_pack_logic(self, mock_config):
        """Test that NeutralGatewayBusinessPolicy has no policy pack logic (unlike Workbot)."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        # Neutral policy should not have policy_pack_path attribute
        assert not hasattr(policy, "_policy_pack_path")
        assert not hasattr(policy, "inject_policy_pack_config")

    def test_neutral_policy_is_host_neutral(self, mock_config):
        """Test that NeutralGatewayBusinessPolicy is truly host-neutral."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        policy = NeutralGatewayBusinessPolicy(config=mock_config)

        # No host-specific attributes should be present
        assert not hasattr(policy, "POLICY_PACK_ENV")
        assert not hasattr(policy, "DEFAULT_POLICY_PACK_PATH")


class TestNeutralPolicyModule:
    """Tests for the neutral_policy module itself."""

    def test_module_exports_neutral_gateway_business_policy(self):
        """Test that module exports NeutralGatewayBusinessPolicy."""
        from memory_core.tools.memory_hook_adapters import neutral_policy as module

        assert hasattr(module, "NeutralGatewayBusinessPolicy")

    def test_module_docstring_exists(self):
        """Test that module has a docstring."""
        from memory_core.tools.memory_hook_adapters import neutral_policy as module

        assert module.__doc__ is not None
        assert "Host-neutral" in module.__doc__

    def test_neutral_gateway_business_policy_docstring(self):
        """Test that NeutralGatewayBusinessPolicy class has a docstring."""
        from memory_core.tools.memory_hook_adapters.neutral_policy import (
            NeutralGatewayBusinessPolicy,
        )

        assert NeutralGatewayBusinessPolicy.__doc__ is not None
        assert "Host-neutral" in NeutralGatewayBusinessPolicy.__doc__
