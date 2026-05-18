from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_core.tools.daily_session_summary import (
    SessionStats,
    _filter_by_date,
    _filter_by_project,
    _find_context_snapshots,
    _find_event_log,
    _json_report,
    _load_errors,
    _load_events,
    _print_report,
    main,
)


class TestSessionStats:
    """Tests for SessionStats class."""

    def test_init_default_values(self) -> None:
        """Test that SessionStats initializes with empty values."""
        stats = SessionStats()
        assert stats.sessions == []
        assert stats.prompts == []
        assert stats.stops == []
        assert stats.projects == {}
        assert stats.status_ok == 0
        assert stats.status_degraded == 0
        assert stats.errors == []
        assert stats.timeline == []

    def test_add_event_session_start(self) -> None:
        """Test adding session-start event."""
        stats = SessionStats()
        event = {
            "event": "session-start",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": "/home/project",
        }
        stats.add_event(event)

        assert len(stats.sessions) == 1
        assert stats.status_ok == 1
        assert "/home/project" in stats.projects
        assert len(stats.timeline) == 1

    def test_add_event_prompt_submit(self) -> None:
        """Test adding prompt-submit event."""
        stats = SessionStats()
        event = {
            "event": "prompt-submit",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": "/home/project",
        }
        stats.add_event(event)

        assert len(stats.prompts) == 1
        assert stats.status_ok == 1

    def test_add_event_stop(self) -> None:
        """Test adding stop event."""
        stats = SessionStats()
        event = {
            "event": "stop",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": "/home/project",
        }
        stats.add_event(event)

        assert len(stats.stops) == 1
        assert stats.status_ok == 1

    def test_add_event_degraded_status(self) -> None:
        """Test adding event with degraded status."""
        stats = SessionStats()
        event = {
            "event": "session-start",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "degraded",
            "cwd": "/home/project",
        }
        stats.add_event(event)

        assert stats.status_degraded == 1
        assert stats.status_ok == 0

    def test_add_event_with_validation_errors(self) -> None:
        """Test adding event with validation errors."""
        stats = SessionStats()
        event = {
            "event": "session-start",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": "/home/project",
            "validation_errors": ["error1", "error2"],
        }
        stats.add_event(event)

        assert len(stats.errors) == 1
        assert stats.errors[0]["errors"] == ["error1", "error2"]

    def test_add_event_multiple_projects(self) -> None:
        """Test adding events from multiple projects."""
        stats = SessionStats()
        stats.add_event({
            "event": "session-start",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": "/home/project1",
        })
        stats.add_event({
            "event": "session-start",
            "generated_at": "2026-01-15T10:01:00Z",
            "status": "ok",
            "cwd": "/home/project2",
        })
        stats.add_event({
            "event": "session-start",
            "generated_at": "2026-01-15T10:02:00Z",
            "status": "ok",
            "cwd": "/home/project1",
        })

        assert stats.projects["/home/project1"] == 2
        assert stats.projects["/home/project2"] == 1

    def test_add_event_timeline_ordering(self) -> None:
        """Test that timeline entries are added in order."""
        stats = SessionStats()
        stats.add_event({
            "event": "session-start",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": "/home/project",
        })
        stats.add_event({
            "event": "prompt-submit",
            "generated_at": "2026-01-15T10:01:00Z",
            "status": "ok",
            "cwd": "/home/project",
        })

        assert len(stats.timeline) == 2
        assert stats.timeline[0]["event"] == "session-start"
        assert stats.timeline[1]["event"] == "prompt-submit"

    def test_add_event_uses_artifact_refs_snapshot(self) -> None:
        """Test that add_event uses artifact_refs.snapshot when generated_at missing."""
        stats = SessionStats()
        event = {
            "event": "session-start",
            "status": "ok",
            "cwd": "/home/project",
            "artifact_refs": {"snapshot": "2026-01-15T10:00:00Z"},
        }
        stats.add_event(event)

        assert len(stats.sessions) == 1
        assert stats.timeline[0]["time"] == "2026-01-15T10:00:00"

    def test_add_event_unknown_event_type(self) -> None:
        """Test handling unknown event type."""
        stats = SessionStats()
        event = {
            "event": "unknown-event",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": "/home/project",
        }
        stats.add_event(event)

        # Should still add to timeline and projects
        assert len(stats.timeline) == 1
        assert "/home/project" in stats.projects


