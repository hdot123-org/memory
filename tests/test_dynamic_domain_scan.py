#!/usr/bin/env python3
"""Tests for dynamic domain scan in _compute_truth_basis_errors.

Validates VAL-DOMAIN-001 through VAL-DOMAIN-006:
- Dynamic scanning of all directories under global_kb_root
- Inclusion of custom domains like infra
- Exclusion of pending directory
- Exclusion of non-directory entries (files)
- Handling of empty/missing global_kb_root
- End-to-end Factory host session-start behavior
"""

from pathlib import Path

from memory_core.tools.memory_hook_core import _compute_truth_basis_errors


class TestDynamicDomainScan:
    """Test dynamic domain enumeration in global KB root."""

    def test_includes_all_directories(self, tmp_path: Path):
        """VAL-DOMAIN-001: allowed_reads includes every directory under global_kb_root."""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir()

        # Create multiple domain directories
        (global_kb_root / "operations").mkdir()
        (global_kb_root / "engineering").mkdir()
        (global_kb_root / "collaboration").mkdir()
        (global_kb_root / "infra").mkdir()

        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=global_kb_root,
            global_kb_enabled=True,
        )

        # All four directories should be in reads
        assert str(global_kb_root / "operations") in reads
        assert str(global_kb_root / "engineering") in reads
        assert str(global_kb_root / "collaboration") in reads
        assert str(global_kb_root / "infra") in reads

    def test_includes_custom_domain_infra(self, tmp_path: Path):
        """VAL-DOMAIN-002: allowed_reads includes infra (custom domain NOT in original hardcoded list)."""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir()
        (global_kb_root / "infra").mkdir()

        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=global_kb_root,
            global_kb_enabled=True,
        )

        assert str(global_kb_root / "infra") in reads

    def test_excludes_pending_directory(self, tmp_path: Path):
        """VAL-DOMAIN-003: allowed_reads excludes pending directory."""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir()
        (global_kb_root / "operations").mkdir()
        (global_kb_root / "pending").mkdir()

        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=global_kb_root,
            global_kb_enabled=True,
        )

        # pending should NOT be in reads
        assert str(global_kb_root / "pending") not in reads
        # but operations should be
        assert str(global_kb_root / "operations") in reads

    def test_excludes_non_directory_entries(self, tmp_path: Path):
        """VAL-DOMAIN-004: allowed_reads excludes non-directory entries like INDEX.md."""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir()
        (global_kb_root / "operations").mkdir()
        (global_kb_root / "INDEX.md").write_text("# Global KB Index\n")
        (global_kb_root / "README.md").write_text("# Readme\n")

        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=global_kb_root,
            global_kb_enabled=True,
        )

        # Files should NOT be in reads
        assert str(global_kb_root / "INDEX.md") not in reads
        assert str(global_kb_root / "README.md") not in reads
        # Directory should be in reads
        assert str(global_kb_root / "operations") in reads

    def test_empty_global_kb_root_no_errors(self, tmp_path: Path):
        """VAL-DOMAIN-005: Empty or missing global_kb_root does not cause errors."""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir()  # Empty directory

        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        # Should not raise any exception
        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=global_kb_root,
            global_kb_enabled=True,
        )

        # No global_kb_root-prefixed paths should be in reads when root is empty
        assert not any(str(global_kb_root) in r for r in reads)

    def test_global_kb_disabled_no_scan(self, tmp_path: Path):
        """When global_kb_enabled=False, no scanning occurs."""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir()
        (global_kb_root / "operations").mkdir()

        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=global_kb_root,
            global_kb_enabled=False,  # Disabled
        )

        # No global_kb paths should be in reads
        assert not any(str(global_kb_root) in r for r in reads)

    def test_global_kb_root_none_no_scan(self, tmp_path: Path):
        """When global_kb_root is None, no scanning occurs."""
        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=None,
            global_kb_enabled=True,
        )

        # Should not raise exception
        assert reads is not None

    def test_multiple_custom_domains(self, tmp_path: Path):
        """Test with various custom domain names."""
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir()

        # Standard domains
        (global_kb_root / "operations").mkdir()
        (global_kb_root / "engineering").mkdir()
        (global_kb_root / "collaboration").mkdir()

        # Custom domains
        (global_kb_root / "infrastructure").mkdir()
        (global_kb_root / "security").mkdir()
        (global_kb_root / "devops").mkdir()
        (global_kb_root / "ai-ml").mkdir()

        # Should be excluded
        (global_kb_root / "pending").mkdir()
        (global_kb_root / ".git").mkdir()  # Hidden directory

        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=global_kb_root,
            global_kb_enabled=True,
        )

        # All custom domains should be included
        assert str(global_kb_root / "infrastructure") in reads
        assert str(global_kb_root / "security") in reads
        assert str(global_kb_root / "devops") in reads
        assert str(global_kb_root / "ai-ml") in reads

        # pending should be excluded
        assert str(global_kb_root / "pending") not in reads

        # Hidden directories should be included (they are valid directories)
        assert str(global_kb_root / ".git") in reads


class TestEndToEndFactoryHost:
    """VAL-DOMAIN-006: End-to-end dynamic enumeration via _compute_truth_basis_errors."""

    def test_dynamic_scan_includes_infra_excludes_pending(self, tmp_path: Path):
        """Factory host with infra/ on disk includes it in reads, excludes pending/ and INDEX.md."""
        # Setup global KB with standard + custom domains
        global_kb_root = tmp_path / "global-kb"
        global_kb_root.mkdir()
        (global_kb_root / "operations").mkdir()
        (global_kb_root / "engineering").mkdir()
        (global_kb_root / "collaboration").mkdir()
        (global_kb_root / "infra").mkdir()
        (global_kb_root / "pending").mkdir()  # Should be excluded
        (global_kb_root / "INDEX.md").write_text("# Global KB\n")  # Should be excluded

        truth_basis = {"refs": [], "errors": []}
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()

        _, _, reads = _compute_truth_basis_errors(
            truth_basis=truth_basis,
            decisions=[],
            lessons=[],
            docs_refs=[],
            workspace_root=workspace_root,
            project_map_refs=[],
            global_kb_root=global_kb_root,
            global_kb_enabled=True,
        )

        # Verify allowed_reads includes infra
        assert any("infra" in r for r in reads), f"infra not found in {reads}"

        # Verify allowed_reads excludes pending
        assert not any("pending" in r for r in reads), f"pending found in {reads}"

        # Verify INDEX.md from global_kb_root is excluded (workspace INDEX.md is OK)
        assert not any(str(global_kb_root) in r and "INDEX.md" in r for r in reads), f"INDEX.md from global_kb found in {reads}"

        # Verify standard domains are included
        assert any("operations" in r for r in reads)
        assert any("engineering" in r for r in reads)
        assert any("collaboration" in r for r in reads)
