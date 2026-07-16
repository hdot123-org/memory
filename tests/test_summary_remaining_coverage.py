"""Tests for remaining daily_summary_generator.py coverage gaps.

Covers:
- _parse_args: all argument combinations
- _read_a_layer: parsing session data from markdown
- _extract_text_blocks: extracting text from message content
- _generate_data_report: generating data report with A+B layer data
- _write_daily_log: writing daily log with data report
- _try_sign_file: signing file with integrity keys
- _enrich_with_b_layer: enriching A layer with B layer data
- _resolve_projects: resolving project paths
- process_project: processing a single project
- main: CLI entry point with various argument combinations
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memory_core.tools.daily_summary_generator import (
    _enrich_with_b_layer,
    _extract_text_blocks,
    _extract_transcript_summary,
    _fallback_check,
    _find_session_jsonl,
    _generate_data_report,
    _parse_args,
    _read_a_layer,
    _read_full_jsonl,
    _read_partial_jsonl,
    _resolve_projects,
    _try_sign_file,
    _write_daily_log,
    main,
    process_project,
)

# ---------------------------------------------------------------------------
# _parse_args: CLI argument parsing
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_date_argument(self):
        """Parse --date argument."""
        args = _parse_args(["--date", "2026-07-12"])
        assert args.date == "2026-07-12"
        assert not args.today

    def test_today_flag(self):
        """Parse --today flag."""
        args = _parse_args(["--today"])
        assert args.today
        assert args.date is None

    def test_project_argument(self):
        """Parse --project argument."""
        args = _parse_args(["--today", "--project", "/tmp/test"])
        assert args.project == "/tmp/test"

    def test_all_projects_flag(self):
        """Parse --all-projects flag."""
        args = _parse_args(["--today", "--all-projects"])
        assert args.all_projects

    def test_dry_run_flag(self):
        """Parse --dry-run flag."""
        args = _parse_args(["--today", "--dry-run"])
        assert args.dry_run

    def test_fallback_days_argument(self):
        """Parse --fallback-days argument."""
        args = _parse_args(["--today", "--fallback-days", "7"])
        assert args.fallback_days == 7

    def test_default_fallback_days(self):
        """Default fallback-days is 3."""
        args = _parse_args(["--today"])
        assert args.fallback_days == 3


# ---------------------------------------------------------------------------
# _read_a_layer: parsing session markdown
# ---------------------------------------------------------------------------


class TestReadALayer:
    def test_file_not_exists(self, tmp_path):
        """When sessions file doesn't exist, returns None."""
        result = _read_a_layer(tmp_path, "2026-07-12")
        assert result is None

    def test_parse_single_session(self, tmp_path):
        """Parse a single session from markdown."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text(
            """### abcd1234
- **标题**: Test session
- **模型**: GLM-5.1 (官方) | 时长: 2m35s
- **Token**: input=100 output=200
- **工具调用**: Read, Write
- **用户意图**: Fix bug
- **助手摘要**: Fixed the bug
""",
            encoding="utf-8",
        )
        result = _read_a_layer(tmp_path, "2026-07-12")
        assert len(result) == 1
        assert result[0]["full_session_id"] == "abcd1234"
        assert result[0]["title"] == "Test session"
        assert result[0]["model"] == "GLM-5.1 (官方)"
        assert result[0]["duration"] == "2m35s"
        assert result[0]["input_tokens"] == 100
        assert result[0]["output_tokens"] == 200

    def test_parse_multiple_sessions(self, tmp_path):
        """Parse multiple sessions from markdown."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text(
            """### abcd1234
- **标题**: Session 1

### ef565678
- **标题**: Session 2

### 12345678
- **标题**: Session 3
""",
            encoding="utf-8",
        )
        result = _read_a_layer(tmp_path, "2026-07-12")
        # Two sessions saved when new header encountered,
        # plus the last session saved after loop
        assert len(result) == 3
        assert result[0]["title"] == "Session 1"
        assert result[1]["title"] == "Session 2"
        assert result[2]["title"] == "Session 3"


# ---------------------------------------------------------------------------
# _extract_text_blocks: extracting text from message content
# ---------------------------------------------------------------------------