class TestFindEventLog:
    """Tests for _find_event_log function."""

    def test_find_partitioned_log(self, tmp_path: Path) -> None:
        """Test finding date-partitioned event log."""
        events_dir = tmp_path / "artifacts" / "memory-hook" / "events"
        events_dir.mkdir(parents=True)
        log_file = events_dir / "2026-01-15.jsonl"
        log_file.write_text("{}")

        result = _find_event_log(tmp_path, "2026-01-15")
        assert result == log_file

    def test_find_legacy_log(self, tmp_path: Path) -> None:
        """Test finding legacy combined event log."""
        events_dir = tmp_path / "artifacts" / "memory-hook"
        events_dir.mkdir(parents=True)
        log_file = events_dir / "events.jsonl"
        log_file.write_text("{}")

        result = _find_event_log(tmp_path, "2026-01-15")
        assert result == log_file

    def test_find_no_log(self, tmp_path: Path) -> None:
        """Test when no event log exists."""
        result = _find_event_log(tmp_path, "2026-01-15")
        assert result is None


class TestFindContextSnapshots:
    """Tests for _find_context_snapshots function."""

    def test_find_snapshots(self, tmp_path: Path) -> None:
        """Test finding context snapshots."""
        contexts_dir = tmp_path / "artifacts" / "memory-hook" / "contexts" / "2026-01-15"
        contexts_dir.mkdir(parents=True)
        (contexts_dir / "snapshot1.json").write_text("{}")
        (contexts_dir / "snapshot2.json").write_text("{}")

        result = _find_context_snapshots(tmp_path, "2026-01-15")
        assert len(result) == 2

    def test_find_no_snapshots_dir(self, tmp_path: Path) -> None:
        """Test when contexts directory doesn't exist."""
        result = _find_context_snapshots(tmp_path, "2026-01-15")
        assert result == []

    def test_find_empty_snapshots_dir(self, tmp_path: Path) -> None:
        """Test when contexts directory exists but is empty."""
        contexts_dir = tmp_path / "artifacts" / "memory-hook" / "contexts" / "2026-01-15"
        contexts_dir.mkdir(parents=True)

        result = _find_context_snapshots(tmp_path, "2026-01-15")
        assert result == []


class TestLoadEvents:
    """Tests for _load_events function."""

    def test_load_valid_events(self, tmp_path: Path) -> None:
        """Test loading valid JSON events."""
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(
            json.dumps({"event": "test1"}) + "\n" +
            json.dumps({"event": "test2"}) + "\n"
        )

        result = _load_events(log_file)
        assert len(result) == 2
        assert result[0]["event"] == "test1"
        assert result[1]["event"] == "test2"

    def test_load_ignores_empty_lines(self, tmp_path: Path) -> None:
        """Test that empty lines are ignored."""
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(
            json.dumps({"event": "test1"}) + "\n\n\n" +
            json.dumps({"event": "test2"}) + "\n"
        )

        result = _load_events(log_file)
        assert len(result) == 2

    def test_load_ignores_invalid_json(self, tmp_path: Path) -> None:
        """Test that invalid JSON lines are skipped."""
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(
            "not json\n" +
            json.dumps({"event": "test1"}) + "\n" +
            "also not json\n"
        )

        result = _load_events(log_file)
        assert len(result) == 1
        assert result[0]["event"] == "test1"


class TestFilterByDate:
    """Tests for _filter_by_date function."""

    def test_filter_by_generated_at(self) -> None:
        """Test filtering by generated_at timestamp."""
        events = [
            {"generated_at": "2026-01-15T10:00:00Z", "event": "test1"},
            {"generated_at": "2026-01-16T10:00:00Z", "event": "test2"},
            {"generated_at": "2026-01-15T11:00:00Z", "event": "test3"},
        ]

        result = _filter_by_date(events, "2026-01-15")
        assert len(result) == 2
        assert result[0]["event"] == "test1"
        assert result[1]["event"] == "test3"

    def test_filter_by_artifact_refs(self) -> None:
        """Test filtering by artifact_refs.snapshot."""
        events = [
            {"artifact_refs": {"snapshot": "2026-01-15/snapshot1.json"}, "event": "test1"},
            {"artifact_refs": {"snapshot": "2026-01-16/snapshot1.json"}, "event": "test2"},
        ]

        result = _filter_by_date(events, "2026-01-15")
        assert len(result) == 1
        assert result[0]["event"] == "test1"

    def test_filter_no_matches(self) -> None:
        """Test when no events match the date."""
        events = [
            {"generated_at": "2026-01-16T10:00:00Z", "event": "test1"},
        ]

        result = _filter_by_date(events, "2026-01-15")
        assert result == []


