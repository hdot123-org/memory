"""Fixture/regression acceptance matrix for layout governance.

This test suite validates the governance rules across 9 fixture types:
1. fresh_project - Clean project with no memory structures
2. business_with_agents_index_project_map - Business content that should be preserved
3. legacy_memory_only - Only legacy memory/ directory exists
4. dot_memory_only - Only modern .memory/ directory exists
5. multi_generation_memory - Multiple memory structures coexist
6. root_pollution - Root-level scattered files
7. manifest_runtime_pollution - Manifest includes runtime paths
8. partial_broken_memory - Incomplete/broken memory structure
9. manual_conflict - AGENTS.md with manual edits conflicting with markers

Acceptance criteria:
- audit JSON/schema is parseable
- plan JSON/schema is parseable
- init adopt dry-run produces no file changes
- business AGENTS/INDEX/project-map are not overwritten by default
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from memory_core.tools.audit_project_layout import (
    audit_project_layout,
    plan_residue_migration,
)
from memory_core.tools.init_project_memory import init_project_memory


class TestFixtureFreshProject:
    """Fixture 1: fresh_project - Clean slate with no memory structures."""

    def test_audit_json_schema_parseable(self, tmp_path: Path) -> None:
        """Audit output must be valid JSON with expected schema."""
        result = audit_project_layout(tmp_path)
        data = result.to_dict()

        # Schema validation
        assert "target" in data
        assert "findings" in data
        assert "summary" in data
        assert "total" in data["summary"]
        assert "p0" in data["summary"]
        assert "p1" in data["summary"]
        assert "p2" in data["summary"]
        assert "scanned_dirs" in data["summary"]
        assert "scanned_files" in data["summary"]

        # Fresh project: only ownership_missing expected (M2 step 2.8)
        non_ownership = [f for f in data["findings"] if f.get("kind") != "ownership_missing"]
        assert len(non_ownership) == 0

    def test_plan_json_schema_parseable(self, tmp_path: Path) -> None:
        """Migration plan must be valid JSON with expected schema."""
        audit_result = audit_project_layout(tmp_path)
        plan = plan_residue_migration(audit_result, tmp_path)
        data = plan.to_dict()

        # Schema validation
        assert "target" in data
        assert "buckets" in data
        assert "summary" in data
        assert "total_items" in data["summary"]
        assert "bucket_counts" in data["summary"]

        # Expected buckets
        expected_buckets = {
            "direct_manage",
            "continue_active",
            "legacy_readonly",
            "runtime_ignore",
            "needs_human_decision",
            "root_pollution",
        }
        assert set(data["buckets"].keys()) == expected_buckets

    def test_init_adopt_dry_run_no_changes(self, tmp_path: Path) -> None:
        """Init with adopt mode and dry-run should not create any files."""
        # Pre-check: no .memory directory
        assert not (tmp_path / ".memory").exists()

        result = init_project_memory(
            tmp_path,
            scope="test_project",
            dry_run=True,
            mode="adopt",
        )

        # Should report success
        assert result["success"] is True
        assert result["dry_run"] is True

        # Verify no files were actually created
        assert not (tmp_path / ".memory").exists()

    def test_init_create_actually_creates(self, tmp_path: Path) -> None:
        """Verify that non-dry-run actually creates the structure."""
        result = init_project_memory(
            tmp_path,
            scope="test_project",
            dry_run=False,
            mode="create",
        )

        assert result["success"] is True
        assert (tmp_path / ".memory").exists()
        assert (tmp_path / ".memory" / "memory.lock").exists()


class TestFixtureBusinessWithAgentsIndexProjectMap:
    """Fixture 2: business_with_agents_index_project_map - Business content preserved."""

    @pytest.fixture
    def business_project(self, tmp_path: Path) -> Path:
        """Create a project with business AGENTS.md, INDEX.md, and project-map."""
        # Business AGENTS.md without memory markers
        agents_content = """# AGENTS.md

## Project Overview

This is a business project with custom agent instructions.

## Team Contacts

- Lead: alice@example.com
- Dev: bob@example.com

## Coding Standards

Use PEP 8 for Python code.
"""
        (tmp_path / "AGENTS.md").write_text(agents_content)

        # Business INDEX.md (not memory-related)
        index_content = """# INDEX.md

## Business Documentation