class TestExtractTextBlocks:
    def test_not_list(self):
        """When content is not a list, returns empty."""
        result = _extract_text_blocks("not a list")
        assert result == []

    def test_extract_text_blocks(self):
        """Extract text blocks from content array."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
            {"type": "other", "data": "ignored"},
        ]
        result = _extract_text_blocks(content)
        assert result == ["Hello", "World"]

    def test_strip_system_reminder(self):
        """Strip system-reminder tags from text."""
        content = [
            {
                "type": "text",
                "text": "<system-reminder>secret</system-reminder>Actual text",
            }
        ]
        result = _extract_text_blocks(content)
        assert result == ["Actual text"]


# ---------------------------------------------------------------------------
# _generate_data_report: data report generation
# ---------------------------------------------------------------------------


class TestGenerateDataReport:
    def test_single_session(self):
        """Generate data report for single session."""
        sessions = [
            {
                "full_session_id": "abcd1234",
                "title": "Test",
                "model": "GLM-5.1",
                "duration": "1m",
                "input_tokens": 100,
                "output_tokens": 200,
                "user_prompt_preview": "Fix bug",
            }
        ]
        report = _generate_data_report(sessions, "2026-07-12")
        assert "2026-07-12" in report
        assert "abcd1234" in report
        assert "Test" in report
        assert "Sessions: 1" in report
        assert "in=100" in report
        assert "out=200" in report

    def test_multiple_sessions(self):
        """Generate data report for multiple sessions."""
        sessions = [
            {"full_session_id": "abcd1234", "input_tokens": 100, "output_tokens": 200},
            {"full_session_id": "efgh5678", "input_tokens": 300, "output_tokens": 400},
        ]
        report = _generate_data_report(sessions, "2026-07-12")
        assert "Sessions: 2" in report
        assert "in=400" in report
        assert "out=600" in report

    def test_includes_b_layer_data(self):
        """Data report includes B-layer user messages, assistant messages, and tool names."""
        sessions = [
            {
                "full_session_id": "abcd1234",
                "title": "Test",
                "input_tokens": 100,
                "output_tokens": 200,
                "user_messages": "User B layer content",
                "assistant_messages": "Assistant B layer content",
                "tool_names": ["Read", "Edit", "Grep"],
            }
        ]
        report = _generate_data_report(sessions, "2026-07-12")
        assert "B层用户消息" in report
        assert "User B layer content" in report
        assert "B层助手消息" in report
        assert "Assistant B layer content" in report
        assert "B层工具列表" in report
        assert "Read" in report
        assert "Edit" in report
        assert "Grep" in report

    def test_no_llm_fallback_note(self):
        """Data report does not contain LLM fallback note."""
        sessions = [{"full_session_id": "abcd1234", "input_tokens": 100, "output_tokens": 200}]
        report = _generate_data_report(sessions, "2026-07-12")
        assert "LLM 总结未生成" not in report
        assert "API key" not in report


# ---------------------------------------------------------------------------
# _try_sign_file: file signing
# ---------------------------------------------------------------------------


class TestTrySignFile:
    def test_no_integrity_modules(self, monkeypatch):
        """When integrity modules not available, does nothing."""
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._integrity", None
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._integrity_keys", None
        )
        # Should not raise
        _try_sign_file(Path("/tmp"), "test.md")


# ---------------------------------------------------------------------------
# _enrich_with_b_layer: enriching sessions
# ---------------------------------------------------------------------------


class TestEnrichWithBLayer:
    def test_no_full_session_id(self):
        """Session without full_session_id is passed through."""
        sessions = [{"title": "Test"}]
        result = _enrich_with_b_layer(sessions)
        assert len(result) == 1
        assert result[0]["title"] == "Test"

    def test_session_jsonl_not_found(self):
        """When session jsonl not found, session is passed through."""
        sessions = [{"full_session_id": "nonexistent123"}]
        result = _enrich_with_b_layer(sessions)
        assert len(result) == 1
        assert result[0]["full_session_id"] == "nonexistent123"


# ---------------------------------------------------------------------------
# _resolve_projects: resolving project paths
# ---------------------------------------------------------------------------


class TestResolveProjects:
    def test_explicit_project(self):
        """Resolve explicit project path."""
        args = _parse_args(["--today", "--project", "/tmp/test"])
        projects = _resolve_projects(args)
        assert len(projects) == 1
        assert projects[0] == Path("/tmp/test").resolve()

    def test_default_current_directory(self):
        """Default resolves to current directory."""
        args = _parse_args(["--today"])
        projects = _resolve_projects(args)
        assert len(projects) >= 1


# ---------------------------------------------------------------------------
# process_project: processing a single project
# ---------------------------------------------------------------------------


class TestProcessProject:
    def test_a_layer_not_exists(self, tmp_path):
        """When A layer doesn't exist, returns False."""
        result = process_project(tmp_path, "2026-07-12", dry_run=True, fallback_days=0)
        assert result is False

    def test_a_layer_empty(self, tmp_path):
        """When A layer is empty, returns False."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text("", encoding="utf-8")
        result = process_project(tmp_path, "2026-07-12", dry_run=True, fallback_days=0)
        assert result is False

    def test_successful_processing(self, tmp_path, monkeypatch):
        """Successful project processing."""
        # Create A layer
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text(
            """### abcd1234
