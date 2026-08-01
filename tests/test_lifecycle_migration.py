"""Tests for lifecycle migration CLI (VAL-MIGRATION-01 through VAL-MIGRATION-05)."""

import hashlib
import json
from pathlib import Path

import pytest

from memory_core.tools.project_lifecycle import migrate_lifecycle_events

# ── VAL-MIGRATION-01: Migration reads old events.jsonl and emits per-project daily files


def test_migration_reads_old_events_and_emits_per_project_daily_files(tmp_path: Path) -> None:
    """VAL-MIGRATION-01: Migration ingests legacy global log and produces correctly sharded files."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    # Create fixture events.jsonl with 2 projects x 2 dates
    events_jsonl = lifecycle_root / "events.jsonl"
    events_data = [
        {"project_id": "proj-a", "observed_at": "2026-08-01T10:00:00Z", "event": "event-1"},
        {"project_id": "proj-a", "observed_at": "2026-08-02T11:00:00Z", "event": "event-2"},
        {"project_id": "proj-b", "observed_at": "2026-08-01T12:00:00Z", "event": "event-3"},
        {"project_id": "proj-b", "observed_at": "2026-08-02T13:00:00Z", "event": "event-4"},
    ]
    with events_jsonl.open("w", encoding="utf-8") as f:
        for event in events_data:
            f.write(json.dumps(event) + "\n")

    # Run migration
    migrate_lifecycle_events(lifecycle_root)

    # Verify 4 daily files created (2 projects x 2 dates)
    projects_dir = lifecycle_root / "projects"
    daily_files = list(projects_dir.glob("*/events/*.jsonl"))
    assert len(daily_files) == 4, f"Expected 4 daily files, got {len(daily_files)}"

    # Verify correct grouping
    proj_a_0801 = projects_dir / "proj-a" / "events" / "2026-08-01.jsonl"
    proj_a_0802 = projects_dir / "proj-a" / "events" / "2026-08-02.jsonl"
    proj_b_0801 = projects_dir / "proj-b" / "events" / "2026-08-01.jsonl"
    proj_b_0802 = projects_dir / "proj-b" / "events" / "2026-08-02.jsonl"

    assert proj_a_0801.exists()
    assert proj_a_0802.exists()
    assert proj_b_0801.exists()
    assert proj_b_0802.exists()

    # Verify line counts
    assert len(proj_a_0801.read_text().strip().split("\n")) == 1
    assert len(proj_a_0802.read_text().strip().split("\n")) == 1
    assert len(proj_b_0801.read_text().strip().split("\n")) == 1
    assert len(proj_b_0802.read_text().strip().split("\n")) == 1

    # Verify content matches source
    proj_a_0801_data = json.loads(proj_a_0801.read_text().strip())
    assert proj_a_0801_data["event"] == "event-1"

    proj_b_0802_data = json.loads(proj_b_0802.read_text().strip())
    assert proj_b_0802_data["event"] == "event-4"


# ── VAL-MIGRATION-02: Original file archived, not deleted


def test_migration_archives_original_file(tmp_path: Path) -> None:
    """VAL-MIGRATION-02: Legacy events.jsonl is renamed to .archived, preserving all bytes."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    # Create fixture events.jsonl
    events_jsonl = lifecycle_root / "events.jsonl"
    original_content = '{"project_id": "test", "observed_at": "2026-08-01T10:00:00Z"}\n'
    events_jsonl.write_text(original_content, encoding="utf-8")

    # Record sha256 before migration
    original_sha = hashlib.sha256(events_jsonl.read_bytes()).hexdigest()

    # Run migration
    stats = migrate_lifecycle_events(lifecycle_root)

    # Verify original is gone
    assert not events_jsonl.exists(), "events.jsonl should be removed"

    # Verify archive exists
    archive_path = lifecycle_root / "events.jsonl.archived"
    assert archive_path.exists(), "events.jsonl.archived should exist"

    # Verify byte-identical (same sha256)
    archive_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert archive_sha == original_sha, "Archive should be byte-identical to original"

    # Verify stats
    assert stats["archive_path"] == str(archive_path)


