from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_core.tools.codex_session_analyzer import (
    CODEX_SESSIONS_DIR,
    SessionAnalyzer,
    find_rollout_files,
    find_todays_sessions,
    main,
)


class TestSessionAnalyzer:
    """Tests for SessionAnalyzer class."""

    def test_init_default_values(self) -> None:
        """Test that SessionAnalyzer initializes with empty values."""
        analyzer = SessionAnalyzer()
        assert analyzer.session_id == ""
        assert analyzer.cwd == ""
        assert analyzer.model_provider == ""
        assert analyzer.cli_version == ""
        assert analyzer.started_at == ""
        assert analyzer.user_messages == []
        assert analyzer.assistant_messages == []
        assert analyzer.tool_calls == []
        assert analyzer.token_events == []
        assert analyzer.errors == []

    def test_parse_file_session_meta(self, tmp_path: Path) -> None:
        """Test parsing session_meta event."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "session_meta",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "id": "test-session-123",
                    "cwd": "/home/test/project",
                    "model_provider": "openai",
                    "cli_version": "1.0.0",
                    "timestamp": "2026-01-15T10:00:00Z",
                },
            })
        )

        analyzer.parse_file(jsonl_file)

        assert analyzer.session_id == "test-session-123"
        assert analyzer.cwd == "/home/test/project"
        assert analyzer.model_provider == "openai"
        assert analyzer.cli_version == "1.0.0"
        assert analyzer.started_at == "2026-01-15T10:00:00Z"

    def test_parse_file_user_message(self, tmp_path: Path) -> None:
        """Test parsing user_message event."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "user_message",
                    "message": "Hello world",
                },
            })
        )

        analyzer.parse_file(jsonl_file)

        assert analyzer.total_user_messages == 1
        assert analyzer.user_messages[0]["timestamp"] == "2026-01-15T10:00:00Z"
        assert analyzer.user_messages[0]["message"] == "Hello world"

    def test_parse_file_agent_message(self, tmp_path: Path) -> None:
        """Test parsing agent_message event."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "agent_message",
                    "message": "I can help you",
                },
            })
        )

        analyzer.parse_file(jsonl_file)

        assert analyzer.total_assistant_messages == 1
        assert analyzer.assistant_messages[0]["message"] == "I can help you"

    def test_parse_file_agent_message_with_phase_skipped(self, tmp_path: Path) -> None:
        """Test that agent_message with phase is skipped."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "agent_message",
                    "message": "Internal message",
                    "phase": "planning",
                },
            })
        )

        analyzer.parse_file(jsonl_file)

        assert analyzer.total_assistant_messages == 0

    def test_parse_file_agent_reasoning(self, tmp_path: Path) -> None:
        """Test parsing agent_reasoning event."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "agent_reasoning",
                    "text": "Thinking about this...",
                },
            })
        )

        analyzer.parse_file(jsonl_file)

        assert analyzer.total_assistant_messages == 1
        assert analyzer.assistant_messages[0]["message"] == "Thinking about this..."

    def test_parse_file_token_count(self, tmp_path: Path) -> None:
        """Test parsing token_count event."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "total_tokens": 150,
                        },
                    },
                },
            })
        )

        analyzer.parse_file(jsonl_file)

        assert len(analyzer.token_events) == 1
        assert analyzer.token_events[0]["input_tokens"] == 100
        assert analyzer.token_events[0]["output_tokens"] == 50
        assert analyzer.token_events[0]["total_tokens"] == 150

    def test_parse_file_function_call(self, tmp_path: Path) -> None:
        """Test parsing function_call (tool) event."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "response_item",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "function_call",
                    "name": "test_tool",
                    "arguments": '{"arg1": "value1"}',
                },
            })
        )

        analyzer.parse_file(jsonl_file)

        assert analyzer.total_tool_calls == 1
        assert analyzer.tool_calls[0]["name"] == "test_tool"
        assert analyzer.tool_calls[0]["arguments"] == '{"arg1": "value1"}'

    def test_parse_file_invalid_json_skipped(self, tmp_path: Path) -> None:
        """Test that invalid JSON lines are skipped."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            "not valid json\n"
            + json.dumps({
                "type": "session_meta",
                "payload": {"id": "test"},
            })
        )

        analyzer.parse_file(jsonl_file)

        assert analyzer.session_id == "test"

    def test_parse_file_empty_lines_skipped(self, tmp_path: Path) -> None:
        """Test that empty lines are skipped."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            "\n\n"
            + json.dumps({
                "type": "session_meta",
                "payload": {"id": "test"},
            })
            + "\n\n"
        )

        analyzer.parse_file(jsonl_file)

        assert analyzer.session_id == "test"

    def test_total_user_messages_property(self) -> None:
        """Test total_user_messages property."""
        analyzer = SessionAnalyzer()
        assert analyzer.total_user_messages == 0
        analyzer.user_messages = [{"message": "m1"}, {"message": "m2"}]
        assert analyzer.total_user_messages == 2

    def test_total_assistant_messages_property(self) -> None:
        """Test total_assistant_messages property."""
        analyzer = SessionAnalyzer()
        assert analyzer.total_assistant_messages == 0
        analyzer.assistant_messages = [{"message": "m1"}, {"message": "m2"}]
        assert analyzer.total_assistant_messages == 2

    def test_total_tool_calls_property(self) -> None:
        """Test total_tool_calls property."""
        analyzer = SessionAnalyzer()
        assert analyzer.total_tool_calls == 0
        analyzer.tool_calls = [{"name": "t1"}, {"name": "t2"}]
        assert analyzer.total_tool_calls == 2

    def test_token_summary_empty(self) -> None:
        """Test token_summary with no events."""
        analyzer = SessionAnalyzer()
        assert analyzer.token_summary == {}

    def test_token_summary_multiple_events(self) -> None:
        """Test token_summary aggregates multiple events."""
        analyzer = SessionAnalyzer()
        analyzer.token_events = [
            {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300},
        ]

        summary = analyzer.token_summary
        assert summary["total_input_tokens"] == 300
        assert summary["total_output_tokens"] == 150
        assert summary["total_tokens"] == 450

    def test_token_summary_with_missing_keys(self) -> None:
        """Test token_summary handles missing keys gracefully."""
        analyzer = SessionAnalyzer()
        analyzer.token_events = [
            {"input_tokens": 100},  # missing output_tokens and total_tokens
        ]

        summary = analyzer.token_summary
        assert summary["total_input_tokens"] == 100
        assert summary["total_output_tokens"] == 0
        assert summary["total_tokens"] == 0

    def test_tool_call_frequency(self, tmp_path: Path) -> None:
        """Test tool_call_frequency returns sorted counts."""
        analyzer = SessionAnalyzer()
        analyzer.tool_calls = [
            {"name": "tool_a"},
            {"name": "tool_b"},
            {"name": "tool_a"},
            {"name": "tool_c"},
            {"name": "tool_a"},
        ]

        freq = analyzer.tool_call_frequency
        assert freq == [("tool_a", 3), ("tool_b", 1), ("tool_c", 1)]

    def test_tool_call_frequency_empty(self) -> None:
        """Test tool_call_frequency with no tool calls."""
        analyzer = SessionAnalyzer()
        assert analyzer.tool_call_frequency == []

    def test_print_report(self, capsys: pytest.CaptureFixture) -> None:
        """Test print_report outputs expected content."""
        analyzer = SessionAnalyzer()
        analyzer.session_id = "test-session-12345"
        analyzer.model_provider = "openai"
        analyzer.cwd = "/home/test"
        analyzer.started_at = "2026-01-15T10:00:00Z"
        analyzer.cli_version = "1.0.0"
        analyzer.user_messages = [{"timestamp": "2026-01-15T10:00:00Z", "message": "Hello"}]
        analyzer.tool_calls = [{"name": "test_tool", "timestamp": "2026-01-15T10:00:00Z"}]

        analyzer.print_report(show_conversation=True, max_msg_len=100)

        captured = capsys.readouterr()
        output = captured.out
        assert "Session Report" in output
        # Session ID is truncated to first 16 chars with "..." suffix in output
        assert "test-session-123" in output
        assert "openai" in output
        assert "User messages:      1" in output
        assert "Tool calls:         1" in output
        assert "Hello" in output

    def test_print_report_no_conversation(self, capsys: pytest.CaptureFixture) -> None:
        """Test print_report with show_conversation=False."""
        analyzer = SessionAnalyzer()
        analyzer.session_id = "test-session-12345"
        analyzer.model_provider = "openai"
        analyzer.user_messages = [{"timestamp": "2026-01-15T10:00:00Z", "message": "Hello"}]

        analyzer.print_report(show_conversation=False, max_msg_len=100)

        captured = capsys.readouterr()
        output = captured.out
        assert "Session Report" in output
        assert "User messages:      1" in output
        assert "Conversation:" not in output


class TestFindRolloutFiles:
    """Tests for find_rollout_files function."""

    def test_find_no_sessions_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding files when sessions dir doesn't exist."""
        fake_dir = tmp_path / "nonexistent"
        monkeypatch.setattr(
            "memory_core.tools.codex_session_analyzer.CODEX_SESSIONS_DIR",
            fake_dir,
        )
        result = find_rollout_files()
        assert result == []

    def test_find_by_thread_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding files by thread ID."""
        sessions_dir = tmp_path / ".codex" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "rollout-abc123.jsonl").write_text("{}")
        (sessions_dir / "rollout-def456.jsonl").write_text("{}")

        monkeypatch.setattr(
            "memory_core.tools.codex_session_analyzer.CODEX_SESSIONS_DIR",
            sessions_dir,
        )

        result = find_rollout_files(thread_id="abc123")
        assert len(result) == 1
        assert "abc123" in str(result[0])

    def test_find_by_date_compact(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding files by date in compact format."""
        sessions_dir = tmp_path / ".codex" / "sessions"
        sessions_dir.mkdir(parents=True)
        # Create file with date in path using compact format 20260115
        # The path includes the date in individual components: 2026/01/15
        # But compact format "20260115" won't match "2026/01/15" path
        # So we create a path that contains the compact format
        dated_dir = sessions_dir / "20260115"
        dated_dir.mkdir(parents=True)
        (dated_dir / "rollout-test.jsonl").write_text("{}")

        monkeypatch.setattr(
            "memory_core.tools.codex_session_analyzer.CODEX_SESSIONS_DIR",
            sessions_dir,
        )

        # Use compact date format 20260115
        result = find_rollout_files(target_date="20260115")
        assert len(result) == 1

    def test_find_by_date_path_format(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding files by date in path format."""
        sessions_dir = tmp_path / ".codex" / "sessions" / "2026" / "01" / "15"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "rollout-test.jsonl").write_text("{}")

        monkeypatch.setattr(
            "memory_core.tools.codex_session_analyzer.CODEX_SESSIONS_DIR",
            sessions_dir.parent.parent.parent.parent,
        )

        result = find_rollout_files(target_date="2026/01/15")
        assert len(result) == 1


class TestFindTodaysSessions:
    """Tests for find_todays_sessions function."""

    def test_find_todays_sessions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding today's sessions."""
        from datetime import date

        today = date.today().strftime("%Y-%m-%d")
        sessions_dir = tmp_path / ".codex" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / f"rollout-{today}-test.jsonl").write_text("{}")

        monkeypatch.setattr(
            "memory_core.tools.codex_session_analyzer.CODEX_SESSIONS_DIR",
            sessions_dir,
        )

        result = find_todays_sessions()
        assert len(result) == 1


