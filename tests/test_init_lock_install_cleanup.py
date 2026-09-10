"""Tests for M1 fix C: init exclusive_lock + install cleanup.

Covers:
- Idempotent install: no backup when content unchanged
- Corrupted settings.json: skip write, add warning
- Concurrent init: exclusive_lock protection
- Dead code removal: desired_factory_hooks and timeout parameter
"""

import json
import stat
from pathlib import Path

import pytest

from memory_core.tools.factory_global_hooks import install_factory_hooks

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
# Idempotent install: skip backup when content unchanged
# ---------------------------------------------------------------------------


class TestIdempotentInstall:
    """Idempotent install: no backup when content unchanged."""

    def test_idempotent_install_no_backup_when_unchanged(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Second install with unchanged content should not create backup."""
        factory_home = tmp_path / ".factory"
        storage_root = tmp_path / "memory-store"
        _fake_memory_commands(tmp_path, monkeypatch)

        # First install
        result1 = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)
        assert result1["success"] is True

        settings_file = factory_home / "settings.json"
        assert settings_file.exists()
        settings_after_first = settings_file.read_text(encoding="utf-8")

        # Second install (idempotent)
        result2 = install_factory_hooks(factory_home=factory_home, storage_root=storage_root)
        assert result2["success"] is True

        # No backup should be created
        settings_backups = list(settings_file.parent.glob("settings.json.bak.*"))
        assert len(settings_backups) == 0, f"Idempotent install should not create backup, found: {settings_backups}"

        # Content should be unchanged
        settings_after_second = settings_file.read_text(encoding="utf-8")
        assert settings_after_second == settings_after_first

    def test_backup_created_when_content_changed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Install should backup when content actually changes."""
        factory_home = tmp_path / ".factory"
        factory_home.mkdir()
        settings_file = factory_home / "settings.json"

        # Pre-populate with different content
        old_settings = {"model": "old-model", "hooks": {}}
        settings_file.write_text(json.dumps(old_settings), encoding="utf-8")

        _fake_memory_commands(tmp_path, monkeypatch)

        result = install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "store")
        assert result["success"] is True

        # Backup should be created
        settings_backups = list(settings_file.parent.glob("settings.json.bak.*"))
        assert len(settings_backups) == 1, f"Expected 1 backup when content changed, found: {settings_backups}"

        # Backup should contain old content
        backup_content = json.loads(settings_backups[0].read_text(encoding="utf-8"))
        assert backup_content["model"] == "old-model"


# ---------------------------------------------------------------------------
# Corrupted settings.json handling
# ---------------------------------------------------------------------------


class TestCorruptedSettings:
    """Corrupted settings.json: skip write, add warning."""

    def test_corrupted_json_skipped_with_warning(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Corrupted settings.json should be skipped with warning."""
        factory_home = tmp_path / ".factory"
        factory_home.mkdir()
        settings_file = factory_home / "settings.json"

        # Write corrupted JSON
        corrupted_content = '{"model": "test", "hooks": {INVALID JSON'
        settings_file.write_text(corrupted_content, encoding="utf-8")

        _fake_memory_commands(tmp_path, monkeypatch)

        result = install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "store")

        assert result["success"] is True

        # Warning should be added
        assert len(result["warnings"]) > 0
        assert any("corrupt" in w.lower() or "invalid" in w.lower() for w in result["warnings"])

        # Corrupted file should be preserved (not overwritten)
        preserved_content = settings_file.read_text(encoding="utf-8")
        assert preserved_content == corrupted_content

    def test_empty_file_treated_as_corrupt(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Empty settings.json should be treated as corrupted."""
        factory_home = tmp_path / ".factory"
        factory_home.mkdir()
        settings_file = factory_home / "settings.json"

        # Write empty file
        settings_file.write_text("", encoding="utf-8")

        _fake_memory_commands(tmp_path, monkeypatch)

        result = install_factory_hooks(factory_home=factory_home, storage_root=tmp_path / "store")

        assert result["success"] is True
        assert len(result["warnings"]) > 0

        # Empty file should be preserved
        preserved_content = settings_file.read_text(encoding="utf-8")
        assert preserved_content == ""


# ---------------------------------------------------------------------------
# Concurrent init with exclusive_lock
# ---------------------------------------------------------------------------


class TestConcurrentInit:
    """Concurrent init: exclusive_lock protection."""

    def test_concurrent_init_no_interleaved_writes(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Multiple concurrent init processes should not interleave writes."""
        import concurrent.futures
        import subprocess
        import sys

        # Create target directory
        target = tmp_path / "project"
        target.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=target, check=True, capture_output=True)

        # Use real CLI entry point (python -m memory_core.tools.init_project_memory)
        # Run 8 concurrent init processes
        def run_init():
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "memory_core.tools.init_project_memory",
                    "--target",
                    str(target),
                    "--host",
                    "factory",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(tmp_path),  # Ensure module can be found
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(run_init) for _ in range(8)]
            results = [f.result() for f in futures]

        # All should succeed
        assert all(r.returncode == 0 for r in results), (
            f"Concurrent init failed: {[r.stderr for r in results if r.returncode != 0]}"
        )

        # AGENTS.md should exist and be valid
        agents_md = target / "AGENTS.md"
        assert agents_md.exists()

        content = agents_md.read_text(encoding="utf-8")

        # Should have exactly one pair of markers (no interleaving)
        begin_count = content.count("<!-- MEMORY_HOOK_BEGIN -->")
        end_count = content.count("<!-- MEMORY_HOOK_END -->")

        assert begin_count == 1, f"Expected 1 MEMORY_HOOK_BEGIN marker, found {begin_count} (interleaved writes?)"
        assert end_count == 1, f"Expected 1 MEMORY_HOOK_END marker, found {end_count} (interleaved writes?)"

        # Markers should be properly paired
        begin_idx = content.index("<!-- MEMORY_HOOK_BEGIN -->")
        end_idx = content.index("<!-- MEMORY_HOOK_END -->")
        assert begin_idx < end_idx, "Markers are not properly ordered"


# ---------------------------------------------------------------------------
# Dead code removal verification
# ---------------------------------------------------------------------------


class TestDeadCodeRemoval:
    """Dead code removal: desired_factory_hooks and timeout parameter."""

    def test_desired_factory_hooks_removed(self) -> None:
        """desired_factory_hooks function should be removed."""
        from memory_core.tools import factory_global_hooks

        assert not hasattr(factory_global_hooks, "desired_factory_hooks"), (
            "desired_factory_hooks should be removed (dead code)"
        )

    def test_install_no_timeout_parameter(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """install_factory_hooks should not accept timeout parameter."""
        import inspect

        sig = inspect.signature(install_factory_hooks)
        params = list(sig.parameters.keys())

        assert "timeout" not in params, f"install_factory_hooks should not have timeout parameter, found: {params}"
