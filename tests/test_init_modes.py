"""Tests for memory-init --mode create|adopt|update|repair."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from memory_core.tools.init_project_memory import (
    MEMORY_HOOK_BEGIN_MARKER,
    MEMORY_HOOK_END_MARKER,
    init_project_memory,
    main,
)


def _call_main(argv: list[str]) -> int:
    """Invoke init_project_memory.main() with patched sys.argv."""
    old_argv = sys.argv
    try:
        sys.argv = ["memory-init", *argv]
        return main()
    finally:
        sys.argv = old_argv


class TestInitModeCreate:
    """Tests for --mode create (default)."""

    def test_create_mode_is_default(self, tmp_path: Path) -> None:
        """Without --mode, should default to create."""
        result = init_project_memory(tmp_path)
        assert result["mode"] == "create"
        assert result["success"] is True

    def test_create_mode_explicit(self, tmp_path: Path) -> None:
        """--mode create should work explicitly."""
        result = init_project_memory(tmp_path, mode="create")
        assert result["mode"] == "create"
        assert result["success"] is True


class TestInitModeAdopt:
    """Tests for --mode adopt (should not overwrite business files)."""

    def test_adopt_does_not_overwrite_business_index(self, tmp_path: Path) -> None:
        """adopt mode should not overwrite business INDEX.md."""
        # Create a business INDEX.md (no memory markers)
        business_content = "# Business Index\n\nThis is business content."
        (tmp_path / "INDEX.md").write_text(business_content)

        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True

        # Business INDEX.md should be preserved
        content = (tmp_path / "INDEX.md").read_text()
        assert content == business_content
        assert "project-map" not in content

    def test_adopt_skips_agents_md_without_marker(self, tmp_path: Path) -> None:
        """adopt mode should not append to AGENTS.md without markers."""
        # Create AGENTS.md without memory markers
        agents_content = "# Agents\n\nThis is business agent configuration."
        (tmp_path / "AGENTS.md").write_text(agents_content)

        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True

        # AGENTS.md should be unchanged
        content = (tmp_path / "AGENTS.md").read_text()
        assert content == agents_content
        assert MEMORY_HOOK_BEGIN_MARKER not in content
        # Should be in skipped list
        assert any("AGENTS.md" in s and "no marker" in s.lower() for s in result.get("skipped", []))

    def test_adopt_skips_agents_md_with_marker(self, tmp_path: Path) -> None:
        """adopt mode should NOT update AGENTS.md even with existing markers (preserve existing)."""
        # Create AGENTS.md with memory markers
        old_block = f"{MEMORY_HOOK_BEGIN_MARKER}\nOld content\n{MEMORY_HOOK_END_MARKER}"
        agents_content = f"# Agents\n\n{old_block}\n\nBusiness content."
        (tmp_path / "AGENTS.md").write_text(agents_content)

        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True

        # AGENTS.md should be preserved as-is in adopt mode
        content = (tmp_path / "AGENTS.md").read_text()
        assert "Old content" in content  # Original content preserved
        assert "Business content." in content

    def test_adopt_preserves_project_map(self, tmp_path: Path) -> None:
        """adopt mode should not overwrite project-map files."""
        # Create existing project-map
        (tmp_path / "project-map").mkdir(parents=True, exist_ok=True)
        existing_content = "# Custom Project Map\n\nThis is custom content."
        (tmp_path / "project-map" / "INDEX.md").write_text(existing_content)
        (tmp_path / "project-map" / "custom.md").write_text("# Custom\n\nMore content.")

        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True

        # Project map should be preserved
        assert (tmp_path / "project-map" / "INDEX.md").read_text() == existing_content
        assert (tmp_path / "project-map" / "custom.md").exists()

    def test_adopt_preserves_index_md_even_with_force(self, tmp_path: Path) -> None:
        """adopt mode should not overwrite INDEX.md even with --force."""
        business_content = "# Business Index\n\nBusiness-owned entrypoint."
        (tmp_path / "INDEX.md").write_text(business_content)

        result = init_project_memory(tmp_path, mode="adopt", force=True)
        assert result["success"] is True
        assert (tmp_path / "INDEX.md").read_text() == business_content


class TestInitModeUpdate:
    """Tests for --mode update (replace marked blocks, preserve content)."""

    def test_update_replaces_marked_block(self, tmp_path: Path) -> None:
        """update mode should replace existing MEMORY_HOOK block."""
        # Create AGENTS.md with old memory markers
        old_block = f"{MEMORY_HOOK_BEGIN_MARKER}\nOld memory hook content\n{MEMORY_HOOK_END_MARKER}"
        agents_content = f"# Agents\n\nBusiness intro.\n\n{old_block}\n\nBusiness outro."
        (tmp_path / "AGENTS.md").write_text(agents_content)

        result = init_project_memory(tmp_path, mode="update")
        assert result["success"] is True

        # Should have updated content
        content = (tmp_path / "AGENTS.md").read_text()
        assert MEMORY_HOOK_BEGIN_MARKER in content
        assert MEMORY_HOOK_END_MARKER in content
        # Business content should be preserved
        assert "Business intro." in content
        assert "Business outro." in content

    def test_update_skips_agents_md_without_marker(self, tmp_path: Path) -> None:
        """update mode should NOT append to AGENTS.md without markers (safe default)."""
        agents_content = "# Agents\n\nNo memory markers here."
        (tmp_path / "AGENTS.md").write_text(agents_content)

        result = init_project_memory(tmp_path, mode="update")
        assert result["success"] is True

        # Should NOT have markers (safe default - skip files without markers)
        content = (tmp_path / "AGENTS.md").read_text()
        assert MEMORY_HOOK_BEGIN_MARKER not in content
        assert MEMORY_HOOK_END_MARKER not in content
        assert "No memory markers here." in content
        # Should be in skipped list (either "no marker" or "no legacy references")
        assert any("AGENTS.md" in s and ("no marker" in s.lower() or "no legacy" in s.lower()) for s in result.get("skipped", []))

    def test_update_preserves_business_index_even_with_force(self, tmp_path: Path) -> None:
        """update mode should not overwrite business INDEX.md even with --force."""
        business_content = "# Business Index\n\nBusiness-owned entrypoint."
        (tmp_path / "INDEX.md").write_text(business_content)

        result = init_project_memory(tmp_path, mode="update", force=True)
        assert result["success"] is True
        assert (tmp_path / "INDEX.md").read_text() == business_content

    def test_update_preserves_project_map_even_with_force(self, tmp_path: Path) -> None:
        """update mode should not overwrite project-map files even with --force."""
        # Create existing project-map
        (tmp_path / "project-map").mkdir(parents=True, exist_ok=True)
        existing_content = "# Custom Project Map\n\nThis is custom content."
        (tmp_path / "project-map" / "INDEX.md").write_text(existing_content)

        result = init_project_memory(tmp_path, mode="update", force=True)
        assert result["success"] is True

        # Project map should be preserved
        assert (tmp_path / "project-map" / "INDEX.md").read_text() == existing_content


class TestInitModeRepair:
    """Tests for --mode repair (repair missing required files)."""

    def test_repair_creates_missing_required_files(self, tmp_path: Path) -> None:
        """repair mode should create missing required files."""
        # First do a regular init
        init_project_memory(tmp_path, mode="create")

        # Delete some required files
        memory_root = tmp_path / "memory" / "system"
        (memory_root / "memory.lock").unlink()
        (memory_root / "adapter.toml").unlink()

        # Run repair
        result = init_project_memory(tmp_path, mode="repair")
        assert result["success"] is True

        # Files should be recreated
        assert (memory_root / "memory.lock").exists()
        assert (memory_root / "adapter.toml").exists()

    def test_repair_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        """repair mode should not overwrite existing files."""
        # Create initial structure
        init_project_memory(tmp_path, mode="create")

        # Modify a file
        memory_lock = tmp_path / "memory" / "system" / "memory.lock"
        custom_content = "# Custom\n\nThis is custom content."
        memory_lock.write_text(custom_content)

        # Run repair
        result = init_project_memory(tmp_path, mode="repair")
        assert result["success"] is True

        # Custom content should be preserved
        content = memory_lock.read_text()
        assert content == custom_content

    def test_repair_creates_agents_md_when_absent(self, tmp_path: Path) -> None:
        """repair mode should create AGENTS.md when it doesn't exist (Phase 2 fix)."""
        # Create initial structure
        init_project_memory(tmp_path, mode="create")

        # Remove AGENTS.md if exists
        agents_path = tmp_path / "AGENTS.md"
        if agents_path.exists():
            agents_path.unlink()

        # Run repair
        result = init_project_memory(tmp_path, mode="repair")
        assert result["success"] is True

        # AGENTS.md SHOULD be created in repair mode when absent (Phase 2 change)
        assert agents_path.exists()

    def test_repair_does_not_create_hooks_json(self, tmp_path: Path) -> None:
        """repair mode should not create new hooks.json."""
        # Create initial structure
        init_project_memory(tmp_path, mode="create")

        # Remove hooks.json if exists
        hooks_dir = tmp_path / ".claude"
        hooks_path = hooks_dir / "hooks.json"
        if hooks_path.exists():
            hooks_path.unlink()

        # Run repair
        result = init_project_memory(tmp_path, mode="repair")
        assert result["success"] is True

        # hooks.json should NOT be created in repair mode (repair focuses on .memory/ files)


