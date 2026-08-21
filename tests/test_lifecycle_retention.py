"""Tests for event file retention cleanup (VAL-RETENTION-01 through VAL-RETENTION-05)."""

from pathlib import Path

from memory_core.tools.project_lifecycle import record_project_lifecycle
from tests.git_helpers import setup_git_repo as _setup_git_repo


def _get_project_id(lifecycle_root: Path) -> str:
    """Extract project_id from lifecycle root."""
    projects_dir = lifecycle_root / "projects"
    for item in projects_dir.iterdir():
        if item.is_file() and item.suffix == ".json":
            return item.stem
    raise ValueError("No project found")


# ── VAL-RETENTION-01: Old files are deleted ──────────────────────────────────────


def test_old_event_files_are_deleted(tmp_path: Path, monkeypatch) -> None:
    """VAL-RETENTION-01: Event files older than retention period are deleted."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    project = tmp_path / "project"
    _setup_git_repo(project)

    # Set retention to 7 days via environment variable
    monkeypatch.setenv("MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS", "7")

    # First, trigger a lifecycle event to create the project structure
    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id = result["project_id"]
    events_dir = lifecycle_root / "projects" / project_id / "events"

    # Create old event files (10 days ago)
    old_date = "2026-07-22"
    old_file = events_dir / f"{old_date}.jsonl"
    old_file.write_text('{"test": "old"}\n', encoding="utf-8")

    # Delete the sentinel to force cleanup
    sentinel = lifecycle_root / "projects" / project_id / ".last-cleanup"
    if sentinel.exists():
        sentinel.unlink()

    # Trigger another event to invoke cleanup
    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T13:00:00Z",
    )

    # Old file should be deleted
    assert not old_file.exists(), f"Old file {old_date}.jsonl should have been deleted"

    # Today's file should still exist
    today_file = events_dir / "2026-08-01.jsonl"
    assert today_file.exists(), "Today's event file should still exist"


# ── VAL-RETENTION-02: New files are preserved ─────────────────────────────────────


def test_recent_event_files_are_preserved(tmp_path: Path, monkeypatch) -> None:
    """VAL-RETENTION-02: Event files within retention period are preserved."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    project = tmp_path / "project"
    _setup_git_repo(project)

    # Set retention to 30 days
    monkeypatch.setenv("MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS", "30")

    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id = result["project_id"]
    events_dir = lifecycle_root / "projects" / project_id / "events"

    # Create recent event files (within 30 days)
    recent_files = [
        "2026-07-15.jsonl",  # 17 days ago
        "2026-07-25.jsonl",  # 7 days ago
        "2026-07-31.jsonl",  # 1 day ago
    ]
    for date_str in recent_files:
        file = events_dir / date_str
        file.write_text(f'{{"date": "{date_str}"}}\n', encoding="utf-8")

    # Delete sentinel to force cleanup
    sentinel = lifecycle_root / "projects" / project_id / ".last-cleanup"
    if sentinel.exists():
        sentinel.unlink()

    # Trigger cleanup
    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T13:00:00Z",
    )

    # All recent files should still exist
    for date_str in recent_files:
        file = events_dir / date_str
        assert file.exists(), f"Recent file {date_str}.jsonl should be preserved"


# ── VAL-RETENTION-03: Cleanup throttled via sentinel ──────────────────────────────


def test_cleanup_throttled_via_sentinel(tmp_path: Path, monkeypatch) -> None:
    """VAL-RETENTION-03: Cleanup runs at most once per day via .last-cleanup sentinel."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    project = tmp_path / "project"
    _setup_git_repo(project)

    monkeypatch.setenv("MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS", "7")

    # First event triggers cleanup
    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id = result["project_id"]
    sentinel = lifecycle_root / "projects" / project_id / ".last-cleanup"

    # Sentinel should exist with today's date
    assert sentinel.exists(), "Sentinel file should be created"
    sentinel_content = sentinel.read_text(encoding="utf-8").strip()
    assert sentinel_content == "2026-08-01", f"Sentinel should contain today's date, got {sentinel_content}"

    # Record sentinel mtime
    sentinel_mtime_1 = sentinel.stat().st_mtime

    # Second event on the same day should NOT update sentinel
    import time
    time.sleep(0.1)  # Small delay to ensure mtime would change if written

    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T13:00:00Z",
    )

    sentinel_mtime_2 = sentinel.stat().st_mtime
    assert sentinel_mtime_1 == sentinel_mtime_2, "Sentinel mtime should not change on same-day invocations"

    # Content should still be the same
    sentinel_content_2 = sentinel.read_text(encoding="utf-8").strip()
    assert sentinel_content_2 == "2026-08-01", "Sentinel content should remain unchanged"


# ── VAL-RETENTION-04: Env var overrides default ───────────────────────────────────


def test_retention_days_env_var_override(tmp_path: Path, monkeypatch) -> None:
    """VAL-RETENTION-04: MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS env var controls retention window."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    project = tmp_path / "project"
    _setup_git_repo(project)

    # Set custom retention to 7 days
    monkeypatch.setenv("MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS", "7")

    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id = result["project_id"]
    events_dir = lifecycle_root / "projects" / project_id / "events"

    # Create files at different ages
    files_to_create = [
        ("2026-07-20.jsonl", 12, False),  # 12 days ago, should be deleted
        ("2026-07-25.jsonl", 7, True),    # 7 days ago, should be preserved (boundary)
        ("2026-07-30.jsonl", 2, True),    # 2 days ago, should be preserved
    ]

    for date_str, age_days, _should_preserve in files_to_create:
        file = events_dir / date_str
        file.write_text(f'{{"date": "{date_str}", "age": {age_days}}}\n', encoding="utf-8")

    # Delete sentinel to force cleanup
    sentinel = lifecycle_root / "projects" / project_id / ".last-cleanup"
    if sentinel.exists():
        sentinel.unlink()

    # Trigger cleanup
    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T13:00:00Z",
    )

    # Verify files were deleted/preserved correctly
    for date_str, age_days, should_preserve in files_to_create:
        file = events_dir / date_str
        if should_preserve:
            assert file.exists(), f"File {date_str} ({age_days} days old) should be preserved"
        else:
            assert not file.exists(), f"File {date_str} ({age_days} days old) should be deleted"


