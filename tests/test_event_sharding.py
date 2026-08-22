"""Tests for per-project daily event file sharding (VAL-SHARDING-01 through VAL-SHARDING-08)."""

import json
from pathlib import Path

from memory_core.tools.project_lifecycle import record_project_lifecycle
from tests.git_helpers import setup_git_repo as _setup_git_repo

# ── VAL-SHARDING-01: Single event writes to per-project daily file ─────────────────


def test_single_event_writes_to_per_project_daily_file(tmp_path: Path) -> None:
    """VAL-SHARDING-01: A single hook event produces a per-project daily event file."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()
    project = tmp_path / "project-a"
    _setup_git_repo(project)

    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    # Verify per-project daily file exists
    project_id = result["project_id"]
    daily_file = lifecycle_root / "projects" / project_id / "events" / "2026-08-01.jsonl"
    assert daily_file.exists(), f"Daily file not found: {daily_file}"

    # Verify exactly one line
    lines = daily_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1, f"Expected 1 line, got {len(lines)}"

    # Verify line is valid JSON with required fields
    event_data = json.loads(lines[0])
    assert "project_id" in event_data
    assert "event" in event_data
    assert "host" in event_data
    assert "observed_at" in event_data
    assert event_data["project_id"] == project_id
    assert event_data["observed_at"].startswith("2026-08-01")

    # Verify global events.jsonl not created or appended to
    global_events = lifecycle_root / "events.jsonl"
    assert not global_events.exists(), "Global events.jsonl should not be created"


# ── VAL-SHARDING-02: Global events.jsonl no longer appended to ─────────────────────


def test_global_events_jsonl_no_longer_appended(tmp_path: Path) -> None:
    """VAL-SHARDING-02: The deprecated global event log receives no writes after the change."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    # Pre-create global events.jsonl with known content
    global_events = lifecycle_root / "events.jsonl"
    initial_content = '{"test": "initial"}\n'
    global_events.write_text(initial_content, encoding="utf-8")
    initial_size = global_events.stat().st_size
    initial_lines = len(global_events.read_text(encoding="utf-8").strip().split("\n"))

    project = tmp_path / "project-b"
    _setup_git_repo(project)

    # Invoke multiple times
    for i in range(3):
        record_project_lifecycle(
            lifecycle_root=lifecycle_root,
            cwd=project,
            host="factory",
            event=f"event-{i}",
            payload={"cwd": str(project)},
            now_iso_fn=lambda i=i: f"2026-08-01T12:0{i}:00Z",
        )

    # Verify global events.jsonl unchanged
    assert global_events.stat().st_size == initial_size, "Global events.jsonl size changed"
    current_lines = len(global_events.read_text(encoding="utf-8").strip().split("\n"))
    assert current_lines == initial_lines, "Global events.jsonl line count changed"
    assert global_events.read_text(encoding="utf-8") == initial_content


# ── VAL-SHARDING-03: Multiple events on same day accumulate in one file ─────────────


def test_multiple_events_same_day_accumulate(tmp_path: Path) -> None:
    """VAL-SHARDING-03: Several events on the same day append to the same daily file."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()
    project = tmp_path / "project-c"
    _setup_git_repo(project)

    # Invoke 5 times on the same day
    num_events = 5
    for i in range(num_events):
        record_project_lifecycle(
            lifecycle_root=lifecycle_root,
            cwd=project,
            host="factory",
            event=f"event-{i}",
            payload={"cwd": str(project)},
            now_iso_fn=lambda: "2026-08-01T12:00:00Z",
        )

    # Verify only one daily file
    project_id = None
    for item in (lifecycle_root / "projects").iterdir():
        if item.is_file() and item.suffix == ".json":
            project_id = item.stem
            break

    events_dir = lifecycle_root / "projects" / project_id / "events"
    daily_files = list(events_dir.glob("*.jsonl"))
    assert len(daily_files) == 1, f"Expected 1 daily file, got {len(daily_files)}"

    # Verify exactly N lines
    daily_file = daily_files[0]
    lines = daily_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == num_events, f"Expected {num_events} lines, got {len(lines)}"

    # Verify all lines are valid JSON
    for line in lines:
        event_data = json.loads(line)
        assert "project_id" in event_data
        assert "observed_at" in event_data


# ── VAL-SHARDING-04: Events on different days go to different files ─────────────────


def test_events_different_days_different_files(tmp_path: Path) -> None:
    """VAL-SHARDING-04: Events on different calendar days land in distinct daily files."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()
    project = tmp_path / "project-d"
    _setup_git_repo(project)

    # Day 1
    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="day1-event",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    # Day 2
    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="day2-event",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-02T12:00:00Z",
    )

    # Verify two daily files
    project_id = None
    for item in (lifecycle_root / "projects").iterdir():
        if item.is_file() and item.suffix == ".json":
            project_id = item.stem
            break

    events_dir = lifecycle_root / "projects" / project_id / "events"
    daily_files = sorted(events_dir.glob("*.jsonl"))
    assert len(daily_files) == 2, f"Expected 2 daily files, got {len(daily_files)}"

    # Verify each file has exactly 1 line
    for daily_file in daily_files:
        lines = daily_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1, f"File {daily_file.name} has {len(lines)} lines, expected 1"

        # Verify observed_at matches filename date
        event_data = json.loads(lines[0])
        expected_date = daily_file.stem  # "2026-08-01" or "2026-08-02"
        assert event_data["observed_at"].startswith(expected_date)