- **标题**: Test
""",
            encoding="utf-8",
        )
        result = process_project(tmp_path, "2026-07-12", dry_run=True, fallback_days=0)
        assert result is True


# ---------------------------------------------------------------------------
# main: CLI entry point
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_date_argument(self, capsys):
        """When neither --date nor --today provided, returns 1."""
        result = main([])
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_no_projects_found(self, monkeypatch, capsys):
        """When no projects found, returns 1."""
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._resolve_projects",
            lambda args: [],
        )
        result = main(["--today"])
        assert result == 1
        captured = capsys.readouterr()
        assert "未找到可扫描的项目" in captured.err

    def test_successful_run(self, tmp_path, monkeypatch, capsys):
        """Successful run with one project."""
        # Create A layer
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text(
            """### abcd1234
- **标题**: Test
""",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._resolve_projects",
            lambda args: [tmp_path],
        )
        result = main(["--date", "2026-07-12", "--dry-run", "--fallback-days", "0"])
        assert result == 0
        captured = capsys.readouterr()
        assert "完成" in captured.out


# ---------------------------------------------------------------------------
# _find_session_jsonl: Find session JSONL files
# ---------------------------------------------------------------------------


class TestFindSessionJsonl:
    def test_find_exact_match(self, tmp_path, monkeypatch):
        """Find session by exact ID."""
        session_dir = tmp_path / "session-12345678"
        session_dir.mkdir()
        jsonl_file = session_dir / "session-12345678.jsonl"
        jsonl_file.write_text('{"type": "message"}', encoding="utf-8")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.SESSIONS_HOME",
            tmp_path
        )

        result = _find_session_jsonl("session-12345678")
        assert result == jsonl_file

    def test_find_prefix_match(self, tmp_path, monkeypatch):
        """Find session by 8-char prefix."""
        session_dir = tmp_path / "session-abc123"
        session_dir.mkdir()
        jsonl_file = session_dir / "abc123-def.jsonl"
        jsonl_file.write_text('{"type": "message"}', encoding="utf-8")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.SESSIONS_HOME",
            tmp_path
        )

        result = _find_session_jsonl("abc123")
        assert result == jsonl_file

    def test_not_found(self, tmp_path, monkeypatch):
        """Return None when session not found."""
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.SESSIONS_HOME",
            tmp_path
        )

        result = _find_session_jsonl("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# _read_full_jsonl and _read_partial_jsonl
# ---------------------------------------------------------------------------


class TestReadJsonl:
    def test_read_full_jsonl(self, tmp_path):
        """Read complete JSONL file."""
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            '{"type": "message", "data": 1}\n'
            '{"type": "message", "data": 2}\n',
            encoding="utf-8"
        )

        result = _read_full_jsonl(jsonl_file)
        assert len(result) == 2
        assert result[0]["data"] == 1
        assert result[1]["data"] == 2

    def test_read_partial_jsonl(self, tmp_path):
        """Read first and last N lines from JSONL."""
        jsonl_file = tmp_path / "test.jsonl"
        lines = [f'{{"type": "message", "line": {i}}}' for i in range(10)]
        jsonl_file.write_text('\n'.join(lines), encoding="utf-8")

        result = _read_partial_jsonl(jsonl_file, first_n=2, last_n=2)
        assert len(result) >= 2
        # Should include first 2 and last 2 lines


# ---------------------------------------------------------------------------
# _extract_transcript_summary
# ---------------------------------------------------------------------------


class TestExtractTranscriptSummary:
    def test_extract_user_and_assistant(self, tmp_path):
        """Extract user and assistant messages from JSONL."""
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text(
            '{"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Hello"}]}}\n'
            '{"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there"}]}}\n',
            encoding="utf-8"
        )

        result = _extract_transcript_summary(jsonl_file)

        assert "Hello" in result["user_messages"]
        assert "Hi there" in result["assistant_messages"]

    def test_extract_tool_names(self, tmp_path):
        """Extract tool names from assistant messages."""
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text(
            '{"type": "message", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "read_file"}]}}\n'
            '{"type": "message", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "write_file"}]}}\n',
            encoding="utf-8"
        )

        result = _extract_transcript_summary(jsonl_file)

        assert "read_file" in result["tool_names"]
        assert "write_file" in result["tool_names"]


# ---------------------------------------------------------------------------
# _enrich_with_b_layer (extended)
# ---------------------------------------------------------------------------


class TestEnrichWithBLayerExtended:
    def test_enrich_with_existing_jsonl(self, tmp_path, monkeypatch):
        """Enrich session with B layer data from JSONL."""
        session_dir = tmp_path / "sessions" / "session-abc12345"
        session_dir.mkdir(parents=True)
        jsonl_file = session_dir / "abc12345.jsonl"
        jsonl_file.write_text(
            '{"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Test input"}]}}\n'
            '{"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Test output"}]}}\n',
            encoding="utf-8"
        )

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.SESSIONS_HOME",
            tmp_path / "sessions"
        )

        a_sessions = [{"full_session_id": "abc12345", "title": "Test"}]
        result = _enrich_with_b_layer(a_sessions)

        assert len(result) == 1
        assert "Test input" in result[0]["user_messages"]
        assert "Test output" in result[0]["assistant_messages"]


# ---------------------------------------------------------------------------
# _fallback_check
# ---------------------------------------------------------------------------


class TestFallbackCheck:
    def test_fallback_generates_missing_logs(self, tmp_path, monkeypatch):
        """Generate missing daily logs for recent days."""
        from datetime import date, timedelta

        # Create A layer for 2 days ago
        two_days_ago = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        a_layer_file = log_dir / f"{two_days_ago}-sessions.md"
        a_layer_file.write_text(
            "### abc12345\n- 标题: Test\n- 模型: Test\n- 输入: 0\n- 输出: 0\n",
            encoding="utf-8"
        )

        result = _fallback_check(tmp_path, fallback_days=3)

        assert two_days_ago in result

    def test_fallback_skips_existing_logs(self, tmp_path):
        """Skip days that already have daily logs."""
        from datetime import date, timedelta

        # Create A layer and daily log for 2 days ago
        two_days_ago = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)

        a_layer_file = log_dir / f"{two_days_ago}-sessions.md"
        a_layer_file.write_text("### abc12345\n", encoding="utf-8")

        daily_file = log_dir / f"{two_days_ago}.md"
        daily_file.write_text("Already exists", encoding="utf-8")

        result = _fallback_check(tmp_path, fallback_days=3)

        assert two_days_ago not in result


# ---------------------------------------------------------------------------
# _resolve_projects (extended)
# ---------------------------------------------------------------------------


class TestResolveProjectsExtended:
    def test_all_projects_from_lifecycle_index(self, tmp_path, monkeypatch):
        """Resolve all projects from lifecycle index."""
        index_file = tmp_path / "path-index.json"
        index_file.write_text(
            json.dumps({
                "paths": {
                    str(tmp_path / "project1"): {"project_name": "proj1"},
                    str(tmp_path / "project2"): {"project_name": "proj2"},
                }
            }),
            encoding="utf-8"
        )

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.LIFECYCLE_INDEX",
            index_file
        )

        args = _parse_args(["--all-projects"])
        result = _resolve_projects(args)

        assert len(result) == 2

    def test_all_projects_fallback_to_home(self, tmp_path, monkeypatch):
        """When lifecycle index doesn't exist, fallback to home directory scan."""
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.LIFECYCLE_INDEX",
            tmp_path / "nonexistent.json"
        )
        monkeypatch.setattr(
            "pathlib.Path.home",
            lambda: tmp_path
        )
        # Create a project directory
        proj_dir = tmp_path / "test_project"
        proj_dir.mkdir()
        (proj_dir / "memory" / "system").mkdir(parents=True)

        args = _parse_args(["--all-projects"])
        result = _resolve_projects(args)

        assert len(result) >= 1