class TestFilterByProject:
    """Tests for _filter_by_project function."""

    def test_filter_by_cwd(self) -> None:
        """Test filtering by cwd."""
        events = [
            {"cwd": "/home/project1", "event": "test1"},
            {"cwd": "/home/project2", "event": "test2"},
            {"cwd": "/home/project1", "event": "test3"},
        ]

        result = _filter_by_project(events, "/home/project1")
        assert len(result) == 2

    def test_filter_by_repo_root(self) -> None:
        """Test filtering by repo_root."""
        events = [
            {"repo_root": "/home/project1", "event": "test1"},
            {"repo_root": "/home/project2", "event": "test2"},
        ]

        result = _filter_by_project(events, "/home/project1")
        assert len(result) == 1

    def test_filter_no_project_path(self) -> None:
        """Test when no project path is provided."""
        events = [
            {"cwd": "/home/project1", "event": "test1"},
        ]

        result = _filter_by_project(events, "")
        assert len(result) == 1

    def test_filter_no_matches(self) -> None:
        """Test when no events match the project."""
        events = [
            {"cwd": "/home/project2", "event": "test1"},
        ]

        result = _filter_by_project(events, "/home/project1")
        assert result == []


class TestLoadErrors:
    """Tests for _load_errors function."""

    def test_load_daily_error_log(self, tmp_path: Path) -> None:
        """Test loading daily error log."""
        errors_dir = tmp_path / "memory" / "system" / "errors"
        errors_dir.mkdir(parents=True)
        error_file = errors_dir / "2026-01-15.log"
        # Include the date in the lines so they are matched
        error_file.write_text("2026-01-15 Error 1\n2026-01-15 Error 2\n")

        result = _load_errors(tmp_path, "2026-01-15")
        assert len(result) == 2
        assert "2026-01-15 Error 1" in result[0]
        assert "2026-01-15 Error 2" in result[1]

    def test_load_from_combined_log(self, tmp_path: Path) -> None:
        """Test loading from combined errors.log."""
        errors_dir = tmp_path / "memory" / "system"
        errors_dir.mkdir(parents=True)
        error_file = errors_dir / "errors.log"
        error_file.write_text("2026-01-15 Error 1\n2026-01-16 Error 2\n2026-01-15 Error 3\n")

        result = _load_errors(tmp_path, "2026-01-15")
        assert len(result) == 2
        assert "2026-01-15 Error 1" in result[0]
        assert "2026-01-15 Error 3" in result[1]

    def test_load_no_error_log(self, tmp_path: Path) -> None:
        """Test when no error log exists."""
        result = _load_errors(tmp_path, "2026-01-15")
        assert result == []


class TestPrintReport:
    """Tests for _print_report function."""

    def test_print_report(self, capsys: pytest.CaptureFixture) -> None:
        """Test printing report."""
        stats = SessionStats()
        stats.sessions = ["2026-01-15T10:00:00Z"]
        stats.prompts = ["2026-01-15T10:01:00Z"]
        stats.stops = ["2026-01-15T10:02:00Z"]
        stats.status_ok = 2
        stats.status_degraded = 1
        stats.projects = {"/home/project1": 2, "/home/project2": 1}

        _print_report(stats, "2026-01-15", ["error line"])

        captured = capsys.readouterr()
        output = captured.out
        assert "Daily Session Summary" in output
        assert "2026-01-15" in output
        assert "Sessions started:   1" in output
        assert "Prompts submitted:  1" in output
        assert "Sessions stopped:   1" in output
        assert "OK:" in output
        assert "Degraded:" in output
        assert "project1" in output

    def test_print_report_with_validation_errors(self, capsys: pytest.CaptureFixture) -> None:
        """Test printing report with validation errors."""
        stats = SessionStats()
        stats.errors = [{
            "time": "2026-01-15T10:00:00",
            "event": "test",
            "project": "/home/project1",
            "errors": ["error1", "error2"],
        }]

        _print_report(stats, "2026-01-15", ["system error"])

        captured = capsys.readouterr()
        output = captured.out
        assert "Validation Errors" in output
        assert "error1" in output
        assert "System Errors" in output

    def test_print_report_with_timeline(self, capsys: pytest.CaptureFixture) -> None:
        """Test printing report with timeline."""
        stats = SessionStats()
        stats.timeline = [
            {"time": "10:00:00", "event": "session-start", "status": "ok", "project": "/home/proj"},
        ]

        _print_report(stats, "2026-01-15", [])

        captured = capsys.readouterr()
        output = captured.out
        assert "Timeline" in output
        assert "session-start" in output

    def test_print_report_no_data(self, capsys: pytest.CaptureFixture) -> None:
        """Test printing report with no data."""
        stats = SessionStats()

        _print_report(stats, "2026-01-15", [])

        captured = capsys.readouterr()
        output = captured.out
        assert "Daily Session Summary" in output