def test_default_retention_is_30_days(tmp_path: Path, monkeypatch) -> None:
    """Verify default retention is 30 days when env var is not set."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    project = tmp_path / "project"
    _setup_git_repo(project)

    # Ensure env var is NOT set
    monkeypatch.delenv("MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS", raising=False)

    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id = result["project_id"]
    events_dir = lifecycle_root / "projects" / project_id / "events"

    # Create files at boundary of default 30-day retention
    files_to_create = [
        ("2026-07-01.jsonl", 31, False),  # 31 days ago, should be deleted
        ("2026-07-02.jsonl", 30, True),   # 30 days ago, should be preserved (boundary)
        ("2026-07-15.jsonl", 17, True),   # 17 days ago, should be preserved
    ]

    for date_str, _age_days, _should_preserve in files_to_create:
        file = events_dir / date_str
        file.write_text(f'{{"date": "{date_str}"}}\n', encoding="utf-8")

    # Delete sentinel to force cleanup
    sentinel = lifecycle_root / "projects" / project_id / ".last-cleanup"
    if sentinel.exists():
        sentinel.unlink()

    # Trigger cleanup
    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T13:00:00Z",
    )

    # Verify files
    for date_str, age_days, should_preserve in files_to_create:
        file = events_dir / date_str
        if should_preserve:
            assert file.exists(), f"File {date_str} ({age_days} days old) should be preserved"
        else:
            assert not file.exists(), f"File {date_str} ({age_days} days old) should be deleted"


# ── VAL-RETENTION-05: Retention=0 disables cleanup ───────────────────────────────


def test_retention_zero_disables_cleanup(tmp_path: Path, monkeypatch) -> None:
    """VAL-RETENTION-05: MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS=0 disables cleanup entirely."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    project = tmp_path / "project"
    _setup_git_repo(project)

    # Disable retention entirely
    monkeypatch.setenv("MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS", "0")

    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id = result["project_id"]
    events_dir = lifecycle_root / "projects" / project_id / "events"

    # Create a very old file (365 days ago)
    old_file = events_dir / "2025-08-01.jsonl"
    old_file.write_text('{"date": "2025-08-01"}\n', encoding="utf-8")

    # Trigger another event
    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T13:00:00Z",
    )

    # Old file should still exist (cleanup disabled)
    assert old_file.exists(), "Old file should be preserved when retention=0"

    # Sentinel should NOT be created (cleanup skipped entirely)
    sentinel = lifecycle_root / "projects" / project_id / ".last-cleanup"
    assert not sentinel.exists(), "Sentinel should not be created when retention=0"


def test_cleanup_failures_do_not_block_hook(tmp_path: Path, monkeypatch) -> None:
    """Verify that cleanup exceptions don't prevent hook from completing."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    project = tmp_path / "project"
    _setup_git_repo(project)

    monkeypatch.setenv("MEMORY_HOOK_LIFECYCLE_RETENTION_DAYS", "7")

    # Create events directory with a malformed filename that would cause parsing error
    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id = result["project_id"]
    events_dir = lifecycle_root / "projects" / project_id / "events"

    # Add a file with invalid date format
    malformed_file = events_dir / "not-a-date.jsonl"
    malformed_file.write_text('{"test": "data"}\n', encoding="utf-8")

    # Delete sentinel to force cleanup
    sentinel = lifecycle_root / "projects" / project_id / ".last-cleanup"
    if sentinel.exists():
        sentinel.unlink()

    # Hook should complete successfully despite malformed file
    result2 = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T14:00:00Z",
    )

    # Verify hook completed successfully
    assert "project_id" in result2
    assert "event_log" in result2
    assert result2["event"] == "session-start"

    # Malformed file should still exist (cleanup skipped it gracefully)
    assert malformed_file.exists(), "Malformed file should be skipped, not deleted"