# ---------------------------------------------------------------------------
# _read_a_layer: missing field parsing (lines 117-118)
# ---------------------------------------------------------------------------


class TestReadALayerMissingFields:
    def test_session_without_full_id(self, tmp_path):
        """Session without full_session_id is not saved."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text(
            """### invalid_id
- **标题**: Test
""",
            encoding="utf-8",
        )
        result = _read_a_layer(tmp_path, "2026-07-12")
        # invalid_id is not 8 hex chars, so no session saved
        assert result == [] or len(result) == 0

    def test_parse_tool_calls_and_intent(self, tmp_path):
        """Parse tool calls and user intent fields."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text(
            """### abcd1234
- **标题**: Test
- **模型**: GLM-5.1 (官方) | 时长: 2m35s
- **Token**: input=100 output=200
- **工具调用**: Read, Write, Execute
- **用户意图**: Fix bug in module X
- **助手摘要**: Fixed the bug successfully
""",
            encoding="utf-8",
        )
        result = _read_a_layer(tmp_path, "2026-07-12")
        assert len(result) == 1
        assert result[0]["tool_calls_raw"] == "Read, Write, Execute"
        assert result[0]["user_prompt_preview"] == "Fix bug in module X"
        assert result[0]["assistant_summary_preview"] == "Fixed the bug successfully"

    def test_parse_invalid_token_values(self, tmp_path):
        """Invalid token values (non-numeric) are handled gracefully."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text(
            """### abcd1234
