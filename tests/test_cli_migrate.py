"""Smoke tests for memory-migrate CLI entry point.

Tests call memory_core.tools.migrate_project_memory.main() directly
(import, not subprocess).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from memory_core.constants import CURRENT_MEMORY_VERSION

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_main(argv: list[str]) -> int:
    """Invoke migrate_project_memory.main() with patched sys.argv."""
    from memory_core.tools.migrate_project_memory import main
    old_argv = sys.argv
    try:
        sys.argv = ["memory-migrate", *argv]
        return main()
    finally:
        sys.argv = old_argv


def _create_memory_skeleton(
    tmp_path: Path,
    *,
    version: str = CURRENT_MEMORY_VERSION,
    adapter_version: str = "0.1.0",
) -> Path:
    """Create a minimal .memory/ skeleton suitable for migration testing."""
    memory_root = tmp_path / ".memory"
    memory_root.mkdir()
    (memory_root / "kb" / "projects").mkdir(parents=True)
    (memory_root / "kb" / "decisions").mkdir(parents=True)
    (memory_root / "kb" / "lessons").mkdir(parents=True)
    (memory_root / "kb" / "global").mkdir(parents=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (memory_root / "memory.lock").write_text(
        f'# memory.lock\n[memory]\nmemory_version = "{version}"\n'
        f'schema_version = "context-package-v1"\nadapter_version = "builtin"\n'
        f'locked_at = "{now}"\nlock_reason = "initial"\n',
        encoding="utf-8",
    )
    (memory_root / "adapter.toml").write_text(
        f'[core]\nversion = "{adapter_version}"\nadapter = "default"\n',
        encoding="utf-8",
    )
    (memory_root / "CANONICAL.md").write_text("# Canonical\n", encoding="utf-8")
    (memory_root / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    (memory_root / "STATE.md").write_text("# State\n", encoding="utf-8")
    (memory_root / "TASKS.md").write_text("# Tasks\n", encoding="utf-8")
    (memory_root / "migrations.log").write_text("# Migrations Log\n", encoding="utf-8")
    return tmp_path


def _count_log_lines(log_path: Path) -> int:
    """Count non-comment, non-empty lines in migrations.log."""
    if not log_path.is_file():
        return 0
    text = log_path.read_text(encoding="utf-8")
    return sum(
        1 for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


# ---------------------------------------------------------------------------
# 1. test_migrate_noop_when_already_at_target
# ---------------------------------------------------------------------------

def test_migrate_noop_when_already_at_target(tmp_path: Path) -> None:
    """先 init 0.2.0 项目，再跑 --from 0.1.0 --to 0.2.0 应 noop / success."""
    _create_memory_skeleton(tmp_path, version=CURRENT_MEMORY_VERSION)
    log_path = tmp_path / ".memory" / "migrations.log"
    before_count = _count_log_lines(log_path)

    exit_code = _call_main([
        "--target", str(tmp_path),
        "--from", "0.1.0",
        "--to", CURRENT_MEMORY_VERSION,
    ])
    assert exit_code == 0

    # No log entry should be added for noop
    assert _count_log_lines(log_path) == before_count


# ---------------------------------------------------------------------------
# 2. test_migrate_dry_run_does_not_modify
# ---------------------------------------------------------------------------

def test_migrate_dry_run_does_not_modify(tmp_path: Path) -> None:
    """dry-run 后 .memory 内容不变."""
    _create_memory_skeleton(tmp_path, version="0.1.0", adapter_version="0.1.0")
    memory_root = tmp_path / ".memory"

    # Capture state before
    lock_before = (memory_root / "memory.lock").read_text(encoding="utf-8")
    adapter_before = (memory_root / "adapter.toml").read_text(encoding="utf-8")

    exit_code = _call_main([
        "--target", str(tmp_path),
        "--from", "0.1.0",
        "--to", CURRENT_MEMORY_VERSION,
        "--dry-run",
    ])
    assert exit_code == 0

    # Content must be unchanged
    assert (memory_root / "memory.lock").read_text(encoding="utf-8") == lock_before
    assert (memory_root / "adapter.toml").read_text(encoding="utf-8") == adapter_before


# ---------------------------------------------------------------------------
# 3. test_migrate_rejects_downgrade
# ---------------------------------------------------------------------------

def test_migrate_rejects_downgrade(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """--from 0.2.0 --to 0.1.0 退出非零或 error（无迁移路径即拒绝降级）."""
    _create_memory_skeleton(tmp_path, version=CURRENT_MEMORY_VERSION)

    # No migration path from 0.2.0 -> 0.1.0 exists
    exit_code = _call_main([
        "--target", str(tmp_path),
        "--from", CURRENT_MEMORY_VERSION,
        "--to", "0.1.0",
        "--json",
    ])
    assert exit_code != 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["success"] is False
    assert len(data.get("errors", [])) > 0


# ---------------------------------------------------------------------------
# 4. test_migrate_json_output_shape
# ---------------------------------------------------------------------------

def test_migrate_json_output_shape(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """--json 输出应包含 success/from_version/to_version/target 字段."""
    _create_memory_skeleton(tmp_path, version=CURRENT_MEMORY_VERSION)

    exit_code = _call_main([
        "--target", str(tmp_path),
        "--from", "0.1.0",
        "--to", CURRENT_MEMORY_VERSION,
        "--json",
    ])
    assert exit_code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "success" in data
    assert "from_version" in data
    assert "to_version" in data
    assert "target" in data
    assert data["success"] is True
    assert data.get("noop") is True


# ---------------------------------------------------------------------------
# 5. test_migrate_creates_backup_when_real_migration
# ---------------------------------------------------------------------------

def test_migrate_creates_backup_when_real_migration(tmp_path: Path) -> None:
    """真实迁移 (0.1.0→0.2.0) 时应创建 backup 目录."""
    _create_memory_skeleton(tmp_path, version="0.1.0", adapter_version="0.1.0")
    memory_root = tmp_path / ".memory"

    exit_code = _call_main([
        "--target", str(tmp_path),
        "--from", "0.1.0",
        "--to", CURRENT_MEMORY_VERSION,
    ])
    assert exit_code == 0

    # Backup should have been created under .memory/backups/
    backups_dir = memory_root / "backups"
    assert backups_dir.is_dir(), "backups directory should exist after real migration"
    backup_entries = list(backups_dir.iterdir())
    assert len(backup_entries) > 0, "at least one backup should exist"

    # Verify manifest
    manifest_path = backup_entries[0] / "BACKUP_MANIFEST.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["from_version"] == "0.1.0"
    assert manifest["to_version"] == CURRENT_MEMORY_VERSION


# ---------------------------------------------------------------------------
# 6. test_migrate_invalid_version_format_errors
# ---------------------------------------------------------------------------

def test_migrate_invalid_version_format_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """--from foo --to bar 应清晰报错."""
    _create_memory_skeleton(tmp_path, version=CURRENT_MEMORY_VERSION)

    exit_code = _call_main([
        "--target", str(tmp_path),
        "--from", "foo",
        "--to", "bar",
        "--json",
    ])
    assert exit_code != 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["success"] is False
    assert len(data.get("errors", [])) > 0
    # Error message should mention no migration path or version mismatch
    error_text = " ".join(data["errors"])
    assert (
        "No migration path" in error_text
        or "Version mismatch" in error_text
        or "migration" in error_text.lower()
    ), f"Expected clear error, got: {error_text}"