- Architecture overview
- API specifications
- Deployment guide
"""
        (tmp_path / "INDEX.md").write_text(index_content)

        # Business project-map
        (tmp_path / "project-map").mkdir()
        (tmp_path / "project-map" / "architecture.md").write_text("# Architecture\n")

        return tmp_path

    def test_audit_detects_business_files(self, business_project: Path) -> None:
        """Audit should detect but not flag business files as errors."""
        result = audit_project_layout(business_project)

        # Should not flag AGENTS.md as pollution if it doesn't have memory markers
        # But should detect it as unmarked if it contains "memory" or "hook"
        # Collect all finding kinds for potential future assertions
        _ = {f.kind for f in result.findings}  # noqa: F841

        # Business INDEX.md without memory keywords should not be flagged
        # as business content detection only happens if file exists
        index_finding = [f for f in result.findings if f.path == "INDEX.md"]
        # If flagged, it should be as business content (P2, continue_active)
        if index_finding:
            assert index_finding[0].severity == "P2"
            assert index_finding[0].suggested_bucket == "continue_active"

    def test_init_adopt_preserves_business_agents(self, business_project: Path) -> None:
        """Init adopt mode should preserve business AGENTS.md content."""
        result = init_project_memory(
            business_project,
            scope="test_project",
            dry_run=False,
            mode="adopt",
        )

        # Check that original content is preserved
        current_content = (business_project / "AGENTS.md").read_text()
        assert "Project Overview" in current_content
        assert "Team Contacts" in current_content

        # Adopt mode should not append a memory hook block to unmarked AGENTS.md
        assert "<!-- memory-core:hook:start -->" not in current_content
        assert result["success"] is True

    def test_init_adopt_preserves_business_index(self, business_project: Path) -> None:
        """Init adopt mode should preserve business INDEX.md."""
        init_project_memory(
            business_project,
            scope="test_project",
            dry_run=False,
            mode="adopt",
        )

        # Business INDEX.md should be preserved
        if (business_project / "INDEX.md").exists():
            content = (business_project / "INDEX.md").read_text()
            assert "Business Documentation" in content


class TestFixtureCurrentMemoryOnly:
    """Fixture 3: current_memory_only - Only root memory/ directory exists (current entry)."""

    @pytest.fixture
    def current_memory_project(self, tmp_path: Path) -> Path:
        """Create a project with only current memory/ structure."""
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "inbox.md").write_text("# Inbox\n")
        (tmp_path / "memory" / "kb").mkdir()
        (tmp_path / "memory" / "kb" / "global").mkdir()
        (tmp_path / "memory" / "kb" / "global" / "truth-model.md").write_text("# Truth\n")
        return tmp_path

    def test_audit_detects_current_memory(self, current_memory_project: Path) -> None:
        """Audit should detect memory/ as current_memory (P1, direct_manage)."""
        result = audit_project_layout(current_memory_project)

        current_findings = [f for f in result.findings if f.kind == "current_memory"]
        assert len(current_findings) == 1
        assert current_findings[0].severity == "P1"
        assert current_findings[0].suggested_bucket == "direct_manage"

    def test_audit_no_multi_generation(self, current_memory_project: Path) -> None:
        """Should not report multi-generation conflict with only current memory."""
        result = audit_project_layout(current_memory_project)

        conflict_findings = [f for f in result.findings if f.kind == "multi_generation_conflict"]
        assert len(conflict_findings) == 0

    def test_plan_categorizes_current_correctly(self, current_memory_project: Path) -> None:
        """Migration plan should categorize current memory as direct_manage."""
        audit_result = audit_project_layout(current_memory_project)
        plan = plan_residue_migration(audit_result, current_memory_project)

        # Current memory should be in direct_manage bucket
        current_items = [
            item for item in plan.buckets.get("direct_manage", [])
            if item.get("path") == "memory"
        ]
        assert len(current_items) == 1
        # Plan should recommend adopt/current, not legacy
        assert plan.risk_level != "critical"
        assert plan.requires_human_confirmation is False

    def test_init_create_does_not_overwrite_current(self, current_memory_project: Path) -> None:
        """Init create should not overwrite existing current memory files."""
        original_content = (current_memory_project / "memory" / "inbox.md").read_text()

        init_project_memory(
            current_memory_project,
            scope="test_project",
            dry_run=False,
            mode="create",
        )

        # Current memory files should be preserved
        assert (current_memory_project / "memory" / "inbox.md").exists()
        current_content = (current_memory_project / "memory" / "inbox.md").read_text()
        assert current_content == original_content


class TestFixtureWorkspaceMemoryOnly:
    """Fixture: workspace_memory_only - Only workspace/memory exists (legacy/retired)."""

    @pytest.fixture
    def workspace_memory_project(self, tmp_path: Path) -> Path:
        """Create a project with only workspace/memory structure."""
        (tmp_path / "workspace").mkdir()
        (tmp_path / "workspace" / "memory").mkdir()
        (tmp_path / "workspace" / "memory" / "inbox.md").write_text("# Legacy Inbox\n")
        (tmp_path / "workspace" / "project-map").mkdir()
        (tmp_path / "workspace" / "project-map" / "architecture.md").write_text("# Old Arch\n")
        return tmp_path

    def test_audit_detects_workspace_memory_as_legacy(self, workspace_memory_project: Path) -> None:
        """Audit should detect workspace/memory as workspace_memory (P1, needs_human_decision)."""
        result = audit_project_layout(workspace_memory_project)

        workspace_findings = [f for f in result.findings if f.kind == "workspace_memory"]
        assert len(workspace_findings) == 1
        assert workspace_findings[0].severity == "P1"
        # Legacy/retired finding
        assert workspace_findings[0].suggested_bucket == "needs_human_decision"

    def test_audit_detects_workspace_project_map(self, workspace_memory_project: Path) -> None:
        """Audit should detect workspace/project-map."""
        result = audit_project_layout(workspace_memory_project)

        pm_findings = [f for f in result.findings if f.kind == "workspace_project_map"]
        assert len(pm_findings) == 1
        assert pm_findings[0].severity == "P1"

    def test_audit_no_multi_generation_for_workspace_only(self, workspace_memory_project: Path) -> None:
        """Should not report multi-generation conflict with only workspace structures."""
        result = audit_project_layout(workspace_memory_project)

        conflict_findings = [f for f in result.findings if f.kind == "multi_generation_conflict"]
        assert len(conflict_findings) == 0

    def test_plan_categorizes_workspace_as_legacy(self, workspace_memory_project: Path) -> None:
        """Migration plan should categorize workspace memory as legacy_readonly."""
        audit_result = audit_project_layout(workspace_memory_project)
        plan = plan_residue_migration(audit_result, workspace_memory_project)

        # Workspace memory should trigger legacy_readonly action
        legacy_actions = [
            a for a in plan.actions
            if a.kind == "workspace_memory" and a.action == "mark_legacy_readonly"
        ]
        assert len(legacy_actions) >= 1


class TestFixtureDotMemoryOnly:
    """Fixture 4: dot_memory_only - Only modern .memory/ directory exists."""

    @pytest.fixture
    def dot_memory_project(self, tmp_path: Path) -> Path:
        """Create a project with only modern .memory/ structure."""
        (tmp_path / ".memory").mkdir()
        (tmp_path / ".memory" / "memory.lock").write_text(
            '[memory]\nproject = "test"\n'
        )
        (tmp_path / ".memory" / "CANONICAL.md").write_text("# Canonical\n")
        return tmp_path

    def test_audit_detects_dot_memory(self, dot_memory_project: Path) -> None:
        """Audit should detect .memory/ as P0 finding with direct_manage bucket."""
        result = audit_project_layout(dot_memory_project)

        dot_findings = [f for f in result.findings if f.kind == "dot_memory"]
        assert len(dot_findings) == 1
        assert dot_findings[0].severity == "P0"
        assert dot_findings[0].suggested_bucket == "direct_manage"

    def test_audit_no_multi_generation(self, dot_memory_project: Path) -> None:
        """Should not report multi-generation conflict with only .memory."""
        result = audit_project_layout(dot_memory_project)

        conflict_findings = [f for f in result.findings if f.kind == "multi_generation_conflict"]
        assert len(conflict_findings) == 0

    def test_plan_categorizes_dot_memory_correctly(self, dot_memory_project: Path) -> None:
        """Migration plan should categorize .memory as direct_manage."""
        audit_result = audit_project_layout(dot_memory_project)
        plan = plan_residue_migration(audit_result, dot_memory_project)

        # .memory should be in direct_manage bucket
        dot_items = [
            item for item in plan.buckets.get("direct_manage", [])
            if item.get("path") == ".memory"
        ]
        assert len(dot_items) == 1

    def test_init_skips_existing_files_by_default(self, dot_memory_project: Path) -> None:
        """Init should skip existing files by default (no --force)."""
        original_content = (dot_memory_project / ".memory" / "memory.lock").read_text()

        result = init_project_memory(
            dot_memory_project,
            scope="test_project",
            dry_run=False,
            mode="create",
        )

        # File should be preserved
        current_content = (dot_memory_project / ".memory" / "memory.lock").read_text()
        assert current_content == original_content
        assert any("skip" in item.lower() or "already exists" in item.lower()
                   for item in result.get("skipped", []))


class TestFixtureCurrentLayout:
    """Fixture: current_layout - .memory + memory + project-map (no conflict, not critical)."""

    @pytest.fixture
    def current_layout_project(self, tmp_path: Path) -> Path:
        """Create a project with current layout: .memory + memory + project-map."""
        # Modern .memory/
        (tmp_path / ".memory").mkdir()
        (tmp_path / ".memory" / "memory.lock").write_text('[memory]\n')

        # Current memory/
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "inbox.md").write_text("# Inbox\n")

        # Current project-map/
        (tmp_path / "project-map").mkdir()
        (tmp_path / "project-map" / "architecture.md").write_text("# Arch\n")

        return tmp_path

    def test_current_layout_audit_json_parseable(self, current_layout_project: Path) -> None:
        """Current layout audit JSON should be parseable."""
        result = audit_project_layout(current_layout_project)
        data = result.to_dict()

        # Should be valid JSON structure
        assert "target" in data
        assert "findings" in data
        assert "summary" in data

    def test_current_layout_plan_json_parseable(self, current_layout_project: Path) -> None:
        """Current layout plan JSON should be parseable."""
        audit_result = audit_project_layout(current_layout_project)
        plan = plan_residue_migration(audit_result, current_layout_project)
        data = plan.to_dict()

        # Should be valid JSON structure
        assert "target" in data
        assert "buckets" in data
        assert "actions" in data

    def test_current_layout_not_requires_human_confirmation(self, current_layout_project: Path) -> None:
        """Current layout should NOT require human confirmation, NOT critical.

        PRODUCTION CODE FAILURE POINT:
        - _check_multi_generation_conflict() counts .memory + memory/ as conflict
        - Expected: No conflict for current layout (.memory + memory + project-map)
        - Actual: Conflict detected, risk_level="critical", requires_human_confirmation=True
        - Location: audit_project_layout.py _check_multi_generation_conflict()
        """
        audit_result = audit_project_layout(current_layout_project)
        plan = plan_residue_migration(audit_result, current_layout_project)

        # Current layout (.memory + memory + project-map) should NOT be critical
        assert plan.requires_human_confirmation is False, (
            "PRODUCTION FAILURE: current layout should not require human confirmation. "
            "Fix _check_multi_generation_conflict() in audit_project_layout.py"
        )
        assert plan.risk_level != "critical", (
            "PRODUCTION FAILURE: current layout should not be critical risk. "
            "Fix _check_multi_generation_conflict() in audit_project_layout.py"
        )

    def test_current_layout_detects_structures(self, current_layout_project: Path) -> None:
        """Audit should detect all current structures."""
        result = audit_project_layout(current_layout_project)

        kinds = {f.kind for f in result.findings}
        assert "dot_memory" in kinds
        assert "current_memory" in kinds
        assert "project_map" in kinds
        # Should NOT have multi-generation conflict for current layout
        assert "multi_generation_conflict" not in kinds


class TestFixtureMultiGenerationMemory:
    """Fixture 5: multi_generation_memory - Multiple memory structures coexist."""

    @pytest.fixture
    def multi_gen_project(self, tmp_path: Path) -> Path:
        """Create a project with multiple memory structures."""
        # Modern .memory/
        (tmp_path / ".memory").mkdir()
        (tmp_path / ".memory" / "memory.lock").write_text('[memory]\n')

        # Current memory/
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "inbox.md").write_text("# Current\n")

        # workspace/memory (legacy)
        (tmp_path / "workspace").mkdir()
        (tmp_path / "workspace" / "memory").mkdir()

        return tmp_path

    def test_audit_detects_multi_generation_conflict(self, multi_gen_project: Path) -> None:
        """Audit should detect multi-generation conflict as P0."""
        result = audit_project_layout(multi_gen_project)

        conflict_findings = [f for f in result.findings if f.kind == "multi_generation_conflict"]
        assert len(conflict_findings) == 1
        assert conflict_findings[0].severity == "P0"

        # Should mention the conflicting locations
        assert ".memory" in conflict_findings[0].message
        assert "memory/" in conflict_findings[0].message

    def test_audit_detects_all_structures(self, multi_gen_project: Path) -> None:
        """Audit should detect all individual memory structures."""
        result = audit_project_layout(multi_gen_project)

        kinds = {f.kind for f in result.findings}
        assert "dot_memory" in kinds
        assert "current_memory" in kinds
        assert "workspace_memory" in kinds
        assert "multi_generation_conflict" in kinds

    def test_plan_categorizes_conflict_correctly(self, multi_gen_project: Path) -> None:
        """Migration plan should categorize multi-generation as needs_human_decision."""
        audit_result = audit_project_layout(multi_gen_project)
        plan = plan_residue_migration(audit_result, multi_gen_project)

        # Multi-generation conflict should be in needs_human_decision
        conflict_items = [
            item for item in plan.buckets.get("needs_human_decision", [])
            if item.get("kind") == "multi_generation_conflict"
        ]
        assert len(conflict_items) == 1


class TestFixtureRootVsWorkspaceConflict:
    """Fixture: Root memory + workspace memory = manual/critical conflict."""

    @pytest.fixture
    def root_workspace_conflict_project(self, tmp_path: Path) -> Path:
        """Create a project with root memory AND workspace memory (conflict)."""
        # Root memory (current)
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "inbox.md").write_text("# Root Inbox\n")

        # Workspace memory (legacy)
        (tmp_path / "workspace").mkdir()
        (tmp_path / "workspace" / "memory").mkdir()
        (tmp_path / "workspace" / "memory" / "old-inbox.md").write_text("# Old Inbox\n")

        return tmp_path

    def test_root_workspace_conflict_critical(self, root_workspace_conflict_project: Path) -> None:
        """Root + workspace memory should be critical risk requiring human confirmation."""
        audit_result = audit_project_layout(root_workspace_conflict_project)
        plan = plan_residue_migration(audit_result, root_workspace_conflict_project)

        # Should be critical and require human confirmation
        assert plan.risk_level == "critical"
        assert plan.requires_human_confirmation is True

    def test_root_workspace_conflict_detected(self, root_workspace_conflict_project: Path) -> None:
        """Audit should detect both root and workspace memory."""
        result = audit_project_layout(root_workspace_conflict_project)

        kinds = {f.kind for f in result.findings}
        assert "current_memory" in kinds
        assert "workspace_memory" in kinds
        assert "multi_generation_conflict" in kinds


class TestFixtureHistoryProjectsRetired:
    """Fixture: history-projects retired should NOT trigger conflict."""

    @pytest.fixture
    def history_projects_project(self, tmp_path: Path) -> Path:
        """Create a project with history-projects (retired, not conflicting)."""
        # Current memory
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "inbox.md").write_text("# Inbox\n")

        # history-projects (retired workspace)
        (tmp_path / "history-projects").mkdir()
        (tmp_path / "history-projects" / "old-project").mkdir()
        (tmp_path / "history-projects" / "old-project" / "notes.md").write_text("# Old\n")

        return tmp_path

    def test_history_projects_not_conflicting(self, history_projects_project: Path) -> None:
        """history-projects should NOT trigger multi-generation conflict."""
        result = audit_project_layout(history_projects_project)

        # Should detect history_projects
        history_findings = [f for f in result.findings if f.kind == "history_projects"]
        assert len(history_findings) == 1

        # Should NOT trigger multi-generation conflict
        conflict_findings = [f for f in result.findings if f.kind == "multi_generation_conflict"]
        assert len(conflict_findings) == 0

    def test_history_projects_marked_legacy(self, history_projects_project: Path) -> None:
        """history-projects should be marked as legacy_readonly."""
        result = audit_project_layout(history_projects_project)

        history_finding = [f for f in result.findings if f.kind == "history_projects"][0]
        assert history_finding.suggested_bucket == "legacy_readonly"


class TestFixtureRootPollution:
    """Fixture 6: root_pollution - Root-level scattered files."""

    @pytest.fixture
    def polluted_project(self, tmp_path: Path) -> Path:
        """Create a project with root pollution files."""
        # Report files
        (tmp_path / "security-report.md").write_text("# Security Report\n")
        (tmp_path / "performance-audit.md").write_text("# Audit\n")

        # Phase plans
        (tmp_path / "p1-migration.md").write_text("# Phase 1\n")
        (tmp_path / "p2-cleanup.md").write_text("# Phase 2\n")

        # Backup files
        (tmp_path / "config.bak").write_text("backup")
        (tmp_path / "data.backup.2024.json").write_text("{}")

        # Dump files
        (tmp_path / "memory-dump.json").write_text("{}")

        # NOW.md
        (tmp_path / "NOW.md").write_text("# NOW\n")

        return tmp_path

    def test_audit_detects_all_pollution_types(self, polluted_project: Path) -> None:
        """Audit should detect all types of root pollution."""
        result = audit_project_layout(polluted_project)

        kinds = {f.kind for f in result.findings}
        assert "root_report" in kinds
        assert "root_audit" in kinds
        assert "root_plan" in kinds
        assert "root_backup" in kinds
        assert "root_dump" in kinds
        assert "root_now" in kinds

    def test_audit_correct_severity(self, polluted_project: Path) -> None:
        """Pollution findings should have correct severity levels."""
        result = audit_project_layout(polluted_project)

        for finding in result.findings:
            if finding.kind in ("root_report", "root_audit", "root_plan", "root_dump"):
                assert finding.severity == "P1"
            elif finding.kind in ("root_backup", "root_now"):
                assert finding.severity == "P2"

    def test_plan_buckets_root_pollution(self, polluted_project: Path) -> None:
        """Migration plan should put root pollution in root_pollution bucket."""
        audit_result = audit_project_layout(polluted_project)
        plan = plan_residue_migration(audit_result, polluted_project)

        # All pollution items should be in root_pollution bucket
        pollution_items = plan.buckets.get("root_pollution", [])
        assert len(pollution_items) >= 6  # report, audit, plan, backup, dump, now

    def test_init_does_not_affect_polluted_root(self, polluted_project: Path) -> None:
        """Init should not clean up root pollution files."""
        # Verify files exist before init
        assert (polluted_project / "security-report.md").exists()

        init_project_memory(
            polluted_project,
            scope="test_project",
            dry_run=False,
            mode="create",
        )

        # Pollution files should still exist
        assert (polluted_project / "security-report.md").exists()
        assert (polluted_project / "config.bak").exists()


class TestFixtureManifestRuntimePollution:
    """Fixture 7: manifest_runtime_pollution - Manifest includes runtime paths."""

    @pytest.fixture
    def manifest_runtime_project(self, tmp_path: Path) -> Path:
        """Create a project with manifest containing runtime paths."""
        (tmp_path / ".memory").mkdir()

        # Manifest with runtime paths
        manifest = {
            "schema_version": "integrity-manifest-v1",
            "entries": [
                {"path": "/tmp/test.json", "rel_path": "tmp/test.json"},
                {"path": "/project/runtime/state.json", "rel_path": "runtime/state.json"},
                {"path": "/project/log/app.log", "rel_path": "log/app.log"},
                {"path": "/project/artifacts/memory-hook/data.json"},
                {"path": "/project/.memory/memory.lock", "rel_path": "memory.lock"},
            ],
        }
        (tmp_path / ".memory" / "manifest.json").write_text(
            json.dumps(manifest)
        )

        return tmp_path

    def test_audit_detects_manifest_runtime_paths(self, manifest_runtime_project: Path) -> None:
        """Audit should detect runtime paths in manifest."""
        result = audit_project_layout(manifest_runtime_project)

        runtime_findings = [f for f in result.findings if f.kind == "manifest_includes_runtime"]
        assert len(runtime_findings) >= 1

    def test_audit_correct_bucket_for_runtime(self, manifest_runtime_project: Path) -> None:
        """Runtime findings should be in runtime_ignore bucket."""
        result = audit_project_layout(manifest_runtime_project)

        for finding in result.findings:
            if finding.kind == "manifest_includes_runtime":
                assert finding.suggested_bucket == "runtime_ignore"

    def test_plan_categorizes_runtime_correctly(self, manifest_runtime_project: Path) -> None:
        """Migration plan should put runtime paths in runtime_ignore bucket."""
        audit_result = audit_project_layout(manifest_runtime_project)
        plan = plan_residue_migration(audit_result, manifest_runtime_project)

        runtime_items = plan.buckets.get("runtime_ignore", [])
        assert len(runtime_items) >= 1


class TestFixturePartialBrokenMemory:
    """Fixture 8: partial_broken_memory - Incomplete/broken memory structure."""

    @pytest.fixture
    def broken_project(self, tmp_path: Path) -> Path:
        """Create a project with broken/incomplete memory structure."""
        # .memory exists but with broken manifest
        (tmp_path / ".memory").mkdir()
        (tmp_path / ".memory" / "manifest.json").write_text("not valid json {[")

        # Some expected files missing
        (tmp_path / ".memory" / "memory.lock").write_text("broken content")

        return tmp_path

    def test_audit_detects_broken_manifest(self, broken_project: Path) -> None:
        """Audit should detect invalid manifest JSON."""
        result = audit_project_layout(broken_project)

        invalid_findings = [f for f in result.findings if f.kind == "manifest_invalid"]
        assert len(invalid_findings) == 1
        assert invalid_findings[0].severity == "P1"

    def test_audit_still_detects_structure(self, broken_project: Path) -> None:
        """Should still detect .memory structure even with broken manifest."""
        result = audit_project_layout(broken_project)

        dot_findings = [f for f in result.findings if f.kind == "dot_memory"]
        assert len(dot_findings) == 1

    def test_init_can_repair_broken_manifest(self, broken_project: Path) -> None:
        """Init should be able to work with broken structures."""
        result = init_project_memory(
            broken_project,
            scope="test_project",
            dry_run=False,
            mode="repair",
        )

        # Should succeed
        assert result["success"] is True


class TestFixtureManualConflict:
    """Fixture 9: manual_conflict - AGENTS.md with manual edits conflicting with markers."""

    @pytest.fixture
    def manual_conflict_project(self, tmp_path: Path) -> Path:
        """Create a project with manually edited AGENTS.md markers."""
        # AGENTS.md with markers but manual edits inside
        content = """<!-- MEMORY_HOOK_BEGIN -->