# ── VAL-SHARDING-05: Per-project isolation ─────────────────────────────────────────


def test_per_project_isolation(tmp_path: Path) -> None:
    """VAL-SHARDING-05: Events from project A never appear in project B's event directory."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    _setup_git_repo(project_a)
    _setup_git_repo(project_b)

    # Record events for both projects
    result_a = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project_a,
        host="factory",
        event="event-a",
        payload={"cwd": str(project_a)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    result_b = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project_b,
        host="factory",
        event="event-b",
        payload={"cwd": str(project_b)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id_a = result_a["project_id"]
    project_id_b = result_b["project_id"]

    # Verify isolation: project A's events only in A's directory
    events_dir_a = lifecycle_root / "projects" / project_id_a / "events"
    events_dir_b = lifecycle_root / "projects" / project_id_b / "events"

    # Check A's events
    for daily_file in events_dir_a.glob("*.jsonl"):
        for line in daily_file.read_text(encoding="utf-8").strip().split("\n"):
            event_data = json.loads(line)
            assert event_data["project_id"] == project_id_a, (
                f"Project B event found in A's directory: {event_data['project_id']}"
            )

    # Check B's events
    for daily_file in events_dir_b.glob("*.jsonl"):
        for line in daily_file.read_text(encoding="utf-8").strip().split("\n"):
            event_data = json.loads(line)
            assert event_data["project_id"] == project_id_b, (
                f"Project A event found in B's directory: {event_data['project_id']}"
            )


# ── VAL-SHARDING-06: State file path unchanged ─────────────────────────────────────


def test_state_file_path_unchanged(tmp_path: Path) -> None:
    """VAL-SHARDING-06: projects/{project_id}.json state file path and overwrite semantics unchanged."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()
    project = tmp_path / "project-f"
    _setup_git_repo(project)

    # First invocation
    result1 = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="event-1",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    project_id = result1["project_id"]
    state_file = lifecycle_root / "projects" / f"{project_id}.json"

    # Verify state file exists at canonical path
    assert state_file.exists(), f"State file not found: {state_file}"

    # Verify state file is NOT inside events/ subtree
    wrong_path = lifecycle_root / "projects" / project_id / "projects" / f"{project_id}.json"
    assert not wrong_path.exists(), "State file should not be inside events/ subtree"

    # Verify state file is single-object (overwrite, not append)
    # Second invocation
    record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="event-2",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T13:00:00Z",
    )

    # State file should still be a single JSON object
    state_content = state_file.read_text(encoding="utf-8")
    state_data = json.loads(state_content)
    assert isinstance(state_data, dict), "State file should contain a single JSON object"
    assert state_data["event"] == "event-2", "State file should reflect latest event"


# ── VAL-SHARDING-07: path-index.json still updated ─────────────────────────────────


def test_path_index_still_updated(tmp_path: Path) -> None:
    """VAL-SHARDING-07: path-index.json is rewritten on each invocation and contains the project's path mapping."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()
    project = tmp_path / "project-g"
    _setup_git_repo(project)

    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    # Verify path-index.json exists
    path_index_file = lifecycle_root / "path-index.json"
    assert path_index_file.exists(), "path-index.json not found"

    # Verify it's valid JSON
    path_index_data = json.loads(path_index_file.read_text(encoding="utf-8"))
    assert isinstance(path_index_data, dict)
    assert "paths" in path_index_data

    # Verify it contains the project's path mapping
    paths = path_index_data["paths"]
    assert str(project) in paths, f"Project path not found in path-index.json: {str(project)}"
    assert paths[str(project)]["project_id"] == result["project_id"]


# ── VAL-SHARDING-08: Return dict event_log path correct ────────────────────────────


def test_return_dict_event_log_path_correct(tmp_path: Path) -> None:
    """VAL-SHARDING-08: The return dict's event_log field points to the per-project daily file."""
    lifecycle_root = tmp_path / "lifecycle"
    lifecycle_root.mkdir()
    project = tmp_path / "project-h"
    _setup_git_repo(project)

    result = record_project_lifecycle(
        lifecycle_root=lifecycle_root,
        cwd=project,
        host="factory",
        event="session-start",
        payload={"cwd": str(project)},
        now_iso_fn=lambda: "2026-08-01T12:00:00Z",
    )

    # Verify event_log field exists
    assert "event_log" in result, "event_log field missing from return dict"

    event_log_path = Path(result["event_log"])

    # Verify path exists
    assert event_log_path.exists(), f"event_log path does not exist: {event_log_path}"

    # Verify path matches pattern: projects/{project_id}/events/{YYYY-MM-DD}.jsonl
    project_id = result["project_id"]
    expected_pattern = f"projects/{project_id}/events/2026-08-01.jsonl"
    assert str(event_log_path).endswith(expected_pattern), (
        f"event_log path does not match expected pattern: {event_log_path}"
    )

    # Verify it's NOT pointing to global events.jsonl
    assert not str(event_log_path).endswith("events.jsonl") or "projects" in str(event_log_path), (
        "event_log should not point to global events.jsonl"
    )