class TestMain:
    """Tests for main function."""

    def test_main_no_files_found(self, capsys: pytest.CaptureFixture) -> None:
        """Test main exits with code 1 when no files found."""
        exit_code = main(["--rollout", "/nonexistent/path/*.jsonl"])
        assert exit_code == 1

    def test_main_with_rollout_file(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test main with valid rollout file."""
        jsonl_file = tmp_path / "rollout-test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "session_meta",
                "payload": {
                    "id": "test",
                    "cwd": "/home",
                    "model_provider": "openai",
                    "cli_version": "1.0",
                    "timestamp": "2026-01-15T10:00:00Z",
                },
            })
        )

        exit_code = main(["--rollout", str(jsonl_file)])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Session Report" in captured.out

    def test_main_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test main with JSON output."""
        jsonl_file = tmp_path / "rollout-test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "session_meta",
                "payload": {
                    "id": "test-session",
                    "cwd": "/home",
                    "model_provider": "openai",
                    "cli_version": "1.0",
                    "timestamp": "2026-01-15T10:00:00Z",
                },
            })
        )

        exit_code = main(["--rollout", str(jsonl_file), "--json"])
        assert exit_code == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["session_id"] == "test-session"

    def test_main_no_conversation(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test main with --no-conversation flag."""
        jsonl_file = tmp_path / "rollout-test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "user_message",
                    "message": "Hello",
                },
            })
        )

        exit_code = main(["--rollout", str(jsonl_file), "--no-conversation"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Conversation:" not in captured.out

    def test_main_max_len(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test main with custom --max-len."""
        jsonl_file = tmp_path / "rollout-test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "user_message",
                    "message": "a" * 100,
                },
            })
        )

        exit_code = main(["--rollout", str(jsonl_file), "--max-len", "10"])
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "..." in captured.out

    def test_main_multiple_files(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Test main with multiple files."""
        jsonl_file1 = tmp_path / "rollout-1.jsonl"
        jsonl_file2 = tmp_path / "rollout-2.jsonl"
        jsonl_file1.write_text(
            json.dumps({
                "type": "session_meta",
                "payload": {"id": "session-1", "cwd": "/home", "model_provider": "openai", "cli_version": "1.0", "timestamp": "2026-01-15T10:00:00Z"},
            })
        )
        jsonl_file2.write_text(
            json.dumps({
                "type": "session_meta",
                "payload": {"id": "session-2", "cwd": "/home", "model_provider": "openai", "cli_version": "1.0", "timestamp": "2026-01-15T10:00:00Z"},
            })
        )

        exit_code = main(["--rollout", str(tmp_path / "rollout-*.jsonl")])
        assert exit_code == 0

        captured = capsys.readouterr()
        # Should have multiple file headers
        assert "File:" in captured.out


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_empty_user_message_skipped(self, tmp_path: Path) -> None:
        """Test empty user messages are skipped."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "user_message",
                    "message": "   ",  # whitespace only
                },
            })
        )

        analyzer.parse_file(jsonl_file)
        assert analyzer.total_user_messages == 0

    def test_empty_assistant_message_skipped(self, tmp_path: Path) -> None:
        """Test empty assistant messages are skipped."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "agent_message",
                    "message": "   ",  # whitespace only
                },
            })
        )

        analyzer.parse_file(jsonl_file)
        assert analyzer.total_assistant_messages == 0

    def test_empty_reasoning_text_skipped(self, tmp_path: Path) -> None:
        """Test empty reasoning text is skipped."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "agent_reasoning",
                    "text": "   ",  # whitespace only
                },
            })
        )

        analyzer.parse_file(jsonl_file)
        assert analyzer.total_assistant_messages == 0

    def test_unknown_event_type_ignored(self, tmp_path: Path) -> None:
        """Test unknown event types are ignored."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "unknown_type",
                "payload": {"data": "test"},
            })
        )

        analyzer.parse_file(jsonl_file)
        assert analyzer.session_id == ""
        assert analyzer.total_user_messages == 0

    def test_unicode_handling(self, tmp_path: Path) -> None:
        """Test handling of unicode content."""
        analyzer = SessionAnalyzer()
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            json.dumps({
                "type": "event_msg",
                "timestamp": "2026-01-15T10:00:00Z",
                "payload": {
                    "type": "user_message",
                    "message": "Hello 世界 🌍",
                },
            })
        )

        analyzer.parse_file(jsonl_file)
        assert analyzer.total_user_messages == 1
        assert "世界" in analyzer.user_messages[0]["message"]


class TestCODEX_SESSIONS_DIR:
    """Tests for CODEX_SESSIONS_DIR constant."""

    def test_codex_sessions_dir_is_path(self) -> None:
        """Test that CODEX_SESSIONS_DIR is a Path object."""
        assert isinstance(CODEX_SESSIONS_DIR, Path)

    def test_codex_sessions_dir_ends_with_sessions(self) -> None:
        """Test that CODEX_SESSIONS_DIR path ends with .codex/sessions."""
        assert str(CODEX_SESSIONS_DIR).endswith(".codex/sessions")