## Memory Hook

This is a manually edited section that might conflict.

Custom instructions here.
<!-- MEMORY_HOOK_END -->

## Other Content

Regular business content outside markers.
"""
        (tmp_path / "AGENTS.md").write_text(content)

        return tmp_path

    def test_audit_detects_marked_agents(self, manual_conflict_project: Path) -> None:
        """Audit should detect AGENTS.md with markers."""
        result = audit_project_layout(manual_conflict_project)

        marked_findings = [f for f in result.findings if f.kind == "agents_md_marked"]
        assert len(marked_findings) == 1
        assert marked_findings[0].severity == "P2"
        assert marked_findings[0].suggested_bucket == "direct_manage"

    def test_init_update_preserves_markers(self, manual_conflict_project: Path) -> None:
        """Init update mode should preserve marker block but update content."""
        result = init_project_memory(
            manual_conflict_project,
            scope="test_project",
            dry_run=False,
            mode="update",
        )

        # Should succeed
        assert result["success"] is True

        # Markers should still exist
        current_content = (manual_conflict_project / "AGENTS.md").read_text()
        assert "<!-- MEMORY_HOOK_BEGIN -->" in current_content
        assert "<!-- MEMORY_HOOK_END -->" in current_content

    def test_init_update_replaces_marked_block(self, manual_conflict_project: Path) -> None:
        """Init update mode should replace content inside markers."""
        init_project_memory(
            manual_conflict_project,
            scope="test_project",
            dry_run=False,
            mode="update",
        )

        current_content = (manual_conflict_project / "AGENTS.md").read_text()

        # Should have updated content within markers
        assert "<!-- MEMORY_HOOK_BEGIN -->" in current_content
        assert "<!-- MEMORY_HOOK_END -->" in current_content

        # Content outside markers should be preserved
        assert "## Other Content" in current_content
        assert "Regular business content" in current_content


class TestAcceptanceCriteria:
    """Cross-fixture acceptance criteria validation."""

    def test_audit_json_is_valid(self, tmp_path: Path) -> None:
        """Audit JSON output must be valid and parseable."""
        # Setup some structures
        (tmp_path / ".memory").mkdir()
        (tmp_path / "memory").mkdir()

        result = audit_project_layout(tmp_path)
        data = result.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        # Validate structure
        assert isinstance(parsed["target"], str)
        assert isinstance(parsed["findings"], list)
        assert isinstance(parsed["summary"], dict)
        assert isinstance(parsed["summary"]["total"], int)

    def test_plan_json_is_valid(self, tmp_path: Path) -> None:
        """Plan JSON output must be valid and parseable."""
        (tmp_path / ".memory").mkdir()
        (tmp_path / "test-report.md").write_text("# Report")

        audit_result = audit_project_layout(tmp_path)
        plan = plan_residue_migration(audit_result, tmp_path)
        data = plan.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        # Validate structure
        assert isinstance(parsed["target"], str)
        assert isinstance(parsed["buckets"], dict)
        assert isinstance(parsed["summary"], dict)
        assert isinstance(parsed["summary"]["total_items"], int)

    def test_init_adopt_dry_run_produces_no_changes(self, tmp_path: Path) -> None:
        """Init adopt dry-run must not produce any file changes."""
        # Create some existing structure
        (tmp_path / "AGENTS.md").write_text("# AGENTS\n")
        (tmp_path / "INDEX.md").write_text("# INDEX\n")

        # Capture pre-run state
        pre_files = set(tmp_path.rglob("*"))

        result = init_project_memory(
            tmp_path,
            scope="test_project",
            dry_run=True,
            mode="adopt",
        )

        # Capture post-run state
        post_files = set(tmp_path.rglob("*"))

        # Should be identical
        assert pre_files == post_files
        assert result["dry_run"] is True

    def test_business_files_not_overwritten_by_default(self, tmp_path: Path) -> None:
        """Business AGENTS/INDEX/project-map must not be overwritten by default."""
        # Create business files
        agents_content = "# Business AGENTS\n\nCustom instructions."
        index_content = "# Business INDEX\n\nDocumentation."

        (tmp_path / "AGENTS.md").write_text(agents_content)
        (tmp_path / "INDEX.md").write_text(index_content)
        (tmp_path / "project-map").mkdir()
        (tmp_path / "project-map" / "architecture.md").write_text("# Architecture")

        # Init without force
        init_project_memory(
            tmp_path,
            scope="test_project",
            dry_run=False,
            mode="adopt",
        )

        # Business content should be preserved
        assert "Business AGENTS" in (tmp_path / "AGENTS.md").read_text()
        assert "Business INDEX" in (tmp_path / "INDEX.md").read_text()
        assert (tmp_path / "project-map" / "architecture.md").exists()

    def test_init_force_can_overwrite(self, tmp_path: Path) -> None:
        """Init with --force should be able to overwrite existing files (with authorized maintenance)."""
        # Create existing .memory structure
        (tmp_path / ".memory").mkdir()
        (tmp_path / ".memory" / "memory.lock").write_text("old content")

        # Init with force (use MEMORY_INIT_RUNNING=1 for authorized maintenance)
        old_env = os.environ.get("MEMORY_INIT_RUNNING")
        try:
            os.environ["MEMORY_INIT_RUNNING"] = "1"
            result = init_project_memory(
                tmp_path,
                scope="new_project_name",
                dry_run=False,
                mode="create",
                force=True,
            )
        finally:
            if old_env is not None:
                os.environ["MEMORY_INIT_RUNNING"] = old_env
            else:
                os.environ.pop("MEMORY_INIT_RUNNING", None)

        # Content should be updated
        content = (tmp_path / ".memory" / "memory.lock").read_text()
        assert "new_project_name" in content
        assert result["force_overwrite"] is True


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_project(self, tmp_path: Path) -> None:
        """Empty project should have no findings except ownership_missing (M2 step 2.8)."""
        result = audit_project_layout(tmp_path)
        non_ownership = [f for f in result.findings if f.kind != "ownership_missing"]
        assert len(non_ownership) == 0

    def test_nonexistent_target(self, tmp_path: Path) -> None:
        """Audit should handle non-existent target gracefully."""
        nonexistent = tmp_path / "does_not_exist"
        result = audit_project_layout(nonexistent)

        assert len(result.findings) == 1
        assert result.findings[0].kind == "target_missing"
        assert result.findings[0].severity == "P0"

    def test_file_as_target(self, tmp_path: Path) -> None:
        """Audit should handle file (not directory) target gracefully."""
        file_path = tmp_path / "not_a_directory.txt"
        file_path.write_text("content")

        result = audit_project_layout(file_path)

        assert len(result.findings) == 1
        assert result.findings[0].kind == "target_not_dir"
        assert result.findings[0].severity == "P0"

    def test_severity_filter_p0(self, tmp_path: Path) -> None:
        """P0 severity filter should only return P0 findings."""
        # Create P0 and P1 findings
        (tmp_path / ".memory").mkdir()  # P0
        (tmp_path / "test-report.md").write_text("# Report")  # P1
        (tmp_path / "config.bak").write_text("backup")  # P2

        result = audit_project_layout(tmp_path, severity_filter="P0")

        assert all(f.severity == "P0" for f in result.findings)

    def test_severity_filter_p1(self, tmp_path: Path) -> None:
        """P1 severity filter should return P0 and P1 findings."""
        (tmp_path / ".memory").mkdir()  # P0
        (tmp_path / "test-report.md").write_text("# Report")  # P1
        (tmp_path / "config.bak").write_text("backup")  # P2

        result = audit_project_layout(tmp_path, severity_filter="P1")

        severities = {f.severity for f in result.findings}
        assert "P0" in severities
        assert "P1" in severities
        assert "P2" not in severities

    def test_agents_md_unmarked_detection(self, tmp_path: Path) -> None:
        """Should detect AGENTS.md with memory refs but no markers."""
        content = """# AGENTS.md

## Memory System

This project uses memory hooks.
"""
        (tmp_path / "AGENTS.md").write_text(content)

        result = audit_project_layout(tmp_path)

        unmarked = [f for f in result.findings if f.kind == "agents_md_unmarked"]
        assert len(unmarked) == 1
        assert unmarked[0].severity == "P1"