class TestJsonReport:
    """Tests for _json_report function."""

    def test_json_report_structure(self) -> None:
        """Test JSON report structure."""
        stats = SessionStats()
        stats.sessions = ["2026-01-15T10:00:00Z"]
        stats.prompts = ["2026-01-15T10:01:00Z"]
        stats.stops = ["2026-01-15T10:02:00Z"]
        stats.status_ok = 2
        stats.status_degraded = 1
        stats.projects = {"/home/project1": 2}
        stats.errors = [{"time": "10:00:00", "errors": ["e1"]}]
        stats.timeline = [{"time": "10:00:00", "event": "test"}]

        result = _json_report(stats, "2026-01-15", ["error line"])

        assert result["date"] == "2026-01-15"
        assert result["sessions"] == 1
        assert result["prompts"] == 1
        assert result["stops"] == 1
        assert result["status_ok"] == 2
        assert result["status_degraded"] == 1
        assert result["projects"] == {"/home/project1": 2}
        assert len(result["validation_errors"]) == 1
        assert result["system_error_count"] == 1
        assert len(result["timeline"]) == 1


class TestMain:
    """Tests for main function."""

    def test_main_no_date_specified(self, capsys: pytest.CaptureFixture) -> None:
        """Test main exits with error when no date specified."""
        exit_code = main([])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err or "specify --date" in captured.err

    def test_main_with_date_no_project(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test main with date but no matching project."""
        # Create a project with no event log
        (tmp_path / ".memory").mkdir()
        (tmp_path / ".git").mkdir()

        exit_code = main(["--date", "2026-01-15", "--project", str(tmp_path)])
        # Should complete but with empty results
        assert exit_code == 0

    def test_main_with_today(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with --today flag."""
        from datetime import date

        today = date.today().isoformat()

        # Setup event log for today
        events_dir = tmp_path / "artifacts" / "memory-hook" / "events"
        events_dir.mkdir(parents=True)
        log_file = events_dir / f"{today}.jsonl"
        log_file.write_text(json.dumps({
            "event": "session-start",
            "generated_at": f"{today}T10:00:00Z",
            "status": "ok",
            "cwd": str(tmp_path),
        }) + "\n")

        exit_code = main(["--today", "--project", str(tmp_path)])
        assert exit_code == 0

    def test_main_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test main with --json flag."""
        events_dir = tmp_path / "artifacts" / "memory-hook" / "events"
        events_dir.mkdir(parents=True)
        log_file = events_dir / "2026-01-15.jsonl"
        log_file.write_text(json.dumps({
            "event": "session-start",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": str(tmp_path),
        }) + "\n")

        exit_code = main(["--date", "2026-01-15", "--project", str(tmp_path), "--json"])
        assert exit_code == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["date"] == "2026-01-15"

    def test_main_with_legacy_events(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test main with legacy events.jsonl."""
        events_dir = tmp_path / "artifacts" / "memory-hook"
        events_dir.mkdir(parents=True)
        log_file = events_dir / "events.jsonl"
        log_file.write_text(json.dumps({
            "event": "session-start",
            "generated_at": "2026-01-15T10:00:00Z",
            "status": "ok",
            "cwd": str(tmp_path),
        }) + "\n")

        exit_code = main(["--date", "2026-01-15", "--project", str(tmp_path)])
        assert exit_code == 0


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_load_events_unicode(self, tmp_path: Path) -> None:
        """Test loading events with unicode content."""
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(
            json.dumps({"event": "test", "message": "Hello 世界"}) + "\n",
            encoding="utf-8"
        )

        result = _load_events(log_file)
        assert len(result) == 1
        assert "世界" in result[0]["message"]

    def test_filter_by_date_no_timestamp(self) -> None:
        """Test filtering events with no timestamp."""
        events = [
            {"event": "test1"},  # No timestamp
        ]

        result = _filter_by_date(events, "2026-01-15")
        assert result == []

    def test_session_stats_short_timestamp(self) -> None:
        """Test SessionStats handles short timestamps."""
        stats = SessionStats()
        stats.add_event({
            "event": "session-start",
            "generated_at": "10:00",  # Short timestamp
            "status": "ok",
            "cwd": "/home/project",
        })

        assert len(stats.sessions) == 1
        assert stats.timeline[0]["time"] == "10:00"  # Preserved as-is

    def test_load_errors_long_lines_preserved(self, tmp_path: Path) -> None:
        """Test that error lines are preserved without truncation in _load_errors."""
        errors_dir = tmp_path / "memory" / "system" / "errors"
        errors_dir.mkdir(parents=True)
        error_file = errors_dir / "2026-01-15.log"
        # Include the date in the line so it's matched
        error_file.write_text("2026-01-15 " + "a" * 200 + "\n")

        result = _load_errors(tmp_path, "2026-01-15")
        assert len(result) == 1
        # The function itself doesn't truncate, but _print_report does
        assert len(result[0]) == 211  # "2026-01-15 " + 200 chars