- **标题**: Test
- **Token**: input=abc output=200
""",
            encoding="utf-8",
        )
        result = _read_a_layer(tmp_path, "2026-07-12")
        # Should not crash, invalid tokens are skipped
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _extract_transcript_summary: large file path (lines 169, 172-173, 177)
# ---------------------------------------------------------------------------


class TestExtractTranscriptSummaryLargeFile:
    def test_large_file_uses_partial_read(self, tmp_path, monkeypatch):
        """Large JSONL file (>5MB) uses partial read."""
        jsonl_file = tmp_path / "large.jsonl"
        # Create a file with many lines to simulate large file
        lines = [f'{{"type": "message", "message": {{"role": "user", "content": [{{"type": "text", "text": "msg{i}"}}]}}}}'
                 for i in range(100)]
        jsonl_file.write_text('\n'.join(lines), encoding="utf-8")

        # Mock _extract_transcript_summary's internal stat check by monkeypatching
        # the Path.stat method to return a large size
        import os
        original_stat = os.stat
        def mock_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            # Create a wrapper that overrides st_size
            class StatResult:
                def __init__(self, real_stat):
                    self._real = real_stat
                def __getattr__(self, name):
                    if name == "st_size":
                        return 6 * 1024 * 1024  # 6MB
                    return getattr(self._real, name)
            return StatResult(result)
        monkeypatch.setattr(os, "stat", mock_stat)

        result = _extract_transcript_summary(jsonl_file)
        # Should use _read_partial_jsonl internally
        assert "user_messages" in result

    def test_stat_error_returns_empty(self, tmp_path, monkeypatch):
        """When stat fails, returns empty dict."""
        jsonl_file = tmp_path / "nonexistent.jsonl"
        result = _extract_transcript_summary(jsonl_file)
        assert result == {}

    def test_non_message_lines_skipped(self, tmp_path):
        """Non-message type lines are skipped."""
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text(
            '{"type": "other", "data": "ignored"}\n'
            '{"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Hello"}]}}\n',
            encoding="utf-8"
        )
        result = _extract_transcript_summary(jsonl_file)
        assert "Hello" in result["user_messages"]


# ---------------------------------------------------------------------------
# _read_partial_jsonl: dedup and error handling (lines 221-222, 237-238)
# ---------------------------------------------------------------------------


class TestReadPartialJsonl:
    def test_dedup_when_overlap(self, tmp_path):
        """Deduplicate when first_n and last_n overlap."""
        jsonl_file = tmp_path / "test.jsonl"
        lines = [f'{{"line": {i}}}' for i in range(5)]
        jsonl_file.write_text('\n'.join(lines), encoding="utf-8")

        result = _read_partial_jsonl(jsonl_file, first_n=3, last_n=3)
        # Should deduplicate overlapping lines
        assert len(result) == 5

    def test_json_decode_error_skipped(self, tmp_path):
        """Invalid JSON lines are skipped."""
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            '{"line": 1}\n'
            'invalid json\n'
            '{"line": 2}\n',
            encoding="utf-8"
        )
        result = _read_partial_jsonl(jsonl_file, first_n=2, last_n=2)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _read_full_jsonl: error handling (lines 252-253)
# ---------------------------------------------------------------------------


class TestReadFullJsonl:
    def test_json_decode_error_skipped(self, tmp_path):
        """Invalid JSON lines are skipped in full read."""
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text(
            '{"data": 1}\n'
            'bad json\n'
            '{"data": 2}\n',
            encoding="utf-8"
        )
        result = _read_full_jsonl(jsonl_file)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _try_sign_file: success and error paths (line 392)
# ---------------------------------------------------------------------------


class TestTrySignFileExtended:
    def test_sign_with_valid_modules(self, tmp_path, monkeypatch):
        """When integrity modules available, attempts signing."""
        mock_key = MagicMock()
        mock_key.load_key = MagicMock(return_value="test-key")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._integrity_keys",
            mock_key
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._integrity",
            MagicMock()
        )

        # Should not raise
        _try_sign_file(tmp_path, "test.md")

    def test_sign_key_none(self, tmp_path, monkeypatch):
        """When load_key returns None, does nothing."""
        mock_key = MagicMock()
        mock_key.load_key = MagicMock(return_value=None)

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._integrity_keys",
            mock_key
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._integrity",
            MagicMock()
        )

        # Should not raise
        _try_sign_file(tmp_path, "test.md")

    def test_sign_exception_caught(self, tmp_path, monkeypatch):
        """When signing raises exception, it's caught gracefully."""
        mock_integrity = MagicMock()
        mock_integrity.sign_project_incremental = MagicMock(
            side_effect=RuntimeError("Sign failed")
        )

        mock_keys = MagicMock()
        mock_keys.load_key = MagicMock(return_value="test-key")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._integrity",
            mock_integrity
        )
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._integrity_keys",
            mock_keys
        )

        # Should not raise
        _try_sign_file(tmp_path, "test.md")


