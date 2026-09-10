"""Tests for install hardening (M1-5): VAL-REL-006 + VAL-REL-012.

VAL-REL-006: settings.json dead-key injection — install must NOT inject hooks
  key into settings.json (hooks.json is the real registration since 2026-08-17).
  Existing dead hooks in settings.json should be cleaned.

VAL-REL-012: wrapper auto-backup — install must backup existing wrapper before
  re-rendering (previously only settings.json was backed up).
"""

import json
import stat
from pathlib import Path

import pytest

from memory_core.tools.factory_global_hooks import (
    install_factory_hooks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_memory_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Create fake gateway/init executables for testing."""
    command_dir = tmp_path / "bin"
    command_dir.mkdir()
    gateway = command_dir / "memory-hook-gateway"
    gateway.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gateway.chmod(gateway.stat().st_mode | stat.S_IXUSR)
    init = command_dir / "memory-init"
    init.write_text(
        "#!/bin/sh\n"
        'host=""\n'
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in\n'
        '    --target) shift; target="$1" ;;\n'
        '    --host) shift; host="$1" ;;\n'
        "  esac\n"
        "  shift\n"
        "done\n"
        'mkdir -p "$target/memory/system"\n'
        'echo "$host" > "$target/memory/system/init-host"\n',
        encoding="utf-8",
    )
    init.chmod(init.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(command_dir))
    return gateway, init


# ---------------------------------------------------------------------------
# VAL-REL-006: settings.json dead-key injection tests
# ---------------------------------------------------------------------------


class TestSettingsDeadKeyInjection:
    """VAL-REL-006: install must NOT inject hooks key into settings.json."""

    def test_install_does_not_inject_hooks_into_settings_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """install must NOT write hooks entries into settings.json.

        hooks.json is the real registration since 2026-08-17.
        settings.json hooks key is a dead key that must not be injected.
        """
        factory_home = tmp_path / ".factory"
        storage_root = tmp_path / "memory-store"
        _fake_memory_commands(tmp_path, monkeypatch)

        result = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)

        assert result["success"] is True
        settings_file = factory_home / "settings.json"

        # settings.json should NOT have hooks key with memory hook entries
        if settings_file.exists():
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            hooks = settings.get("hooks", {})
            # No memory hook commands should be in settings.json hooks
            for _event_name, event_groups in hooks.items():
                for group in event_groups:
                    for hook in group.get("hooks", []):
                        command = hook.get("command", "")
                        assert "memory-hook" not in command, (
                            f"settings.json hooks must not contain memory-hook: {command}"
                        )

    def test_install_cleans_existing_dead_hooks_from_settings_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """install should clean existing dead hooks from settings.json.

        If settings.json already has dead hooks entries, install should
        filter them out rather than preserving them.
        """
        factory_home = tmp_path / ".factory"
        factory_home.mkdir()
        settings_file = factory_home / "settings.json"

        # Pre-populate settings.json with dead hooks
        dead_settings = {
            "model": "keep-me",
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "/old/path/memory-hook-gateway.py --host factory --event session-start",
                                "timeout": 10,
                            }
                        ]
                    }
                ],
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 /old/memory_hook_gateway.py --host factory --event prompt-submit",
                                "timeout": 10,
                            }
                        ]
                    }
                ],
                "PreToolUse": [
                    {
                        "matcher": "Execute",
                        "hooks": [{"type": "command", "command": "keep-this-guard"}],
                    }
                ],
            },
        }
        settings_file.write_text(json.dumps(dead_settings), encoding="utf-8")

        _fake_memory_commands(tmp_path, monkeypatch)

        result = install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "store")
        assert result["success"] is True

        # Re-read settings.json: dead hooks should be cleaned
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
        assert settings["model"] == "keep-me"

        # Dead memory hooks should be removed
        session_start_hooks = settings.get("hooks", {}).get("SessionStart", [])
        for group in session_start_hooks:
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                assert "memory-hook-gateway.py" not in command
                assert "memory_hook_gateway.py" not in command

        # Non-memory hooks should be preserved
        pretooluse_hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert len(pretooluse_hooks) >= 1

    def test_dry_run_does_not_plan_hooks_injection(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """--dry-run should not plan hooks injection into settings.json."""
        factory_home = tmp_path / ".factory"
        storage_root = tmp_path / "memory-store"
        _fake_memory_commands(tmp_path, monkeypatch)

        result = install_factory_hooks(factory_home=factory_home, storage_root=storage_root, dry_run=True)

        assert result["success"] is True
        assert result["dry_run"] is True

        # The settings preview should NOT contain memory hook entries
        settings_preview = result.get("settings", {})
        hooks = settings_preview.get("hooks", {})
        for _event_name, event_groups in hooks.items():
            for group in event_groups:
                for hook in group.get("hooks", []):
                    command = hook.get("command", "")
                    # Memory hooks should not be planned for settings.json
                    assert "memory-hook" not in command, f"dry-run should not plan memory hook injection: {command}"


# ---------------------------------------------------------------------------
# VAL-REL-012: wrapper auto-backup tests
# ---------------------------------------------------------------------------


class TestWrapperAutoBackup:
    """VAL-REL-012: install must backup wrapper before re-rendering."""

    def test_install_backs_up_existing_wrapper(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """install must backup existing wrapper before overwriting."""
        factory_home = tmp_path / ".factory"
        storage_root = tmp_path / "memory-store"
        _fake_memory_commands(tmp_path, monkeypatch)

        # First install: creates wrapper
        result1 = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)
        assert result1["success"] is True

        wrapper = factory_home / "bin" / "memory-hook"
        assert wrapper.is_file()
        original_content = wrapper.read_text(encoding="utf-8")

        # Second install: should backup existing wrapper
        result2 = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)
        assert result2["success"] is True

        # Check that a backup was created
        wrapper_backups = list(wrapper.parent.glob("memory-hook.bak.*"))
        assert len(wrapper_backups) >= 1, (
            f"Expected wrapper backup in {wrapper.parent}, found: {list(wrapper.parent.iterdir())}"
        )

        # Backup content should match original
        backup_content = wrapper_backups[0].read_text(encoding="utf-8")
        assert backup_content == original_content

    def test_wrapper_backup_appears_in_result_backups_list(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """wrapper backup path should appear in result['backups']."""
        factory_home = tmp_path / ".factory"
        storage_root = tmp_path / "memory-store"
        _fake_memory_commands(tmp_path, monkeypatch)

        # First install
        install_factory_hooks(factory_home=factory_home, storage_root=storage_root)

        # Second install: should list wrapper backup
        result = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)
        assert result["success"] is True

        backups = result.get("backups", [])

        # At least one backup should be the wrapper backup
        wrapper_backups = [b for b in backups if "memory-hook.bak" in b]
        assert len(wrapper_backups) >= 1, f"Expected wrapper backup in result['backups'], got: {backups}"

    def test_no_backup_on_first_install(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """First install (no existing wrapper) should not create wrapper backup."""
        factory_home = tmp_path / ".factory"
        storage_root = tmp_path / "memory-store"
        _fake_memory_commands(tmp_path, monkeypatch)

        result = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)
        assert result["success"] is True

        wrapper = factory_home / "bin" / "memory-hook"
        # No wrapper backups should exist
        wrapper_backups = list(wrapper.parent.glob("memory-hook.bak.*"))
        assert len(wrapper_backups) == 0

    def test_dry_run_does_not_create_backup(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """--dry-run should not create any backups."""
        factory_home = tmp_path / ".factory"
        storage_root = tmp_path / "memory-store"
        _fake_memory_commands(tmp_path, monkeypatch)

        # First real install
        install_factory_hooks(factory_home=factory_home, storage_root=storage_root)

        wrapper = factory_home / "bin" / "memory-hook"
        backups_before = list(wrapper.parent.glob("memory-hook.bak.*"))

        # Dry run should not create new backups
        result = install_factory_hooks(factory_home=factory_home, storage_root=storage_root, dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True

        backups_after = list(wrapper.parent.glob("memory-hook.bak.*"))
        assert len(backups_after) == len(backups_before), (
            f"dry-run should not create backups: before={len(backups_before)}, after={len(backups_after)}"
        )

    def test_wrapper_backup_preserves_executable_permission(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Backup should preserve the original wrapper's executable permission."""
        factory_home = tmp_path / ".factory"
        storage_root = tmp_path / "memory-store"
        _fake_memory_commands(tmp_path, monkeypatch)

        # First install
        install_factory_hooks(factory_home=factory_home, storage_root=storage_root)
        wrapper = factory_home / "bin" / "memory-hook"
        original_mode = wrapper.stat().st_mode

        # Second install: should backup with same permissions
        install_factory_hooks(factory_home=factory_home, storage_root=storage_root)

        wrapper_backups = list(wrapper.parent.glob("memory-hook.bak.*"))
        assert len(wrapper_backups) >= 1
        backup_mode = wrapper_backups[0].stat().st_mode

        # Permissions should be preserved (shutil.copy2 preserves metadata)
        assert stat.S_IMODE(original_mode) == stat.S_IMODE(backup_mode)
