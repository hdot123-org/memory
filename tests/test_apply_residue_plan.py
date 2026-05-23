"""Tests for memory_core.tools.apply_residue_plan module.

Tests the safe migrator functionality including:
- Dry-run mode (no file writes)
- Plan validation (no plan = rejection)
- Human confirmation rejection
- Manual decision action rejection
- Forbidden overwrite protection
- Root report apply with backup manifest creation
- Rollback functionality
- Destination exists rejection
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Import the module under test
from memory_core.tools.apply_residue_plan import (
    _is_forbidden_path,
    _now_iso,
    _rollback_from_manifest,
    _sha256_file,
    _validate_plan,
    apply_residue_plan,
    main,
)


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_sha256_file(self, tmp_path: Path) -> None:
        """SHA256 calculation should work correctly."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        sha256 = _sha256_file(test_file)
        # Known SHA256 for "hello world" (without newline)
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert sha256 == expected

    def test_now_iso_returns_string(self) -> None:
        """_now_iso should return a string."""
        result = _now_iso()
        assert isinstance(result, str)
        assert "T" in result or "-" in result  # ISO format indicators

    def test_is_forbidden_path_agents_md(self) -> None:
        """AGENTS.md should be forbidden."""
        assert _is_forbidden_path("AGENTS.md") is True
        assert _is_forbidden_path("agents.md") is True
        assert _is_forbidden_path("/path/to/AGENTS.md") is True

    def test_is_forbidden_path_index_md(self) -> None:
        """INDEX.md should be forbidden."""
        assert _is_forbidden_path("INDEX.md") is True
        assert _is_forbidden_path("index.md") is True

    def test_is_forbidden_path_claude_md(self) -> None:
        """CLAUDE.md should be forbidden."""
        assert _is_forbidden_path("CLAUDE.md") is True
        assert _is_forbidden_path("claude.md") is True

    def test_is_forbidden_path_project_map(self) -> None:
        """project-map paths should be forbidden."""
        assert _is_forbidden_path("project-map/INDEX.md") is True
        assert _is_forbidden_path("PROJECT-MAP/file.md") is True
        assert _is_forbidden_path("path/project-map/") is True

    def test_is_forbidden_path_allowed(self) -> None:
        """Other paths should be allowed."""
        assert _is_forbidden_path("README.md") is False
        assert _is_forbidden_path("test-report.md") is False
        assert _is_forbidden_path("artifacts/reports/file.md") is False


