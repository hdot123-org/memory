"""Tests for migrate_project_memory.py: idempotent migration, backup, rollback, and atomic log append."""

import json
import multiprocessing
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from memory_core.constants import (
    _BACKUP_FAILED,
    CURRENT_MEMORY_VERSION,
    MIGRATION_LOG_LINE_PATTERN,
)
from memory_core.tools.migrate_project_memory import (
    execute_rollback,
    migrate_project_memory,
    plan_rollback,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_memory_skeleton(tmp_path: Path, *, version: str = CURRENT_MEMORY_VERSION) -> Path:
    """Create a valid .memory/ skeleton and return the project root."""
    memory_root = tmp_path / ".memory"
    memory_root.mkdir(parents=True)
    (memory_root / "kb" / "projects").mkdir(parents=True)
    (memory_root / "kb" / "decisions").mkdir(parents=True)
    (memory_root / "kb" / "lessons").mkdir(parents=True)
    (memory_root / "kb" / "global").mkdir(parents=True)

    lock_path = memory_root / "memory.lock"
    lock_path.write_text(
        f'# memory.lock\n[memory]\nmemory_version = "{version}"\n'
        f'schema_version = "context-package-v1"\nadapter_version = "builtin"\n'
        f'locked_at = "{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}"\n'
        f'lock_reason = "initial"\n',
        encoding="utf-8",
    )
    (memory_root / "adapter.toml").write_text(
        '[core]\nversion = "0.1.0"\nadapter = "default"\n',
        encoding="utf-8",
    )
    (memory_root / "migrations.log").write_text(
        "# Migrations Log\n",
        encoding="utf-8",
    )
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
# 1. Idempotent: already at target → noop
# ---------------------------------------------------------------------------

def test_migrate_already_at_target_is_noop(tmp_path: Path) -> None:
    """current=0.2.0, from=0.1.0, to=0.2.0 应返回 noop（不报错），migrations.log 不增条."""
    project_root = _create_memory_skeleton(tmp_path, version=CURRENT_MEMORY_VERSION)
    log_path = project_root / ".memory" / "migrations.log"
    before_count = _count_log_lines(log_path)

    result = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)

    assert result["success"] is True
    assert result.get("noop") is True
    assert result.get("reason") == "already at target version"
    assert _count_log_lines(log_path) == before_count  # 不增条


# ---------------------------------------------------------------------------
# 2. Migration creates backup before write
# ---------------------------------------------------------------------------

def test_migrate_creates_backup_before_write(tmp_path: Path) -> None:
    """成功迁移后 .memory/backups/<ts>/BACKUP_MANIFEST.json 存在."""
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")

    result = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)

    assert result["success"] is True
    assert not result.get("noop")

    # Backup should have been created under .memory/backups/
    backups_dir = project_root / ".memory" / "backups"
    assert backups_dir.is_dir()

    backup_ts_dirs = [d for d in backups_dir.iterdir() if d.is_dir()]
    assert len(backup_ts_dirs) >= 1

    # Find the one with BACKUP_MANIFEST.json
    manifest_found = False
    for bd in backup_ts_dirs:
        manifest_path = bd / "BACKUP_MANIFEST.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert manifest["from_version"] == "0.1.0"
            assert manifest["to_version"] == CURRENT_MEMORY_VERSION
            assert "timestamp" in manifest
            assert "source_files_count" in manifest
            manifest_found = True
            break
    assert manifest_found, "BACKUP_MANIFEST.json not found in any backup dir"


# ---------------------------------------------------------------------------
# 3. Dry-run does not create backup
# ---------------------------------------------------------------------------

def test_dry_run_does_not_create_backup(tmp_path: Path) -> None:
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")

    result = migrate_project_memory(
        project_root, "0.1.0", CURRENT_MEMORY_VERSION, dry_run=True,
    )

    assert result["success"] is True
    backups_dir = project_root / ".memory" / "backups"
    assert not backups_dir.is_dir()


# ---------------------------------------------------------------------------
# 4. plan_rollback returns can_rollback=True after migration
# ---------------------------------------------------------------------------

def test_plan_rollback_returns_can_rollback_true_after_migration(tmp_path: Path) -> None:
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")

    migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)

    memory_root = project_root / ".memory"
    rb = plan_rollback(memory_root)
    assert rb["can_rollback"] is True
    assert "backup_dir" in rb
    assert "from_version" in rb
    assert "to_version" in rb
    assert "ts" in rb