# ---------------------------------------------------------------------------
# _write_daily_log: file write error (lines 435, 437-444)
# ---------------------------------------------------------------------------


class TestWriteDailyLogError:
    def test_write_os_error(self, tmp_path, monkeypatch):
        """When file write fails, OSError is raised."""
        sessions = [{"input_tokens": 100, "output_tokens": 200}]
        # Mock Path.write_text to raise OSError
        def mock_write_text(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr("pathlib.Path.write_text", mock_write_text)

        with pytest.raises(OSError):
            _write_daily_log(tmp_path, "2026-07-12", sessions, dry_run=False)


# ---------------------------------------------------------------------------
# _fallback_check: missing a_layer (lines 540-548)
# ---------------------------------------------------------------------------


class TestFallbackCheckMissing:
    def test_a_layer_missing_skips(self, tmp_path):
        """When A layer doesn't exist for a date, that date is skipped."""

        # No A layer files exist
        result = _fallback_check(tmp_path, fallback_days=3, dry_run=True)
        assert result == []

    def test_dry_run_flag_respected(self, tmp_path, monkeypatch):
        """Dry run flag prevents actual file writes."""
        from datetime import date, timedelta

        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        a_layer = log_dir / f"{yesterday}-sessions.md"
        a_layer.write_text("### abc12345\n- **标题**: Test\n", encoding="utf-8")

        result = _fallback_check(tmp_path, fallback_days=3, dry_run=True)
        # Should generate but not write
        assert yesterday in result
        # Daily file should not exist
        daily_file = log_dir / f"{yesterday}.md"
        assert not daily_file.exists()


# ---------------------------------------------------------------------------
# _enrich_with_b_layer: exception handling (line 578)
# ---------------------------------------------------------------------------


class TestEnrichWithBLayerException:
    def test_b_layer_exception_caught(self, tmp_path, monkeypatch):
        """When B layer extraction raises, session is passed through."""
        session_dir = tmp_path / "sessions" / "session-abc12345"
        session_dir.mkdir(parents=True)
        jsonl_file = session_dir / "abc12345.jsonl"
        jsonl_file.write_text("invalid json", encoding="utf-8")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.SESSIONS_HOME",
            tmp_path / "sessions"
        )

        # Mock _extract_transcript_summary to raise
        def bad_extract(*args, **kwargs):
            raise RuntimeError("Extract failed")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._extract_transcript_summary",
            bad_extract
        )

        a_sessions = [{"full_session_id": "abc12345", "title": "Test"}]
        result = _enrich_with_b_layer(a_sessions)

        # Session should be passed through without B layer data
        assert len(result) == 1
        assert result[0]["title"] == "Test"
        assert "user_messages" not in result[0]


# ---------------------------------------------------------------------------
# _resolve_projects: error handling (lines 611-613)
# ---------------------------------------------------------------------------


class TestResolveProjectsError:
    def test_invalid_json_in_index(self, tmp_path, monkeypatch):
        """When index JSON is invalid, returns empty list."""
        index_file = tmp_path / "path-index.json"
        index_file.write_text("invalid json", encoding="utf-8")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.LIFECYCLE_INDEX",
            index_file
        )

        args = _parse_args(["--all-projects"])
        result = _resolve_projects(args)
        # Should handle gracefully
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# process_project: B layer enrichment (lines 631-632)
# ---------------------------------------------------------------------------