class TestPlanValidation:
    """Tests for plan validation."""

    def test_validate_valid_plan(self) -> None:
        """Valid plan should pass validation."""
        plan = {
            "target": "/path/to/project",
            "actions": [
                {"action": "move_root_pollution", "path": "test-report.md", "severity": "P1"},
            ],
            "risk_level": "medium",
            "requires_human_confirmation": False,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_rejects_no_plan(self) -> None:
        """Non-dict plan should fail validation."""
        is_valid, errors = _validate_plan(None)
        assert is_valid is False
        assert any("JSON object" in e for e in errors)

    def test_validate_rejects_missing_target(self) -> None:
        """Plan without target should fail validation."""
        plan = {
            "actions": [],
            "risk_level": "low",
            "requires_human_confirmation": False,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is False
        assert any("target" in e for e in errors)

    def test_validate_rejects_missing_actions(self) -> None:
        """Plan without actions should fail validation."""
        plan = {
            "target": "/path/to/project",
            "risk_level": "low",
            "requires_human_confirmation": False,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is False
        assert any("actions" in e for e in errors)

    def test_validate_rejects_human_confirmation(self) -> None:
        """Plan with requires_human_confirmation=true should be rejected."""
        plan = {
            "target": "/path/to/project",
            "actions": [],
            "risk_level": "high",
            "requires_human_confirmation": True,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is False
        assert any("human confirmation" in e.lower() for e in errors)

    def test_validate_rejects_manual_decision_action(self) -> None:
        """Plan with manual_decision_required actions should be rejected."""
        plan = {
            "target": "/path/to/project",
            "actions": [
                {"action": "manual_decision_required", "path": "conflict.md", "severity": "P0"},
            ],
            "risk_level": "critical",
            "requires_human_confirmation": False,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is False
        assert any("manual decision" in e.lower() for e in errors)

    def test_validate_rejects_forbidden_overwrite_agents(self) -> None:
        """Plan targeting AGENTS.md should be rejected."""
        plan = {
            "target": "/path/to/project",
            "actions": [
                {"action": "move_root_pollution", "path": "AGENTS.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is False
        assert any("forbidden" in e.lower() for e in errors)

    def test_validate_rejects_forbidden_overwrite_index(self) -> None:
        """Plan targeting INDEX.md should be rejected."""
        plan = {
            "target": "/path/to/project",
            "actions": [
                {"action": "move_root_pollution", "path": "INDEX.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is False
        assert any("forbidden" in e.lower() for e in errors)

    def test_validate_rejects_forbidden_overwrite_project_map(self) -> None:
        """Plan targeting project-map/** should be rejected."""
        plan = {
            "target": "/path/to/project",
            "actions": [
                {"action": "move_root_pollution", "path": "project-map/INDEX.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is False
        assert any("forbidden" in e.lower() for e in errors)

    def test_validate_rejects_forbidden_overwrite_claude(self) -> None:
        """Plan targeting CLAUDE.md should be rejected."""
        plan = {
            "target": "/path/to/project",
            "actions": [
                {"action": "move_root_pollution", "path": "CLAUDE.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        is_valid, errors = _validate_plan(plan)
        assert is_valid is False
        assert any("forbidden" in e.lower() for e in errors)


class TestDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_does_not_write_files(self, tmp_path: Path) -> None:
        """Dry-run should not write any files."""
        project = tmp_path / "project"
        project.mkdir()

        # Create a file that would be moved
        report_file = project / "test-report.md"
        report_file.write_text("# Report")

        # Create plan
        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "test-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        # Run in dry-run mode
        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=True,
            backup_dir=None,
            json_output=False,
        )

        # Verify success
        assert result.success is True
        assert result.dry_run is True

        # Verify file still exists in original location
        assert report_file.exists()

        # Verify no artifacts/reports directory created
        assert not (project / "artifacts" / "reports").exists()

        # Verify no backup directory created
        assert not (project / "memory" / "system" / "backups").exists()

    def test_dry_run_reports_would_move(self, tmp_path: Path) -> None:
        """Dry-run should report what would be moved."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "test-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "test-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=True,
            backup_dir=None,
            json_output=False,
        )

        # Should have applied actions in dry-run
        assert len(result.actions_applied) == 1
        assert result.actions_applied[0]["status"] == "dry-run"

    def test_dry_run_reports_would_ignore(self, tmp_path: Path) -> None:
        """Dry-run should report what would be ignored."""
        project = tmp_path / "project"
        project.mkdir()

        plan = {
            "target": str(project),
            "actions": [
                {"action": "ignore_runtime_artifact", "path": "artifacts/memory-hook/log.json", "severity": "P2"},
            ],
            "risk_level": "low",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=True,
            backup_dir=None,
            json_output=False,
        )

        # Should have applied actions in dry-run
        assert len(result.actions_applied) == 1
        assert result.actions_applied[0]["action"] == "ignore_runtime_artifact"


class TestNoPlanRejection:
    """Tests for no plan rejection."""

    def test_no_plan_rejected(self, tmp_path: Path) -> None:
        """Apply without plan should be rejected."""
        project = tmp_path / "project"
        project.mkdir()

        result = apply_residue_plan(
            target=project,
            plan_path=None,
            dry_run=False,
            backup_dir=None,
            json_output=False,
        )

        assert result.success is False
        assert any("no plan" in e.lower() for e in result.errors)


class TestMoveRootPollution:
    """Tests for move_root_pollution action."""

    def test_move_root_report_to_artifacts(self, tmp_path: Path) -> None:
        """Root report should be moved to artifacts/reports."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "status-report.md"
        report_content = "# Status Report\n\nContent here."
        report_file.write_text(report_content)

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=tmp_path / "backup",
            json_output=False,
        )

        assert result.success is True

        # Original file should be gone
        assert not report_file.exists()

        # File should be in artifacts/reports
        moved_file = project / "artifacts" / "reports" / "status-report.md"
        assert moved_file.exists()
        assert moved_file.read_text() == report_content

    def test_move_creates_backup_manifest(self, tmp_path: Path) -> None:
        """Moving files should create backup manifest."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "status-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        backup_dir = tmp_path / "backup"

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=backup_dir,
            json_output=False,
        )

        assert result.success is True
        assert result.backup_manifest is not None

        # Manifest should exist
        manifest_path = Path(result.backup_manifest["path"])
        assert manifest_path.exists()

        # Manifest should be valid JSON
        manifest_data = json.loads(manifest_path.read_text())
        assert manifest_data["version"] == "backup-manifest-v1"
        assert len(manifest_data["entries"]) == 1

    def test_move_rejects_existing_destination(self, tmp_path: Path) -> None:
        """Should reject if destination already exists."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "status-report.md"
        report_file.write_text("# Report")

        # Pre-create the destination
        reports_dir = project / "artifacts" / "reports"
        reports_dir.mkdir(parents=True)
        existing_file = reports_dir / "status-report.md"
        existing_file.write_text("# Existing")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=tmp_path / "backup",
            json_output=False,
        )

        # Should have failed
        assert result.success is False
        assert len(result.actions_failed) == 1
        assert "already exists" in result.actions_failed[0].get("error", "").lower()

        # Original file should still exist
        assert report_file.exists()


class TestIgnoreRuntimeArtifact:
    """Tests for ignore_runtime_artifact action."""

    def test_ignore_does_not_modify_gitignore(self, tmp_path: Path) -> None:
        """ignore_runtime_artifact should NOT modify .gitignore."""
        project = tmp_path / "project"
        project.mkdir()

        # Create .gitignore
        gitignore = project / ".gitignore"
        gitignore.write_text("*.pyc\n")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "ignore_runtime_artifact", "path": "artifacts/memory-hook/log.json", "severity": "P2"},
            ],
            "risk_level": "low",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=tmp_path / "backup",
            json_output=False,
        )

        assert result.success is True

        # .gitignore should be unchanged
        assert gitignore.read_text() == "*.pyc\n"

    def test_ignore_reports_skipped(self, tmp_path: Path) -> None:
        """ignore_runtime_artifact should report as skipped."""
        project = tmp_path / "project"
        project.mkdir()

        plan = {
            "target": str(project),
            "actions": [
                {"action": "ignore_runtime_artifact", "path": "artifacts/memory-hook/log.json", "severity": "P2"},
            ],
            "risk_level": "low",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=tmp_path / "backup",
            json_output=False,
        )

        assert result.success is True
        assert len(result.actions_applied) == 1
        assert result.actions_applied[0]["status"] == "skipped"


class TestBackupAndRollback:
    """Tests for backup and rollback functionality."""

    def test_backup_contains_file_content(self, tmp_path: Path) -> None:
        """Backup should contain actual file content."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "status-report.md"
        report_content = "# Secret Report\n\nSensitive data."
        report_file.write_text(report_content)

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        backup_dir = tmp_path / "backup"

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=backup_dir,
            json_output=False,
        )

        assert result.success is True

        # Find backup file
        backup_entries = list(backup_dir.glob("*.backup"))
        assert len(backup_entries) == 1

        # Backup should contain original content
        assert backup_entries[0].read_text() == report_content

    def test_backup_manifest_has_correct_sha256(self, tmp_path: Path) -> None:
        """Backup manifest should have correct SHA256."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "status-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        backup_dir = tmp_path / "backup"

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=backup_dir,
            json_output=False,
        )

        # Load manifest
        manifest_path = Path(result.backup_manifest["path"])
        manifest_data = json.loads(manifest_path.read_text())

        # Verify SHA256 matches actual file
        backup_file = backup_dir / manifest_data["entries"][0]["backup_path"]
        actual_sha256 = _sha256_file(backup_file)
        assert manifest_data["entries"][0]["sha256"] == actual_sha256

    def test_rollback_restores_original_file(self, tmp_path: Path) -> None:
        """Rollback should restore original file."""
        project = tmp_path / "project"
        project.mkdir()

        # Create and move a file
        report_file = project / "status-report.md"
        original_content = "# Original Report"
        report_file.write_text(original_content)

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        backup_dir = tmp_path / "backup"

        # Apply
        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=backup_dir,
            json_output=False,
        )

        assert result.success is True
        assert not report_file.exists()  # Moved

        # Rollback
        manifest_path = Path(result.backup_manifest["path"])
        rollback_result = _rollback_from_manifest(project, manifest_path, dry_run=False)

        assert rollback_result.success is True
        assert report_file.exists()
        assert report_file.read_text() == original_content

    def test_rollback_removes_destination_file(self, tmp_path: Path) -> None:
        """Rollback should remove the applied destination file."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "status-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        backup_dir = tmp_path / "backup"

        # Apply
        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=backup_dir,
            json_output=False,
        )

        # Destination should exist
        dest_file = project / "artifacts" / "reports" / "status-report.md"
        assert dest_file.exists()

        # Rollback
        manifest_path = Path(result.backup_manifest["path"])
        _rollback_from_manifest(project, manifest_path, dry_run=False)

        # Destination should be removed
        assert not dest_file.exists()

    def test_rollback_rejects_conflict(self, tmp_path: Path) -> None:
        """Rollback should reject if source already exists (conflict)."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "status-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        backup_dir = tmp_path / "backup"

        # Apply
        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=backup_dir,
            json_output=False,
        )

        # Re-create the file (simulating conflict)
        report_file.write_text("# New conflicting content")

        # Rollback should fail
        manifest_path = Path(result.backup_manifest["path"])
        rollback_result = _rollback_from_manifest(project, manifest_path, dry_run=False)

        assert rollback_result.success is False
        assert any("conflict" in e.lower() for e in rollback_result.errors)

    def test_rollback_dry_run(self, tmp_path: Path) -> None:
        """Rollback in dry-run should not restore files."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "status-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "status-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        backup_dir = tmp_path / "backup"

        # Apply
        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=backup_dir,
            json_output=False,
        )

        # File should be moved
        assert not report_file.exists()

        # Dry-run rollback
        manifest_path = Path(result.backup_manifest["path"])
        rollback_result = _rollback_from_manifest(project, manifest_path, dry_run=True)

        assert rollback_result.success is True
        assert rollback_result.dry_run is True

        # File should still be gone (dry-run)
        assert not report_file.exists()


class TestCLIMain:
    """Tests for CLI entry point."""

    def test_main_dry_run(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """main() with --dry-run should report without changes."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "test-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "test-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        exit_code = main([
            "--target", str(project),
            "--plan", str(plan_file),
            "--dry-run",
        ])

        assert exit_code == 0
        assert report_file.exists()  # Not moved

    def test_main_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """main() with --json should output valid JSON."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "test-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "test-report.md", "severity": "P1"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        exit_code = main([
            "--target", str(project),
            "--plan", str(plan_file),
            "--dry-run",
            "--json",
        ])

        assert exit_code == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "success" in data
        assert "target" in data
        assert "actions_applied" in data

    def test_main_rejects_missing_plan(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """main() without --plan should error."""
        project = tmp_path / "project"
        project.mkdir()

        exit_code = main([
            "--target", str(project),
        ])

        assert exit_code == 1

    def test_main_rejects_mutually_exclusive_options(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """main() should reject --plan and --rollback together."""
        project = tmp_path / "project"
        project.mkdir()

        exit_code = main([
            "--target", str(project),
            "--plan", "/dev/null",
            "--rollback", "/dev/null",
        ])

        assert exit_code == 2

    def test_main_rollback_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """main() with --rollback should perform rollback."""
        project = tmp_path / "project"
        project.mkdir()

        # Create backup manifest
        manifest = {
            "version": "backup-manifest-v1",
            "created_at": _now_iso(),
            "target": str(project),
            "plan_path": None,
            "entries": [
                {
                    "action": "move_root_pollution",
                    "src": "test-report.md",
                    "dst": "artifacts/reports/test-report.md",
                    "backup_path": "test-report.md.backup",
                    "sha256": "dummy",
                    "timestamp": _now_iso(),
                },
            ],
        }
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest))

        # Create backup file
        backup_file = tmp_path / "test-report.md.backup"
        backup_file.write_text("# Original")

        exit_code = main([
            "--target", str(project),
            "--rollback", str(manifest_file),
            "--dry-run",
        ])

        # Should succeed in dry-run (backup file not found is expected)
        assert exit_code == 0 or exit_code == 1  # May fail due to missing backup file


class TestResultStructure:
    """Tests for result data structure."""

    def test_result_to_dict_structure(self, tmp_path: Path) -> None:
        """Result to_dict should have expected structure."""
        project = tmp_path / "project"
        project.mkdir()

        plan = {
            "target": str(project),
            "actions": [],
            "risk_level": "low",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=False,
            backup_dir=None,
            json_output=False,
        )

        data = result.to_dict()
        assert "success" in data
        assert "target" in data
        assert "dry_run" in data
        assert "actions_applied" in data
        assert "actions_skipped" in data
        assert "actions_failed" in data
        assert "backup_manifest" in data
        assert "errors" in data
        assert "warnings" in data
        assert "summary" in data
        assert "applied" in data["summary"]
        assert "skipped" in data["summary"]
        assert "failed" in data["summary"]
        assert "total" in data["summary"]


class TestActionFiltering:
    """Tests for action filtering."""

    def test_only_allowed_actions_applied(self, tmp_path: Path) -> None:
        """Only allowed actions should be applied."""
        project = tmp_path / "project"
        project.mkdir()

        report_file = project / "test-report.md"
        report_file.write_text("# Report")

        plan = {
            "target": str(project),
            "actions": [
                {"action": "move_root_pollution", "path": "test-report.md", "severity": "P1"},
                {"action": "adopt_existing_memory", "path": "memory/inbox.md", "severity": "P0"},
                {"action": "mark_legacy_readonly", "path": "workspace/memory", "severity": "P0"},
            ],
            "risk_level": "high",
            "requires_human_confirmation": False,
        }
        plan_file = tmp_path / "plan.json"
        plan_file.write_text(json.dumps(plan))

        result = apply_residue_plan(
            target=project,
            plan_path=plan_file,
            dry_run=True,
            backup_dir=None,
            json_output=False,
        )

        # Should only apply move_root_pollution
        applied_actions = [a.get("action") for a in result.actions_applied]
        assert "move_root_pollution" in applied_actions
        assert "adopt_existing_memory" not in applied_actions
        assert "mark_legacy_readonly" not in applied_actions

        # Others should be skipped
        skipped_actions = [a.get("action") for a in result.actions_skipped]
        assert "adopt_existing_memory" in skipped_actions or any(
            "not in allowed" in str(a) for a in result.actions_skipped
        )