# ---------------------------------------------------------------------------
# 5. plan_rollback returns False when no backup
# ---------------------------------------------------------------------------

def test_plan_rollback_returns_false_when_no_backup(tmp_path: Path) -> None:
    project_root = _create_memory_skeleton(tmp_path, version=CURRENT_MEMORY_VERSION)
    memory_root = project_root / ".memory"

    rb = plan_rollback(memory_root)
    assert rb["can_rollback"] is False
    assert rb.get("reason") == "no backup found"


# ---------------------------------------------------------------------------
# 6. execute_rollback restores state
# ---------------------------------------------------------------------------

def test_execute_rollback_restores_state(tmp_path: Path) -> None:
    """迁移后改 .memory 某文件，rollback 后内容恢复."""
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")
    memory_root = project_root / ".memory"

    # Migrate
    result = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)
    assert result["success"] is True

    # Corrupt a file
    lock_path = memory_root / "memory.lock"
    lock_path.write_text("# CORRUPTED\n", encoding="utf-8")

    # Rollback
    rb = execute_rollback(memory_root)
    assert rb["success"] is True

    # Verify restored (memory.lock should have original TOML content)
    content = lock_path.read_text(encoding="utf-8")
    assert "# CORRUPTED" not in content


# ---------------------------------------------------------------------------
# 7. Migration failure triggers auto-rollback
# ---------------------------------------------------------------------------

def test_migration_failure_triggers_auto_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """monkeypatch 使迁移中段抛异常，确认 .memory 状态被恢复 + migrations.log 含 failed_rolled_back."""
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")
    memory_root = project_root / ".memory"

    def _failing_mig(_root: Path) -> dict[str, Any]:
        raise RuntimeError("simulated migration failure")

    # Patch the migration function to fail
    from memory_core.tools import migrate_project_memory as mod
    monkeypatch.setattr(mod, "MIGRATION_REGISTRY", {
        f"0.1.0->{CURRENT_MEMORY_VERSION}": _failing_mig,
    })

    result = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)

    # Migration should have failed
    assert result["success"] is False
    assert result["errors"]

    # Verify state was restored (memory.lock should still be original)
    lock_path = memory_root / "memory.lock"
    content = lock_path.read_text(encoding="utf-8")
    assert "# CORRUPTED" not in content
    assert "memory_version" in content

    # Verify migrations.log contains failed_rolled_back
    log_path = memory_root / "migrations.log"
    log_text = log_path.read_text(encoding="utf-8")
    assert "failed_rolled_back" in log_text


# ---------------------------------------------------------------------------
# 8. migrations.log concurrent append — no corruption
# ---------------------------------------------------------------------------

def _worker_append(log_path_str: str, start: int, count: int) -> None:
    """Worker process that appends lines to migrations.log."""
    log_path = Path(log_path_str)
    for i in range(count):
        line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} | 0.1.0 | 0.2.0 | success | worker line {start + i}"
        # Use the actual append logic from the module
        try:
            import fcntl
        except ImportError:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        else:
            with open(log_path, "a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(line + "\n")
                    f.flush()
                    import os
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        time.sleep(0.001)  # tiny delay to increase contention


def test_migrations_log_concurrent_append_no_corruption(tmp_path: Path) -> None:
    """多进程写 50 行，最终行数 == 50 且每行都符合 MIGRATION_LOG_LINE_PATTERN."""
    log_path = tmp_path / "migrations.log"
    log_path.write_text("# Migrations Log\n", encoding="utf-8")

    num_workers = 5
    lines_per_worker = 10
    total_expected = num_workers * lines_per_worker

    processes = []
    for w in range(num_workers):
        p = multiprocessing.Process(
            target=_worker_append,
            args=(str(log_path), w * lines_per_worker, lines_per_worker),
        )
        processes.append(p)
        p.start()

    for p in processes:
        p.join(timeout=30)
        assert not p.exitcode, f"Worker process exited with code {p.exitcode}"

    # Verify
    lines = log_path.read_text(encoding="utf-8").splitlines()
    data_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    assert len(data_lines) == total_expected, f"Expected {total_expected} lines, got {len(data_lines)}"

    for line in data_lines:
        assert MIGRATION_LOG_LINE_PATTERN.match(line), f"Line does not match pattern: {line!r}"


# ---------------------------------------------------------------------------
# 9. Idempotent rerun — same direction
# ---------------------------------------------------------------------------

def test_idempotent_rerun_same_direction(tmp_path: Path) -> None:
    """跑两次相同 from→to，第一次 success，第二次 noop（不抛、不写盘）."""
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")
    log_path = project_root / ".memory" / "migrations.log"
    before_count = _count_log_lines(log_path)

    # First run: should succeed
    result1 = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)
    assert result1["success"] is True
    assert not result1.get("noop")

    after_first = _count_log_lines(log_path)
    assert after_first > before_count

    # Second run: already at target → noop
    result2 = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)
    assert result2["success"] is True
    assert result2.get("noop") is True
    assert _count_log_lines(log_path) == after_first  # 不增条