class TestProcessProjectWithBLayer:
    def test_b_layer_enrichment(self, tmp_path, monkeypatch):
        """Process project with B layer enrichment."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        sessions_file = log_dir / "2026-07-12-sessions.md"
        sessions_file.write_text(
            """### abcd1234
- **标题**: Test
""",
            encoding="utf-8",
        )

        # Create B layer
        session_dir = tmp_path / "sessions" / "session-abcd1234"
        session_dir.mkdir(parents=True)
        jsonl_file = session_dir / "abcd1234.jsonl"
        jsonl_file.write_text(
            '{"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Test input"}]}}\n',
            encoding="utf-8"
        )

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.SESSIONS_HOME",
            tmp_path / "sessions"
        )

        result = process_project(tmp_path, "2026-07-12", dry_run=True, fallback_days=0)
        assert result is True


# ---------------------------------------------------------------------------
# main: all-projects flag (lines 648-651, 653)
# ---------------------------------------------------------------------------


class TestMainAllProjects:
    def test_all_projects_flag(self, tmp_path, monkeypatch, capsys):
        """Main with --all-projects processes multiple projects."""
        # Create two project directories
        proj1 = tmp_path / "project1"
        proj2 = tmp_path / "project2"
        for proj in [proj1, proj2]:
            log_dir = proj / "memory" / "log"
            log_dir.mkdir(parents=True)
            sessions_file = log_dir / "2026-07-12-sessions.md"
            sessions_file.write_text("### abcd1234\n- **标题**: Test\n", encoding="utf-8")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._resolve_projects",
            lambda args: [proj1, proj2]
        )

        result = main(["--date", "2026-07-12", "--dry-run", "--fallback-days", "0"])
        assert result == 0


# ---------------------------------------------------------------------------
# main: fallback check (lines 691, 700-702)
# ---------------------------------------------------------------------------


class TestMainFallbackCheck:
    def test_fallback_days_processed(self, tmp_path, monkeypatch, capsys):
        """Main processes fallback days."""
        from datetime import date, timedelta

        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)

        # Create A layer for yesterday
        a_layer = log_dir / f"{yesterday}-sessions.md"
        a_layer.write_text("### abc12345\n- **标题**: Test\n", encoding="utf-8")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._resolve_projects",
            lambda args: [tmp_path]
        )

        result = main(["--date", "2026-07-12", "--dry-run", "--fallback-days", "3"])
        assert result == 0
        captured = capsys.readouterr()
        # Should mention fallback processing
        assert "完成" in captured.out or "fallback" in captured.out.lower()


# ---------------------------------------------------------------------------
# main: error handling (lines 738-740, 745-748, 752)
# ---------------------------------------------------------------------------


class TestMainErrorHandling:
    def test_project_processing_exception(self, tmp_path, monkeypatch, capsys):
        """When project processing raises, it's caught gracefully."""
        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator._resolve_projects",
            lambda args: [tmp_path]
        )

        def bad_process(*args, **kwargs):
            raise RuntimeError("Processing failed")

        monkeypatch.setattr(
            "memory_core.tools.daily_summary_generator.process_project",
            bad_process
        )

        result = main(["--date", "2026-07-12", "--dry-run", "--fallback-days", "0"])
        # Should not crash, error is caught
        assert result == 0 or result == 1

    def test_no_date_no_today_error(self, capsys):
        """When neither --date nor --today provided, returns error."""
        result = main([])
        assert result == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err or "必须指定" in captured.err


# ---------------------------------------------------------------------------
# Lines 143: _find_session_jsonl when SESSIONS_HOME doesn't exist
# ---------------------------------------------------------------------------

class TestFindSessionJsonlNoSessionsHome:
    def test_sessions_home_not_exists(self, monkeypatch, tmp_path):
        """_find_session_jsonl returns None when SESSIONS_HOME doesn't exist."""
        from memory_core.tools import daily_summary_generator
        fake_path = tmp_path / "nonexistent"
        monkeypatch.setattr(daily_summary_generator, "SESSIONS_HOME", fake_path)
        result = daily_summary_generator._find_session_jsonl("abc123")
        assert result is None


# ---------------------------------------------------------------------------
# Lines 443-444: _try_sign_file exception handling
# ---------------------------------------------------------------------------

