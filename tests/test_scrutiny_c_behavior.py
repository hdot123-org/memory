#!/usr/bin/env python3
"""Scrutiny (c) behavior tests: corrupt-manifest audit log + _classify_truth_ref priority.

M2 scrutiny handoff item (c): Two behavior tests to钉住:
1. When manifest is corrupt/invalid, sign_project_incremental falls back to full sign
   and writes audit log with action="full-sign" to the correct path.
2. _classify_truth_ref priority order: exact match > global_canonical > path containment > "other".

These tests verify the actual behavior, not just code structure.
"""

import json
from pathlib import Path
from typing import Any


def _make_config(tmp_path: Path, **overrides: Any) -> Any:
    """Build a minimal GatewayBusinessPolicyConfig rooted under tmp_path."""
    from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyConfig

    repo = tmp_path / "repo"
    pm_root = tmp_path / "project_map"
    for d in (repo, pm_root):
        d.mkdir(parents=True, exist_ok=True)
    (repo / "workspace").mkdir(parents=True, exist_ok=True)

    def _noop_read(path: Path) -> str:
        return ""

    defaults: dict[str, Any] = {
        "repo_root": repo,
        "workspace_root": repo / "workspace",
        "project_map_root": pm_root,
        "project_map_files": [pm_root / "INDEX.md", pm_root / "legal-core-map.md"],
        "project_map_governance": pm_root / "governance.md",
        "truth_model": repo / "workspace" / "truth_model.md",
        "global_canonical": [repo / "workspace" / "global_1.md"],
        "authority_allowed_paths": {repo / "workspace" / "authority_1.md"},
        "lower_evidence_roots": [repo / "workspace" / "evidence"],
        "legal_core_markers": ["active-legal"],
        "required_registry_scopes": ["incoming-raw"],
        "project_canonical": {"test-scope": repo / "workspace" / "test_scope.md"},
        "project_runtime_root": {"test-scope": repo / "workspace" / "runtime"},
        "project_doc_refs": {},
        "default_decision_refs": [],
        "project_decision_refs": {},
        "default_lesson_refs": [],
        "project_lesson_refs": {},
        "governance_frozen_tuple_files": [],
        "event_contract_files": {},
        "frozen_tuple_expected": set(),
        "frozen_tuple_legacy_markers": set(),
        "formal_source_types": set(),
        "formal_event_types": set(),
        "formal_event_statuses": set(),
        "formal_field_keys": set(),
        "legacy_field_keys": set(),
        "required_canonical": [],
        "workspace_index_path": repo / "workspace" / "INDEX.md",
        "docs_index_path": repo / "workspace" / "docs_index.md",
        "overview_doc_path": repo / "workspace" / "overview.md",
        "global_index_path": repo / "workspace" / "global_index.md",
        "hook_contract_path": repo / "workspace" / "hook_contract.md",
        "default_project_scope": "default",
        "scope_match_hints": {"kb": [repo / "workspace" / "memory" / "kb"]},
        "read_text_if_exists_fn": _noop_read,
    }
    defaults.update(overrides)
    return GatewayBusinessPolicyConfig(**defaults)


class TestCorruptManifestAuditLog:
    """Verify that corrupt manifest triggers fallback to full sign with audit log."""

    def test_corrupt_manifest_writes_audit_log(self, tmp_path: Path) -> None:
        """When manifest.json is corrupt (JSONDecodeError), sign_project_incremental
        should fall back to full sign and write audit log with action='full-sign'."""
        from memory_core.tools.memory_hook_integrity_manifest import (
            AUDIT_LOG_FILENAME,
            sign_project_incremental,
        )

        # Setup: create a project structure with a corrupt manifest
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Create memory/system directory structure first
        memory_dir = project_root / "memory" / "system"
        memory_dir.mkdir(parents=True)
        manifest_path = memory_dir / "manifest.json"

        # Write corrupt manifest (invalid JSON)
        manifest_path.write_text("{ invalid json content", encoding="utf-8")

        # Create a key for signing
        key = b"0" * 32

        # Create a sample file to sign
        sample_file = project_root / "memory" / "kb" / "test.md"
        sample_file.parent.mkdir(parents=True)
        sample_file.write_text("# Test", encoding="utf-8")

        # Call sign_project_incremental with corrupt manifest
        result = sign_project_incremental(
            project_root,
            key,
            changed_paths=["memory/kb/test.md"],
            reason="test-corrupt-manifest",
        )

        # Verify: should fall back to full sign (result is not None)
        assert result is not None, "sign_project_incremental should fall back to full sign on corrupt manifest"
        assert "entries" in result, "Result should contain 'entries' key"

        # Verify: audit log should be written
        audit_path = memory_dir / AUDIT_LOG_FILENAME
        assert audit_path.exists(), f"Audit log should exist at {audit_path}"

        # Verify: audit log should contain action="full-sign"
        audit_content = audit_path.read_text(encoding="utf-8")
        assert "full-sign" in audit_content, "Audit log should contain 'full-sign' action"
        assert "test-corrupt-manifest" in audit_content, "Audit log should contain the reason"

        # Verify: audit log should be valid JSON lines
        lines = [line for line in audit_content.strip().split("\n") if line]
        assert len(lines) > 0, "Audit log should have at least one line"
        for line in lines:
            entry = json.loads(line)  # Should not raise
            assert "action" in entry, "Each audit entry should have 'action' field"
            assert "timestamp" in entry, "Each audit entry should have 'timestamp' field"

    def test_invalid_manifest_structure_writes_audit_log(self, tmp_path: Path) -> None:
        """When manifest.json is valid JSON but not a dict (e.g., list),
        sign_project_incremental should fall back to full sign and write audit log."""
        from memory_core.tools.memory_hook_integrity_manifest import (
            AUDIT_LOG_FILENAME,
            sign_project_incremental,
        )

        # Setup: create a project structure with invalid manifest structure
        project_root = tmp_path / "project"
        project_root.mkdir()

        # Create memory/system directory structure first
        memory_dir = project_root / "memory" / "system"
        memory_dir.mkdir(parents=True)
        manifest_path = memory_dir / "manifest.json"

        # Write manifest as a list instead of dict
        manifest_path.write_text("[1, 2, 3]", encoding="utf-8")

        # Create a key for signing
        key = b"0" * 32

        # Create a sample file to sign
        sample_file = project_root / "memory" / "kb" / "test.md"
        sample_file.parent.mkdir(parents=True)
        sample_file.write_text("# Test", encoding="utf-8")

        # Call sign_project_incremental with invalid manifest structure
        result = sign_project_incremental(
            project_root,
            key,
            changed_paths=["memory/kb/test.md"],
            reason="test-invalid-structure",
        )

        # Verify: should fall back to full sign
        assert result is not None, "sign_project_incremental should fall back to full sign on invalid structure"

        # Verify: audit log should be written
        audit_path = memory_dir / AUDIT_LOG_FILENAME
        assert audit_path.exists(), f"Audit log should exist at {audit_path}"

        # Verify: audit log should contain action="full-sign"
        audit_content = audit_path.read_text(encoding="utf-8")
        assert "full-sign" in audit_content, "Audit log should contain 'full-sign' action"


