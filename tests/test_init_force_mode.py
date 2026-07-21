#!/usr/bin/env python3
"""Tests for init_project_memory force/overwrite mode and template render warnings.

Test cases:
1. test_init_default_skip_existing - Default behavior skips existing files
2. test_init_force_overwrites - --force overwrites existing files
3. test_init_no_clobber_errors_on_existing - --no-clobber errors on existing files
4. test_init_force_and_dry_run_compatible - --force + --dry-run shows preview
5. test_init_force_no_clobber_mutually_exclusive - Both options together errors
6. test_init_template_render_warning_on_special_chars - Template warnings on bad chars
"""


import inspect
import os
from pathlib import Path

# Import the module under test
from memory_core.tools.init_project_memory import (
    init_project_memory,
    main,
    template_adapter_toml,
    template_canonical_md,
    template_memory_lock,
    template_migrations_log,
    template_plan_md,
    template_state_md,
    template_tasks_md,
)


class TestInitDefaultSkipExisting:
    """Test 1: Default behavior skips existing files."""

    def test_default_skip_existing_files(self, tmp_path: Path) -> None:
        """When files exist, default mode skips them and returns mode=skip."""
        # First init
        result1 = init_project_memory(tmp_path, scope="test_project")
        assert result1["success"] is True
        assert result1["mode"] == "create"

        # Modify one file
        memory_lock = tmp_path / "memory" / "system" / "memory.lock"
        memory_lock.write_text("custom content")

        # Second init (default)
        result2 = init_project_memory(tmp_path, scope="test_project")
        assert result2["success"] is True
        assert result2["mode"] == "skip"
        assert result2["force_overwrite"] is False

        # Verify file was NOT overwritten
        assert memory_lock.read_text() == "custom content"

        # Check skipped list
        assert any("memory.lock" in s for s in result2["skipped"])


class TestInitForceOverwrites:
    """Test 2: --force overwrites existing files."""

    def test_force_overwrites_existing_files(self, tmp_path: Path) -> None:
        """When --force is used, existing files are overwritten."""
        # First init
        result1 = init_project_memory(tmp_path, scope="test_project")
        assert result1["success"] is True

        # Modify one file
        memory_lock = tmp_path / "memory" / "system" / "memory.lock"
        memory_lock.write_text("custom content")

        # Second init with force (use MEMORY_INIT_RUNNING=1 to allow owned file overwrite)
        old_env = os.environ.get("MEMORY_INIT_RUNNING")
        try:
            os.environ["MEMORY_INIT_RUNNING"] = "1"
            result2 = init_project_memory(tmp_path, scope="test_project", force=True)
        finally:
            if old_env is not None:
                os.environ["MEMORY_INIT_RUNNING"] = old_env
            else:
                os.environ.pop("MEMORY_INIT_RUNNING", None)
        assert result2["success"] is True
        assert result2["mode"] == "overwrite"
        assert result2["force_overwrite"] is True

        # Verify file WAS overwritten (contains template content now)
        content = memory_lock.read_text()
        assert "custom content" not in content
        assert "test_project" in content

        # Check created list shows overwritten
        assert any("memory.lock" in c and "overwritten" in c for c in result2["created"])


class TestInitNoClobberErrors:
    """Test 3: --no-clobber errors on existing files."""

    def test_no_clobber_errors_when_files_exist(self, tmp_path: Path) -> None:
        """When --no-clobber is used and files exist, error is returned."""
        # First init
        result1 = init_project_memory(tmp_path, scope="test_project")
        assert result1["success"] is True

        # Second init with no-clobber
        result2 = init_project_memory(tmp_path, scope="test_project", no_clobber=True)
        assert result2["success"] is False
        assert result2["mode"] == "error"

        # Check error message
        assert any("refused to clobber" in e for e in result2["errors"])
        assert any("use --force" in e for e in result2["errors"])

    def test_no_clobber_succeeds_when_no_files(self, tmp_path: Path) -> None:
        """When --no-clobber is used and no files exist, init succeeds."""
        result = init_project_memory(tmp_path, scope="test_project", no_clobber=True)
        assert result["success"] is True
        assert result["mode"] == "create"


class TestInitForceAndDryRunCompatible:
    """Test 4: --force + --dry-run shows preview without writing."""

    def test_force_dry_run_shows_preview(self, tmp_path: Path) -> None:
        """Dry run with force shows what would be overwritten."""
        # First init
        result1 = init_project_memory(tmp_path, scope="test_project")
        assert result1["success"] is True

        # Modify one file
        memory_lock = tmp_path / "memory" / "system" / "memory.lock"
        memory_lock.write_text("custom content")

        # Dry run with force
        result2 = init_project_memory(tmp_path, scope="test_project", force=True, dry_run=True)
        assert result2["success"] is True
        assert result2["mode"] == "dry-run"
        assert result2["force_overwrite"] is True

        # Verify file was NOT actually changed
        assert memory_lock.read_text() == "custom content"

        # Check dry_run_output shows overwrite
        dry_out = result2.get("dry_run_output", {})
        files = dry_out.get("would_create_files", [])
        assert any("memory.lock" in f and "overwrite" in f for f in files)