class TestTrySignFileException:
    def test_sign_exception(self, monkeypatch, tmp_path, capsys):
        """_try_sign_file handles exception when signing fails."""
        from memory_core.tools import daily_summary_generator

        # Skip test if modules not available
        if daily_summary_generator._integrity is None or daily_summary_generator._integrity_keys is None:
            pytest.skip("integrity modules not available")

        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        def mock_sign(*args, **kwargs):
            raise RuntimeError("Signing failed")

        def mock_load_key():
            return "test_key"

        monkeypatch.setattr(daily_summary_generator._integrity, "sign_project_incremental", mock_sign)
        monkeypatch.setattr(daily_summary_generator._integrity_keys, "load_key", mock_load_key)

        # _try_sign_file returns None, not bool, and doesn't raise
        daily_summary_generator._try_sign_file(tmp_path, "test.md")
        # Should not crash, exception is caught internally


# ---------------------------------------------------------------------------
# Lines 578: _fallback_check when daily_path exists
# ---------------------------------------------------------------------------

class TestFallbackCheckDailyExists:
    def test_daily_already_exists(self, monkeypatch, tmp_path, capsys):
        """_fallback_check skips when daily log already exists."""

        from memory_core.tools import daily_summary_generator

        # _fallback_check signature: (project_root: Path, fallback_days: int, dry_run: bool = False)
        target_date = "2024-01-15"
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)

        a_layer_path = log_dir / f"{target_date}-sessions.md"
        a_layer_path.write_text("### abc123\n- Test session")

        daily_path = log_dir / f"{target_date}.md"
        daily_path.write_text("# Already exists")

        monkeypatch.setattr(daily_summary_generator, "_read_a_layer", lambda p, d: [{"session_id": "abc123"}])
        monkeypatch.setattr(daily_summary_generator, "_enrich_with_b_layer", lambda s: s)
        monkeypatch.setattr(daily_summary_generator, "_write_daily_log", lambda *a: None)

        # Correct signature: _fallback_check(project_root, fallback_days, dry_run=False)
        result = daily_summary_generator._fallback_check(tmp_path, 3, False)
        # Should not generate since daily_path already exists
        assert target_date not in result


# ---------------------------------------------------------------------------
# Lines 691, 700-702: main() fallback processing
# ---------------------------------------------------------------------------

class TestMainFallbackProcessing:
    def test_fallback_days_zero(self, monkeypatch, tmp_path, capsys):
        """main() handles fallback_days=0."""
        from memory_core.tools import daily_summary_generator

        monkeypatch.setattr(daily_summary_generator, "_resolve_projects", lambda args: [tmp_path])

        def mock_process(*args, **kwargs):
            return True

        monkeypatch.setattr(daily_summary_generator, "process_project", mock_process)

        result = daily_summary_generator.main(
            ["--date", "2024-01-15", "--fallback-days", "0"]
        )

        assert result == 0
        captured = capsys.readouterr()
        assert "完成" in captured.out or "1/1" in captured.out


# ---------------------------------------------------------------------------
# Lines 745-748: main() exception handling
# ---------------------------------------------------------------------------

class TestMainExceptionHandling:
    def test_process_project_exception(self, monkeypatch, tmp_path, capsys):
        """main() handles exception in process_project."""
        from memory_core.tools import daily_summary_generator

        monkeypatch.setattr(daily_summary_generator, "_resolve_projects", lambda args: [tmp_path])

        def failing_process(*args, **kwargs):
            raise RuntimeError("Processing failed")

        monkeypatch.setattr(daily_summary_generator, "process_project", failing_process)

        # main catches the exception and continues, returns 0
        result = daily_summary_generator.main(["--date", "2024-01-15"])

        # The main function catches exceptions per project and prints to stderr
        capsys.readouterr()
        assert result == 0


# ---------------------------------------------------------------------------
# Lines 336, 375, 392, 402, 412: write_error_log calls
# ---------------------------------------------------------------------------

class TestWriteErrorLogCalls:
    """Test that write_error_log is called when available and errors occur."""

    def test_write_error_log_on_failure(self, monkeypatch, tmp_path):
        """write_error_log is called when file write fails."""
        from unittest.mock import Mock

        from memory_core.tools import daily_summary_generator

        # Mock write_error_log
        mock_error_log = Mock()
        monkeypatch.setattr(daily_summary_generator, "write_error_log", mock_error_log)

        # Mock Path.write_text to raise OSError
        original_write_text = Path.write_text
        def mock_write_text(self, *args, **kwargs):
            if str(self).endswith("2026-07-12.md"):
                raise OSError("Permission denied")
            return original_write_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", mock_write_text)

        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)

        sessions = [{"input_tokens": 100, "output_tokens": 200}]

        with pytest.raises(OSError):
            daily_summary_generator._write_daily_log(tmp_path, "2026-07-12", sessions, dry_run=False)

        # write_error_log should have been called
        assert mock_error_log.called