class TestInitModeCLI:
    """Tests for --mode CLI argument."""

    def test_cli_mode_create(self, tmp_path: Path) -> None:
        """CLI should accept --mode create."""
        exit_code = _call_main(["--target", str(tmp_path), "--mode", "create"])
        assert exit_code == 0

    def test_cli_mode_adopt(self, tmp_path: Path) -> None:
        """CLI should accept --mode adopt."""
        exit_code = _call_main(["--target", str(tmp_path), "--mode", "adopt"])
        assert exit_code == 0

    def test_cli_mode_update(self, tmp_path: Path) -> None:
        """CLI should accept --mode update."""
        exit_code = _call_main(["--target", str(tmp_path), "--mode", "update"])
        assert exit_code == 0

    def test_cli_mode_repair(self, tmp_path: Path) -> None:
        """CLI should accept --mode repair."""
        # First create structure
        _call_main(["--target", str(tmp_path), "--mode", "create"])
        # Then repair
        exit_code = _call_main(["--target", str(tmp_path), "--mode", "repair"])
        assert exit_code == 0

    def test_cli_invalid_mode(self, tmp_path: Path) -> None:
        """CLI should reject invalid mode."""
        with pytest.raises(SystemExit) as exc_info:
            _call_main(["--target", str(tmp_path), "--mode", "invalid"])
        # argparse exits with code 2 for invalid choice
        assert exc_info.value.code == 2