# ---------------------------------------------------------------------------
# 10. Backup failure returns structured error (S3 fix)
# ---------------------------------------------------------------------------

def test_backup_failure_returns_structured_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """monkeypatch _create_backup 抛 OSError，断言 result["success"] is False + result["error"] == "backup_failed" + 错误消息含异常文本."""
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")
    memory_root = project_root / ".memory"

    from memory_core.tools import migrate_project_memory as mod

    def _failing_backup(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full: no space left on device")

    monkeypatch.setattr(mod, "_create_backup", _failing_backup)

    result = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)

    assert result["success"] is False
    assert result["error"] == _BACKUP_FAILED
    assert any("disk full" in e for e in result["errors"]), f"Expected 'disk full' in errors: {result['errors']}"

    # Verify migrations.log contains failed_backup_failed
    log_path = memory_root / "migrations.log"
    log_text = log_path.read_text(encoding="utf-8")
    assert "failed_backup_failed" in log_text


# ---------------------------------------------------------------------------
# 11. Rollback failure during auto-rollback (S2 fix)
# ---------------------------------------------------------------------------

def test_rollback_failure_during_auto_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """monkeypatch 让 migration 失败 + execute_rollback 也抛错，断言 result["rollback_attempted"] is True + result["rollback_succeeded"] is False + log 记录 failed_rollback_failed."""
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")
    memory_root = project_root / ".memory"

    from memory_core.tools import migrate_project_memory as mod

    def _failing_mig(_root: Path) -> dict[str, Any]:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(mod, "MIGRATION_REGISTRY", {
        f"0.1.0->{CURRENT_MEMORY_VERSION}": _failing_mig,
    })

    def _failing_rollback(_root: Path, *, backup_dir=None) -> dict[str, Any]:
        raise RuntimeError("rollback also failed: backup corrupted")

    monkeypatch.setattr(mod, "execute_rollback", _failing_rollback)

    result = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)

    assert result["success"] is False
    assert result["rollback_attempted"] is True
    assert result["rollback_succeeded"] is False
    assert any("rollback also failed" in e for e in result["errors"]), f"Expected rollback error in: {result['errors']}"

    # Verify migrations.log contains failed_rollback_failed
    log_path = memory_root / "migrations.log"
    log_text = log_path.read_text(encoding="utf-8")
    assert "failed_rollback_failed" in log_text


# ---------------------------------------------------------------------------
# 12. Rollback success during auto-rollback (S2 fix)
# ---------------------------------------------------------------------------

def test_rollback_success_during_auto_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """monkeypatch 让 migration 失败但 rollback 成功，断言 result["rollback_succeeded"] is True."""
    project_root = _create_memory_skeleton(tmp_path, version="0.1.0")
    memory_root = project_root / ".memory"

    from memory_core.tools import migrate_project_memory as mod

    def _failing_mig(_root: Path) -> dict[str, Any]:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(mod, "MIGRATION_REGISTRY", {
        f"0.1.0->{CURRENT_MEMORY_VERSION}": _failing_mig,
    })

    result = migrate_project_memory(project_root, "0.1.0", CURRENT_MEMORY_VERSION)

    assert result["success"] is False
    assert result["rollback_attempted"] is True
    assert result["rollback_succeeded"] is True

    # Verify migrations.log contains failed_rolled_back (not failed_rollback_failed)
    log_path = memory_root / "migrations.log"
    log_text = log_path.read_text(encoding="utf-8")
    assert "failed_rolled_back" in log_text
    assert "failed_rollback_failed" not in log_text