class TestClassifyTruthRefPriority:
    """Verify _classify_truth_ref priority order: exact > global_canonical > path > other."""

    def test_exact_match_wins_over_global_canonical(self, tmp_path: Path) -> None:
        """When a path matches an exact table entry AND is in global_canonical,
        exact match should win."""
        from memory_core.tools.business_policy_checks import TruthBasisResolver

        # Setup: create config where legal-core-map.md is both in exact table
        # and in global_canonical
        config = _make_config(tmp_path)

        legal_core_path = config.project_map_root / "legal-core-map.md"
        legal_core_path.write_text("# Legal Core", encoding="utf-8")

        # Add legal_core_path to global_canonical
        config.global_canonical.append(legal_core_path)

        resolver = TruthBasisResolver(config)

        # Verify: exact match should win
        result = resolver._classify_truth_ref(legal_core_path)
        assert result == "legal-core", (
            f"Exact match should win over global_canonical, got {result}"
        )

    def test_global_canonical_wins_over_path_containment(self, tmp_path: Path) -> None:
        """When a path is in global_canonical AND under a path containment table,
        global_canonical should win."""
        from memory_core.tools.business_policy_checks import TruthBasisResolver

        # Setup: create config where a path is both in global_canonical
        # and under workspace_root/memory/kb/projects (which would classify as project-canonical)
        config = _make_config(tmp_path)

        # Path that is under kb/projects AND in global_canonical
        kb_path = config.workspace_root / "memory" / "kb" / "projects" / "global_ref.md"
        kb_path.parent.mkdir(parents=True)
        kb_path.write_text("# Global Reference", encoding="utf-8")

        # Add kb_path to global_canonical
        config.global_canonical.append(kb_path)

        resolver = TruthBasisResolver(config)

        # Verify: global_canonical should win over path containment
        result = resolver._classify_truth_ref(kb_path)
        assert result == "global-canonical", (
            f"global_canonical should win over path containment, got {result}"
        )

    def test_path_containment_wins_over_other(self, tmp_path: Path) -> None:
        """When a path is under a path containment table entry,
        it should be classified by that table, not as 'other'."""
        from memory_core.tools.business_policy_checks import TruthBasisResolver

        # Setup: create config with a path under docs
        config = _make_config(tmp_path)

        docs_path = config.workspace_root / "memory" / "docs" / "readme.md"
        docs_path.parent.mkdir(parents=True)
        docs_path.write_text("# Documentation", encoding="utf-8")

        resolver = TruthBasisResolver(config)

        # Verify: path containment should classify as "docs", not "other"
        result = resolver._classify_truth_ref(docs_path)
        assert result == "docs", (
            f"Path under docs should be classified as 'docs', got {result}"
        )

    def test_unmatched_path_returns_other(self, tmp_path: Path) -> None:
        """When a path doesn't match any rule, it should return 'other'."""
        from memory_core.tools.business_policy_checks import TruthBasisResolver

        # Setup: create config with a path that doesn't match any rule
        config = _make_config(tmp_path)

        random_path = tmp_path / "random" / "file.txt"
        random_path.parent.mkdir(parents=True)
        random_path.write_text("random content", encoding="utf-8")

        resolver = TruthBasisResolver(config)

        # Verify: unmatched path should return "other"
        result = resolver._classify_truth_ref(random_path)
        assert result == "other", (
            f"Unmatched path should return 'other', got {result}"
        )