# ── VAL-MIGRATION-03: Migration is idempotent


def test_migration_is_idempotent(tmp_path: Path) -> None:
    """VAL-MIGRATION-03: Running migration twice does not duplicate data or error."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    # Create fixture events.jsonl
    events_jsonl = lifecycle_root / "events.jsonl"
    events_data = [
        {"project_id": "proj-x", "observed_at": "2026-08-01T10:00:00Z"},
        {"project_id": "proj-x", "observed_at": "2026-08-01T11:00:00Z"},
    ]
    with events_jsonl.open("w", encoding="utf-8") as f:
        for event in events_data:
            f.write(json.dumps(event) + "\n")

    # Run migration first time
    migrate_lifecycle_events(lifecycle_root)

    # Capture shasums of daily files
    daily_files = list((lifecycle_root / "projects").glob("*/events/*.jsonl"))
    shasums1 = {}
    for daily_file in daily_files:
        shasums1[daily_file.name] = hashlib.sha256(daily_file.read_bytes()).hexdigest()

    # Run migration second time (should be no-op since events.jsonl is archived)
    stats2 = migrate_lifecycle_events(lifecycle_root)

    # Verify zero stats on second run
    assert stats2["total_read"] == 0
    assert stats2["total_written"] == 0
    assert stats2["skipped"] == 0
    assert stats2["archive_path"] is None

    # Verify daily files unchanged
    daily_files2 = list((lifecycle_root / "projects").glob("*/events/*.jsonl"))
    shasums2 = {}
    for daily_file in daily_files2:
        shasums2[daily_file.name] = hashlib.sha256(daily_file.read_bytes()).hexdigest()

    assert shasums1 == shasums2, "Daily files should not change on second run"

    # Verify no duplicate lines
    for daily_file in daily_files2:
        lines = daily_file.read_text().strip().split("\n")
        assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"


# ── VAL-MIGRATION-04: Migration reports statistics


def test_migration_reports_statistics(tmp_path: Path, capsys) -> None:
    """VAL-MIGRATION-04: CLI prints human/machine-readable summary with all required stats."""

    from memory_core.tools.project_lifecycle import migrate_main

    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    # Create fixture with 3 good lines + 1 malformed
    events_jsonl = lifecycle_root / "events.jsonl"
    with events_jsonl.open("w", encoding="utf-8") as f:
        f.write('{"project_id": "proj-a", "observed_at": "2026-08-01T10:00:00Z"}\n')
        f.write('{"project_id": "proj-a", "observed_at": "2026-08-02T11:00:00Z"}\n')
        f.write('{"project_id": "proj-b", "observed_at": "2026-08-01T12:00:00Z"}\n')
        f.write("this is not valid json\n")

    # Run migration with --json flag
    with pytest.raises(SystemExit) as exc_info:
        migrate_main(["--lifecycle-root", str(lifecycle_root), "--json"])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    stats = json.loads(captured.out)

    # Verify all required fields present
    assert "total_read" in stats
    assert "total_written" in stats
    assert "per_project" in stats
    assert "skipped" in stats
    assert "archive_path" in stats

    # Verify counts reconcile
    assert stats["total_read"] == 4  # 3 good + 1 malformed
    assert stats["total_written"] == 3  # 3 good lines written
    assert stats["skipped"] == 1  # 1 malformed line
    assert stats["per_project"]["proj-a"] == 2
    assert stats["per_project"]["proj-b"] == 1

    # Verify arithmetic consistency
    total_per_project = sum(stats["per_project"].values())
    assert total_per_project + stats["skipped"] == stats["total_read"]


# ── VAL-MIGRATION-05: Migration handles malformed lines gracefully


def test_migration_handles_malformed_lines(tmp_path: Path) -> None:
    """VAL-MIGRATION-05: Non-JSON or schema-invalid lines are skipped, not fatal."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    # Create fixture with 1 good, 1 non-JSON, 1 missing project_id
    events_jsonl = lifecycle_root / "events.jsonl"
    with events_jsonl.open("w", encoding="utf-8") as f:
        f.write('{"project_id": "proj-good", "observed_at": "2026-08-01T10:00:00Z"}\n')
        f.write("this is not valid json\n")
        f.write('{"observed_at": "2026-08-01T11:00:00Z"}\n')  # missing project_id

    # Run migration
    stats = migrate_lifecycle_events(lifecycle_root)

    # Verify exit code 0 (no crash)
    assert stats["total_read"] == 3
    assert stats["total_written"] == 1  # Only the good line
    assert stats["skipped"] == 2  # 2 malformed lines

    # Verify only the valid line was migrated
    daily_file = lifecycle_root / "projects" / "proj-good" / "events" / "2026-08-01.jsonl"
    assert daily_file.exists()
    lines = daily_file.read_text().strip().split("\n")
    assert len(lines) == 1

    event_data = json.loads(lines[0])
    assert event_data["project_id"] == "proj-good"