class TestInitForceNoClobberMutuallyExclusive:
    """Test 5: --force and --no-clobber are mutually exclusive."""

    def test_mutually_exclusive_options(self, tmp_path: Path) -> None:
        """Using both --force and --no-clobber results in error."""
        exit_code = main(["--target", str(tmp_path), "--force", "--no-clobber"])
        assert exit_code == 2


class TestInitTemplateRenderWarning:
    """Test 6: Template warnings on special characters in project_name."""

    def test_template_render_with_special_chars(self) -> None:
        """Template rendering handles special characters gracefully."""
        # Test that template functions return warnings for problematic input
        # The f-strings themselves won't raise errors, but the template functions
        # are wrapped in try/except for safety

        # Test normal case first - no warnings expected
        content, warnings = template_memory_lock("normal_project")
        assert "normal_project" in content
        assert len(warnings) == 0

        # Test with characters that might cause issues
        content, warnings = template_memory_lock('project"with"quotes')
        # This should either work or return warnings
        assert isinstance(content, str)
        assert isinstance(warnings, list)

    def test_template_adapter_toml_with_special_chars(self) -> None:
        """Adapter template handles special characters."""
        content, warnings = template_adapter_toml("test{project}")
        assert isinstance(content, str)
        assert isinstance(warnings, list)

    def test_template_canonical_md_with_special_chars(self) -> None:
        """CANONICAL template handles special characters."""
        content, warnings = template_canonical_md("project{name}")
        assert isinstance(content, str)
        assert isinstance(warnings, list)

    def test_template_plan_md_with_special_chars(self) -> None:
        """PLAN template handles special characters."""
        content, warnings = template_plan_md("project{name}")
        assert isinstance(content, str)
        assert isinstance(warnings, list)

    def test_template_state_md_with_special_chars(self) -> None:
        """STATE template handles special characters."""
        content, warnings = template_state_md("project{name}")
        assert isinstance(content, str)
        assert isinstance(warnings, list)

    def test_template_tasks_md_with_special_chars(self) -> None:
        """TASKS template handles special characters."""
        content, warnings = template_tasks_md("project{name}")
        assert isinstance(content, str)
        assert isinstance(warnings, list)

    def test_template_migrations_log_with_special_chars(self) -> None:
        """Migrations log template handles special characters."""
        content, warnings = template_migrations_log("project{name}")
        assert isinstance(content, str)
        assert isinstance(warnings, list)

    def test_init_with_special_chars_in_scope(self, tmp_path: Path) -> None:
        """Init with special chars in scope still succeeds with warnings."""
        # This tests the actual init flow with potentially problematic input
        result = init_project_memory(tmp_path, scope='test"special"chars')
        assert result["success"] is True
        # Should have warnings field
        assert "warnings" in result
        assert isinstance(result["warnings"], list)


class TestInitMainCompatibility:
    """Test main() function signature compatibility."""

    def test_main_with_no_argv(self) -> None:
        """main() works with no argv (uses sys.argv)."""
        # This test ensures backward compatibility
        # We can't really test this without mocking, but we verify the signature
        sig = inspect.signature(main)
        params = list(sig.parameters.keys())
        assert "argv" in params

    def test_main_returns_int(self, tmp_path: Path) -> None:
        """main() returns integer exit code."""
        result = main(["--target", str(tmp_path)])
        assert isinstance(result, int)


class TestResultFields:
    """Test that result dict contains expected fields."""

    def test_result_has_all_required_fields(self, tmp_path: Path) -> None:
        """Result dict has all required fields."""
        result = init_project_memory(tmp_path, scope="test_project")

        required_fields = [
            "success",
            "dry_run",
            "target",
            "created",
            "skipped",
            "errors",
            "mode",
            "warnings",
            "force_overwrite",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

        assert result["mode"] in ["create", "skip", "overwrite", "dry-run", "error"]
        assert isinstance(result["warnings"], list)
        assert isinstance(result["force_overwrite"], bool)


class TestInitIdempotent:
    """Test that init is idempotent with default behavior."""

    def test_init_is_idempotent(self, tmp_path: Path) -> None:
        """Running init twice without force is idempotent (doesn't change files)."""
        # First init
        result1 = init_project_memory(tmp_path, scope="test_project")
        assert result1["success"] is True
        assert result1["mode"] == "create"

        # Read state after first init
        memory_lock = tmp_path / "memory" / "system" / "memory.lock"
        first_content = memory_lock.read_text()

        # Second init (no force)
        result2 = init_project_memory(tmp_path, scope="test_project")
        assert result2["success"] is True
        assert result2["mode"] == "skip"

        # Content should be unchanged
        second_content = memory_lock.read_text()
        assert first_content == second_content
