"""Tests for memory-init integration with global KB.

Covers validation assertions:
- VAL-STRUCT-002: memory-init automatically creates global KB structure
- VAL-INIT-001: init creates adapter.toml with [global_kb] section
- VAL-INIT-002: init --dry-run doesn't actually write
- VAL-INIT-003: update mode doesn't overwrite existing [global_kb] config
- VAL-CROSS-001: init full flow (config → routing works)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_core.tools.adapter_toml_schema import load_adapter_toml
from memory_core.tools.global_kb_init import (
    create_global_kb_structure,
    is_global_kb_initialized,
)
from memory_core.tools.init_project_memory import init_project_memory


class TestInitCreatesGlobalKbStructure:
    """VAL-STRUCT-002: memory-init automatically creates global KB structure."""

    def test_init_creates_global_kb_when_not_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """memory-init should create global KB structure if it doesn't exist."""
        # Mock HOME to use tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))
        global_kb_root = tmp_path / ".memory" / "global-kb"

        # Verify it doesn't exist yet
        assert not global_kb_root.exists()

        # Run init
        project = tmp_path / "test-project"
        project.mkdir()
        result = init_project_memory(project, dry_run=False)

        assert result["success"], f"Init failed: {result['errors']}"

        # Verify global KB structure was created
        assert global_kb_root.exists()
        assert (global_kb_root / "operations").is_dir()
        assert (global_kb_root / "engineering").is_dir()
        assert (global_kb_root / "collaboration").is_dir()
        assert (global_kb_root / "pending").is_dir()
        assert (global_kb_root / "INDEX.md").is_file()

    def test_init_idempotent_does_not_overwrite_existing_index(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If global KB INDEX.md already exists, init should not overwrite it."""
        monkeypatch.setenv("HOME", str(tmp_path))
        global_kb_root = tmp_path / ".memory" / "global-kb"

        # Create global KB structure with custom INDEX.md
        create_global_kb_structure(global_kb_root)
        original_index = (global_kb_root / "INDEX.md").read_text()
        custom_content = "# Custom Index\n\nThis is custom content."
        (global_kb_root / "INDEX.md").write_text(custom_content)

        # Run init
        project = tmp_path / "test-project"
        project.mkdir()
        result = init_project_memory(project, dry_run=False)

        assert result["success"]

        # Verify INDEX.md was NOT overwritten
        current_index = (global_kb_root / "INDEX.md").read_text()
        assert current_index == custom_content
        assert current_index != original_index


class TestInitCreatesAdapterTomlWithGlobalKb:
    """VAL-INIT-001: init creates adapter.toml with [global_kb] section."""

    def test_init_adapter_toml_has_global_kb_section(self, tmp_path: Path) -> None:
        """adapter.toml should contain [global_kb] section after init."""
        project = tmp_path / "test-project"
        project.mkdir()

        result = init_project_memory(project, dry_run=False)
        assert result["success"], f"Init failed: {result['errors']}"

        # Load and verify adapter.toml
        adapter_path = project / "memory" / "system" / "adapter.toml"
        assert adapter_path.exists()

        adapter_content = adapter_path.read_text()
        assert "[global_kb]" in adapter_content

        # Load with schema to verify structure
        config = load_adapter_toml(adapter_path)
        assert config.global_kb_enabled is True
        # root should be default ~/.memory/global-kb (expanded)
        assert config.global_kb_root == str(Path("~/.memory/global-kb").expanduser())

    def test_init_adapter_toml_global_kb_enabled_by_default(self, tmp_path: Path) -> None:
        """[global_kb] enabled should default to true."""
        project = tmp_path / "test-project"
        project.mkdir()

        result = init_project_memory(project, dry_run=False)
        assert result["success"]

        adapter_path = project / "memory" / "system" / "adapter.toml"
        config = load_adapter_toml(adapter_path)

        assert config.global_kb_enabled is True


class TestInitDryRunDoesNotWrite:
    """VAL-INIT-002: init --dry-run doesn't actually write."""

    def test_init_dry_run_does_not_create_global_kb(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--dry-run should not create global KB structure."""
        monkeypatch.setenv("HOME", str(tmp_path))
        global_kb_root = tmp_path / ".memory" / "global-kb"

        project = tmp_path / "test-project"
        project.mkdir()

        result = init_project_memory(project, dry_run=True)
        assert result["success"]
        assert result["dry_run"] is True

        # Verify global KB was NOT created
        assert not global_kb_root.exists()

    def test_init_dry_run_does_not_create_adapter_toml(self, tmp_path: Path) -> None:
        """--dry-run should not create adapter.toml."""
        project = tmp_path / "test-project"
        project.mkdir()

        result = init_project_memory(project, dry_run=True)
        assert result["success"]
        assert result["dry_run"] is True

        # Verify adapter.toml was NOT created
        adapter_path = project / "memory" / "system" / "adapter.toml"
        assert not adapter_path.exists()


class TestInitUpdateModePreservesGlobalKb:
    """VAL-INIT-003: update mode doesn't overwrite existing [global_kb] config."""

    def test_init_update_preserves_custom_global_kb_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Update mode should not overwrite custom [global_kb] root."""
        monkeypatch.setenv("HOME", str(tmp_path))

        project = tmp_path / "test-project"
        project.mkdir()

        # First init with default config
        result1 = init_project_memory(project, dry_run=False)
        assert result1["success"]

        # Manually modify adapter.toml to have custom root
        adapter_path = project / "memory" / "system" / "adapter.toml"
        custom_content = adapter_path.read_text()
        custom_root = "/custom/global-kb/path"
        custom_content = custom_content.replace(
            'root = "~/.memory/global-kb"',
            f'root = "{custom_root}"'
        )
        adapter_path.write_text(custom_content)

        # Verify custom config
        config_before = load_adapter_toml(adapter_path)
        assert config_before.global_kb_root == custom_root

        # Run init in update mode
        result2 = init_project_memory(project, mode="update", dry_run=False)
        assert result2["success"]

        # Verify custom root was preserved
        config_after = load_adapter_toml(adapter_path)
        assert config_after.global_kb_root == custom_root

    def test_init_update_preserves_disabled_global_kb(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Update mode should not overwrite disabled [global_kb]."""
        monkeypatch.setenv("HOME", str(tmp_path))

        project = tmp_path / "test-project"
        project.mkdir()

        # First init
        result1 = init_project_memory(project, dry_run=False)
        assert result1["success"]

        # Manually disable global KB
        adapter_path = project / "memory" / "system" / "adapter.toml"
        custom_content = adapter_path.read_text()
        custom_content = custom_content.replace("enabled = true", "enabled = false")
        adapter_path.write_text(custom_content)

        # Verify disabled
        config_before = load_adapter_toml(adapter_path)
        assert config_before.global_kb_enabled is False

        # Run init in update mode
        result2 = init_project_memory(project, mode="update", dry_run=False)
        assert result2["success"]

        # Verify still disabled
        config_after = load_adapter_toml(adapter_path)
        assert config_after.global_kb_enabled is False


class TestInitFullFlowRouting:
    """VAL-CROSS-001: init full flow - config → routing works."""

    def test_init_enables_routing_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """After init, routing fallback should be enabled."""
        monkeypatch.setenv("HOME", str(tmp_path))
        global_kb_root = tmp_path / ".memory" / "global-kb"

        project = tmp_path / "test-project"
        project.mkdir()

        # Run init
        result = init_project_memory(project, dry_run=False)
        assert result["success"]

        # Verify global KB structure exists
        assert global_kb_root.exists()
        assert is_global_kb_initialized(global_kb_root)

        # Verify adapter.toml has [global_kb] enabled
        adapter_path = project / "memory" / "system" / "adapter.toml"
        config = load_adapter_toml(adapter_path)
        assert config.global_kb_enabled is True

        # Create a file in global KB
        global_file = global_kb_root / "operations" / "global-guide.md"
        global_file.write_text("# Global Guide\n\nGlobal knowledge.")

        # Build runtime profile and verify global KB is in profile
        from memory_core.tools.memory_hook_adapters.default_runtime_profile import build_default_runtime_profile

        profile = build_default_runtime_profile(project, project)
        assert "GLOBAL_KB_ROOT" in profile
        assert profile["GLOBAL_KB_ENABLED"] is True

        # Test routing can find global file
        from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl

        route_policy = RouteTargetPolicyImpl(
            workspace_root=project,
            repo_root=project,
            global_kb_root=global_kb_root,
            global_kb_enabled=True,
        )

        resolved = route_policy.resolve_kb_file("operations", "global-guide.md")
        assert resolved == global_file