# Additional test: empty events.jsonl
def test_migration_empty_events_jsonl(tmp_path: Path) -> None:
    """Migration handles empty events.jsonl gracefully."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    # Create empty events.jsonl
    events_jsonl = lifecycle_root / "events.jsonl"
    events_jsonl.write_text("", encoding="utf-8")

    # Run migration
    stats = migrate_lifecycle_events(lifecycle_root)

    assert stats["total_read"] == 0
    assert stats["total_written"] == 0
    assert stats["skipped"] == 0
    assert stats["archive_path"] is not None
    assert (lifecycle_root / "events.jsonl.archived").exists()


# Additional test: events.jsonl with only blank lines
def test_migration_blank_lines_only(tmp_path: Path) -> None:
    """Migration handles events.jsonl with only blank lines."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    events_jsonl = lifecycle_root / "events.jsonl"
    events_jsonl.write_text("\n\n\n", encoding="utf-8")

    stats = migrate_lifecycle_events(lifecycle_root)

    assert stats["total_read"] == 3  # 3 blank lines counted
    assert stats["total_written"] == 0
    assert stats["skipped"] == 0  # Blank lines are skipped but not counted as malformed


# Additional test: multiple events for same project and date
def test_migration_multiple_events_same_project_date(tmp_path: Path) -> None:
    """Migration correctly accumulates multiple events for same project+date."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    events_jsonl = lifecycle_root / "events.jsonl"
    with events_jsonl.open("w", encoding="utf-8") as f:
        for i in range(5):
            f.write(f'{{"project_id": "proj-x", "observed_at": "2026-08-01T1{i}:00:00Z"}}\n')

    stats = migrate_lifecycle_events(lifecycle_root)

    assert stats["total_read"] == 5
    assert stats["total_written"] == 5
    assert stats["per_project"]["proj-x"] == 5

    daily_file = lifecycle_root / "projects" / "proj-x" / "events" / "2026-08-01.jsonl"
    lines = daily_file.read_text().strip().split("\n")
    assert len(lines) == 5


# Additional test: JSON line missing observed_at
def test_migration_missing_observed_at(tmp_path: Path) -> None:
    """Migration skips lines missing observed_at field."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    events_jsonl = lifecycle_root / "events.jsonl"
    with events_jsonl.open("w", encoding="utf-8") as f:
        f.write('{"project_id": "proj-a"}\n')  # missing observed_at
        f.write('{"project_id": "proj-b", "observed_at": "2026-08-01T10:00:00Z"}\n')

    stats = migrate_lifecycle_events(lifecycle_root)

    assert stats["total_read"] == 2
    assert stats["total_written"] == 1
    assert stats["skipped"] == 1


# Additional test: CLI with no events.jsonl
def test_migration_cli_no_events(tmp_path: Path, capsys) -> None:
    """CLI handles missing events.jsonl gracefully."""
    from memory_core.tools.project_lifecycle import migrate_main

    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    # No events.jsonl created

    with pytest.raises(SystemExit) as exc_info:
        migrate_main(["--lifecycle-root", str(lifecycle_root)])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "Migration complete" in captured.out
    assert "total_read: 0" in captured.out
    assert "no migration needed" in captured.out.lower()