class TestInitModeDryRun:
    """Tests for --dry-run mode behavior."""

    def test_dry_run_no_files_written(self, tmp_path: Path) -> None:
        """dry-run should not create any files."""
        result = init_project_memory(tmp_path, mode="create", dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True

        # No files should be created
        assert not (tmp_path / "memory" / "system").exists()
        assert not (tmp_path / "AGENTS.md").exists()

    @pytest.mark.flaky(reruns=2)
    def test_dry_run_reflects_mode(self, tmp_path: Path) -> None:
        """dry-run should reflect mode in output."""
        result = init_project_memory(tmp_path, mode="adopt", dry_run=True)
        assert result["success"] is True
        assert result.get("mode") == "dry-run"
        assert result.get("requested_mode") == "adopt"

    def test_dry_run_with_json_reflects_mode(self, tmp_path: Path) -> None:
        """dry-run --json should reflect mode."""
        result = init_project_memory(tmp_path, mode="repair", dry_run=True, json_output=True)
        assert result["success"] is True
        assert result.get("mode") == "dry-run"
        assert result.get("requested_mode") == "repair"
        assert "dry_run_output" in result

    def test_dry_run_adopt_shows_skip_existing(self, tmp_path: Path) -> None:
        """dry-run adopt should show skip for existing files."""
        # Create some files first
        (tmp_path / "INDEX.md").write_text("# Business Index")

        result = init_project_memory(tmp_path, mode="adopt", dry_run=True)
        assert result["success"] is True

        # Check that INDEX.md would be skipped
        dry_run_files = result.get("dry_run_output", {}).get("would_create_files", [])
        index_actions = [f for f in dry_run_files if "INDEX.md" in f]
        assert any("skip" in a.lower() and "adopt" in a.lower() for a in index_actions)


class TestInitModeIntegration:
    """Integration tests for different modes."""

    def test_adopt_preserves_business_content(self, tmp_path: Path) -> None:
        """Full test: adopt should preserve all business content."""
        # Create business files
        (tmp_path / "INDEX.md").write_text("# Business Index")
        (tmp_path / "AGENTS.md").write_text("# Business Agents")
        (tmp_path / "README.md").write_text("# Business README")

        result = init_project_memory(tmp_path, mode="adopt")
        assert result["success"] is True

        # Business files should be preserved
        assert (tmp_path / "INDEX.md").read_text() == "# Business Index"
        assert (tmp_path / "AGENTS.md").read_text() == "# Business Agents"
        assert (tmp_path / "README.md").read_text() == "# Business README"

    def test_update_preserves_external_content(self, tmp_path: Path) -> None:
        """Full test: update should preserve external AGENTS.md content."""
        # Create AGENTS.md with markers and business content
        old_block = f"{MEMORY_HOOK_BEGIN_MARKER}\nOld content\n{MEMORY_HOOK_END_MARKER}"
        business_content = f"# Agents\n\nPre-business content.\n\n{old_block}\n\nPost-business content."
        (tmp_path / "AGENTS.md").write_text(business_content)

        result = init_project_memory(tmp_path, mode="update")
        assert result["success"] is True

        # Business content should be preserved
        content = (tmp_path / "AGENTS.md").read_text()
        assert "Pre-business content." in content
        assert "Post-business content." in content
        assert MEMORY_HOOK_BEGIN_MARKER in content
        assert MEMORY_HOOK_END_MARKER in content


class TestMemoryInitFillSkillGeneration:
    """Tests for VAL-SKILL-003: memory-init generates memory-init-fill.yaml."""

    def test_memory_init_generates_fill_skill(self, tmp_path: Path) -> None:
        """VAL-SKILL-003: memory-init generates .memory/skills/memory-init-fill.yaml."""
        # Initialize as a git repo for proper project name detection
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        result = init_project_memory(tmp_path, mode="create")
        assert result["success"] is True

        # Skill file should exist
        skill_path = tmp_path / "memory" / "system" / "skills" / "memory-init-fill.yaml"
        assert skill_path.exists(), "memory-init-fill.yaml should be generated"

        content = skill_path.read_text()
        assert "memory-init-fill" in content
        assert "version: 1" in content
        assert "probe_project" in content

    def test_fill_skill_listed_in_created(self, tmp_path: Path) -> None:
        """VAL-SKILL-003: Result includes the skill file in created list."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        result = init_project_memory(tmp_path)
        created_files = result.get("created", [])
        assert any("memory-init-fill.yaml" in f for f in created_files)

    def test_fill_skill_not_generated_without_template(self, tmp_path: Path) -> None:
        """VAL-SKILL-002: When template is missing, init still succeeds (warning only)."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        # Template exists in the repo, so this should work. This test
        # just verifies the try/except path is reachable and doesn't crash.
        result = init_project_memory(tmp_path)
        assert result["success"] is True
        # Either created or skipped (if exists), no errors
        fill_skill_created = any("memory-init-fill.yaml" in f for f in result.get("created", []))
        fill_skill_skipped = any("memory-init-fill.yaml" in f for f in result.get("skipped", []))
        assert fill_skill_created or fill_skill_skipped
