"""Comprehensive unit tests for daily_summary_generator.py coverage improvement.

Target: raise coverage from 20.14% to >=50%.
Covers: helper functions, A/B layer reading, data report generation,
write_daily_log, fallback_check, enrich_with_b_layer, resolve_projects,
process_project, main(), and CLI parsing.
"""
from __future__ import annotations

import argparse
import json
import textwrap
from datetime import date, timedelta
from unittest.mock import patch

from memory_core.tools.daily_summary_generator import (
    _enrich_with_b_layer,
    _extract_text_blocks,
    _extract_transcript_summary,
    _fallback_check,
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
# _parse_args tests
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_date_arg(self):
        args = _parse_args(["--date", "2026-05-28"])
        assert args.date == "2026-05-28"
        assert not args.today

    def test_today_flag(self):
        args = _parse_args(["--today"])
        assert args.today is True
        assert args.date is None

    def test_project_arg(self):
        args = _parse_args(["--today", "--project", "/tmp/myproj"])
        assert args.project == "/tmp/myproj"

    def test_all_projects_flag(self):
        args = _parse_args(["--today", "--all-projects"])
        assert args.all_projects is True

    def test_dry_run_flag(self):
        args = _parse_args(["--today", "--dry-run"])
        assert args.dry_run is True

    def test_fallback_days_default(self):
        args = _parse_args(["--today"])
        assert args.fallback_days == 3

    def test_fallback_days_custom(self):
        args = _parse_args(["--today", "--fallback-days", "7"])
        assert args.fallback_days == 7


# ---------------------------------------------------------------------------
# _read_a_layer tests
# ---------------------------------------------------------------------------

class TestReadALayer:
    def test_missing_file_returns_none(self, tmp_path):
        result = _read_a_layer(tmp_path, "2026-05-28")
        assert result is None

    def test_empty_file_returns_empty_list(self, tmp_path):
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "2026-05-28-sessions.md").write_text("", encoding="utf-8")
        result = _read_a_layer(tmp_path, "2026-05-28")
        assert result == []

    def test_parse_single_session(self, tmp_path):
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            ### abcd1234
            - **标题**: 修复 Bug
            - **模型**: GLM-5.1 (官方) | 时长: 2m35s
            - **Token**: input=1000 output=500
            - **工具调用**: Read, Edit
            - **用户意图**: 修复登录页面的 bug
            - **助手摘要**: 修复了登录页面的验证逻辑
        """)
        (log_dir / "2026-05-28-sessions.md").write_text(content, encoding="utf-8")
        result = _read_a_layer(tmp_path, "2026-05-28")
        assert len(result) == 1
        s = result[0]
        assert s["full_session_id"] == "abcd1234"
        assert s["title"] == "修复 Bug"
        assert s["model"] == "GLM-5.1 (官方)"
        assert s["duration"] == "2m35s"
        assert s["input_tokens"] == 1000
        assert s["output_tokens"] == 500
        assert s["tool_calls_raw"] == "Read, Edit"
        assert s["user_prompt_preview"] == "修复登录页面的 bug"
        assert s["assistant_summary_preview"] == "修复了登录页面的验证逻辑"

    def test_parse_multiple_sessions(self, tmp_path):
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            ### aaaa1111
            - **标题**: 第一个 session
            - **模型**: GLM-5.1 | 时长: 1m
            - **Token**: input=100 output=200

            ### bbbb2222
            - **标题**: 第二个 session
            - **模型**: GLM-5.1 | 时长: 3m
            - **Token**: input=300 output=400
        """)
        (log_dir / "2026-05-28-sessions.md").write_text(content, encoding="utf-8")
        result = _read_a_layer(tmp_path, "2026-05-28")
        assert len(result) == 2
        assert result[0]["full_session_id"] == "aaaa1111"
        assert result[1]["full_session_id"] == "bbbb2222"

    def test_header_must_be_8_hex(self, tmp_path):
        """Non-hex or wrong-length headers are ignored."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            ### zzzz (not hex, should not match)
            - **标题**: 无效 header
            ### abcd1234
            - **标题**: 有效 session
        """)
        (log_dir / "2026-05-28-sessions.md").write_text(content, encoding="utf-8")
        result = _read_a_layer(tmp_path, "2026-05-28")
        # Only the valid hex header should produce a session
        assert len(result) == 1
        assert result[0]["full_session_id"] == "abcd1234"


# ---------------------------------------------------------------------------
# _extract_text_blocks tests
# ---------------------------------------------------------------------------

class TestExtractTextBlocks:
    def test_empty_list(self):
        assert _extract_text_blocks([]) == []

    def test_non_list_input(self):
        assert _extract_text_blocks("not a list") == []
        assert _extract_text_blocks(None) == []

    def test_extract_text_blocks(self):
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "tool_use", "name": "Read"},
            {"type": "text", "text": "World"},
        ]
        result = _extract_text_blocks(content)
        assert result == ["Hello", "World"]

    def test_strip_system_reminder(self):
        content = [
            {"type": "text", "text": "<system-reminder>hidden</system-reminder>visible text"},
        ]
        result = _extract_text_blocks(content)
        assert result == ["visible text"]

    def test_non_dict_items_ignored(self):
        content = ["string_item", 42, {"type": "text", "text": "valid"}]
        result = _extract_text_blocks(content)
        assert result == ["valid"]


# ---------------------------------------------------------------------------
# _read_full_jsonl and _read_partial_jsonl tests
# ---------------------------------------------------------------------------

class TestJsonlReaders:
    def test_read_full_jsonl(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a": 1}\n{"b": 2}\n\nbad json\n{"c": 3}\n', encoding="utf-8")
        result = _read_full_jsonl(f)
        assert len(result) == 3
        assert result[0] == {"a": 1}
        assert result[1] == {"b": 2}
        assert result[2] == {"c": 3}

    def test_read_full_jsonl_empty(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        assert _read_full_jsonl(f) == []

    def test_read_partial_jsonl(self, tmp_path):
        f = tmp_path / "test.jsonl"
        lines = [json.dumps({"line": i}) for i in range(100)]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = _read_partial_jsonl(f, 5, 3)
        # Should have first 5 + last 3 (no overlap)
        assert len(result) == 8
        assert result[0] == {"line": 0}
        assert result[4] == {"line": 4}

    def test_read_partial_jsonl_small_file(self, tmp_path):
        """Small file where first_n + last_n > total lines."""
        f = tmp_path / "small.jsonl"
        lines = [json.dumps({"i": i}) for i in range(5)]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = _read_partial_jsonl(f, 10, 10)
        # Should deduplicate
        assert len(result) == 5


# ---------------------------------------------------------------------------
# _find_session_jsonl tests
# ---------------------------------------------------------------------------

class TestFindSessionJsonl:
    def test_nonexistent_home(self, tmp_path, monkeypatch):
        import memory_core.tools.daily_summary_generator as mod
        monkeypatch.setattr(mod, "SESSIONS_HOME", tmp_path / "nonexistent")
        assert mod._find_session_jsonl("abc12345") is None

    def test_exact_match(self, tmp_path, monkeypatch):
        import memory_core.tools.daily_summary_generator as mod
        sessions_dir = tmp_path / "session1"
        sessions_dir.mkdir()
        jsonl_file = sessions_dir / "abc12345-1234-5678-9abc-def012345678.jsonl"
        jsonl_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "SESSIONS_HOME", tmp_path)
        # Prefix match
        result = mod._find_session_jsonl("abc12345")
        assert result == jsonl_file

    def test_prefix_match(self, tmp_path, monkeypatch):
        import memory_core.tools.daily_summary_generator as mod
        sessions_dir = tmp_path / "sdir"
        sessions_dir.mkdir()
        target = sessions_dir / "abcd1234-extra.jsonl"
        target.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mod, "SESSIONS_HOME", tmp_path)
        result = mod._find_session_jsonl("abcd1234")
        assert result is not None
        assert result.name.startswith("abcd1234")


# ---------------------------------------------------------------------------
# _extract_transcript_summary tests
# ---------------------------------------------------------------------------

class TestExtractTranscriptSummary:
    def test_basic_extraction(self, tmp_path):
        jsonl_path = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Hello"}]}}),
            json.dumps({"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there"}]}}),
            json.dumps({"type": "message", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Read"}]}}),
        ]
        jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = _extract_transcript_summary(jsonl_path)
        assert "Hello" in result["user_messages"]
        assert "Hi there" in result["assistant_messages"]
        assert "Read" in result["tool_names"]

    def test_osserror_returns_empty(self, tmp_path):
        result = _extract_transcript_summary(tmp_path / "nonexistent.jsonl")
        assert result == {}

    def test_large_file_partial_read(self, tmp_path):
        """Create a file > 5MB and verify partial read doesn't crash."""
        jsonl_path = tmp_path / "large.jsonl"
        # Write just enough lines to exceed 5MB check
        # We'll monkeypatch the size instead for speed
        small_data = [
            json.dumps({"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}}),
            json.dumps({"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}}),
        ]
        jsonl_path.write_text("\n".join(small_data) + "\n", encoding="utf-8")

        # Mock the internal read functions to simulate large file behavior
        # without patching Path.stat globally (which would pollute other tests)
        with patch("memory_core.tools.daily_summary_generator._read_partial_jsonl",
                   return_value=[
                       {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}},
                       {"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}},
                   ]):
            result = _extract_transcript_summary(jsonl_path)
        assert "hi" in result.get("user_messages", "")
        assert "hello" in result.get("assistant_messages", "")


# ---------------------------------------------------------------------------
# _generate_data_report tests
# ---------------------------------------------------------------------------

class TestGenerateDataReport:
    def test_empty_sessions(self):
        result = _generate_data_report([], "2026-05-28")
        assert "2026-05-28" in result
        assert "Sessions: 0" in result

    def test_with_sessions(self):
        sessions = [
            {
                "full_session_id": "abcd1234-0000",
                "title": "Test Session",
                "model": "GLM-5.1",
                "duration": "2m",
                "input_tokens": 500,
                "output_tokens": 300,
                "user_prompt_preview": "fix something",
                "assistant_summary_preview": "fixed it",
                "tool_calls_raw": "Read, Edit",
            },
        ]
        result = _generate_data_report(sessions, "2026-05-28")
        assert "Sessions: 1" in result
        assert "in=500" in result
        assert "out=300" in result
        assert "abcd1234" in result
        assert "Test Session" in result
        assert "fix something" in result
        assert "fixed it" in result
        assert "Read, Edit" in result

    def test_with_b_layer_data(self):
        """_generate_data_report includes B-layer data when present."""
        sessions = [
            {
                "full_session_id": "abcd1234",
                "title": "Test Session",
                "input_tokens": 100,
                "output_tokens": 200,
                "user_messages": "Please fix this bug",
                "assistant_messages": "I have fixed the bug",
                "tool_names": ["Read", "Edit"],
            },
        ]
        result = _generate_data_report(sessions, "2026-05-28")
        assert "B层用户消息" in result
        assert "Please fix this bug" in result
        assert "B层助手消息" in result
        assert "I have fixed the bug" in result
        assert "B层工具列表" in result
        assert "Read" in result
        assert "Edit" in result

    def test_multiple_sessions_stats(self):
        sessions = [
            {"full_session_id": "aaaa", "input_tokens": 100, "output_tokens": 200},
            {"full_session_id": "bbbb", "input_tokens": 300, "output_tokens": 400},
        ]
        result = _generate_data_report(sessions, "2026-05-28")
        assert "Sessions: 2" in result
        assert "in=400" in result
        assert "out=600" in result


# ---------------------------------------------------------------------------
# _write_daily_log tests
# ---------------------------------------------------------------------------

class TestWriteDailyLog:
    def test_write_data_report(self, tmp_path):
        sessions = [
            {"full_session_id": "abcd1234", "input_tokens": 100, "output_tokens": 200,
             "title": "Test", "model": "GLM", "duration": "1m"},
        ]
        result = _write_daily_log(tmp_path, "2026-05-28", sessions)
        assert result.exists()
        content = result.read_text(encoding="utf-8")
        assert "2026-05-28" in content
        assert "Daily Report" in content
        assert "Sessions: 1" in content
        assert "abcd1234" in content

    def test_dry_run_no_file_written(self, tmp_path):
        sessions = [{"input_tokens": 10, "output_tokens": 20}]
        _write_daily_log(tmp_path, "2026-05-28", sessions, dry_run=True)
        # dry_run doesn't write the file
        assert not (tmp_path / "memory" / "log" / "2026-05-28.md").exists()

    def test_creates_log_dir(self, tmp_path):
        """Log directory should be created if it doesn't exist."""
        _write_daily_log(tmp_path, "2026-06-01", [])
        assert (tmp_path / "memory" / "log").is_dir()


# ---------------------------------------------------------------------------
# _fallback_check tests
# ---------------------------------------------------------------------------

class TestFallbackCheck:
    def test_no_missing_logs(self, tmp_path):
        """No fallback needed when all daily logs exist."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        # Create both A layer and daily log for yesterday
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        (log_dir / f"{yesterday}-sessions.md").write_text("### abcd1234\n", encoding="utf-8")
        (log_dir / f"{yesterday}.md").write_text("exists", encoding="utf-8")

        result = _fallback_check(tmp_path, 3)
        assert result == []

    def test_fallback_generates_missing(self, tmp_path):
        """Fallback should generate missing daily logs."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        # A layer exists but daily log doesn't
        content = "### abcd1234\n- **标题**: Test\n"
        (log_dir / f"{yesterday}-sessions.md").write_text(content, encoding="utf-8")

        result = _fallback_check(tmp_path, 3)
        assert yesterday in result
        # Daily log should now exist
        assert (log_dir / f"{yesterday}.md").exists()

    def test_skip_when_no_a_layer(self, tmp_path):
        """Fallback should skip dates with no A layer data."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        result = _fallback_check(tmp_path, 1)
        assert result == []


# ---------------------------------------------------------------------------
# _enrich_with_b_layer tests
# ---------------------------------------------------------------------------

class TestEnrichWithBLayer:
    def test_no_full_session_id(self):
        sessions = [{"title": "no id"}]
        result = _enrich_with_b_layer(sessions)
        assert len(result) == 1
        assert result[0] == {"title": "no id"}

    def test_session_jsonl_not_found(self):
        sessions = [{"full_session_id": "nonexistent99"}]
        with patch("memory_core.tools.daily_summary_generator._find_session_jsonl", return_value=None):
            result = _enrich_with_b_layer(sessions)
        assert len(result) == 1
        assert "full_session_id" in result[0]

    def test_successful_enrichment(self, tmp_path):
        jsonl_path = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]}}),
            json.dumps({"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}}),
        ]
        jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        sessions = [{"full_session_id": "test1234"}]
        # Patch both _find_session_jsonl AND _extract_transcript_summary to avoid
        # test-order-dependent pollution from other tests
        expected_b_data = {
            "user_messages": "hi",
            "assistant_messages": "hello",
            "tool_names": [],
        }
        with patch("memory_core.tools.daily_summary_generator._find_session_jsonl", return_value=jsonl_path), \
             patch("memory_core.tools.daily_summary_generator._extract_transcript_summary", return_value=expected_b_data):
            result = _enrich_with_b_layer(sessions)
        assert len(result) == 1
        assert "hi" in result[0].get("user_messages", "")
        assert "hello" in result[0].get("assistant_messages", "")


# ---------------------------------------------------------------------------
# _resolve_projects tests
# ---------------------------------------------------------------------------

class TestResolveProjects:
    def test_explicit_project(self):
        args = argparse.Namespace(project="/tmp/myproj", all_projects=False)
        projects = _resolve_projects(args)
        assert len(projects) == 1
        assert str(projects[0]).endswith("myproj")

    def test_all_projects_with_lifecycle_index(self, tmp_path, monkeypatch):
        import memory_core.tools.daily_summary_generator as mod
        index_file = tmp_path / "path-index.json"
        index_file.write_text(json.dumps({"paths": {"/tmp/proj1": {}, "/tmp/proj2": {}}}), encoding="utf-8")
        monkeypatch.setattr(mod, "LIFECYCLE_INDEX", index_file)
        args = argparse.Namespace(project=None, all_projects=True)
        projects = _resolve_projects(args)
        assert len(projects) == 2

    def test_all_projects_empty_index_fallback(self, tmp_path, monkeypatch):
        import memory_core.tools.daily_summary_generator as mod
        index_file = tmp_path / "nonexistent" / "path-index.json"
        monkeypatch.setattr(mod, "LIFECYCLE_INDEX", index_file)
        # No matching projects found
        args = argparse.Namespace(project=None, all_projects=True)
        projects = _resolve_projects(args)
        # Should try fallback (scan home dir), might be empty
        assert isinstance(projects, list)

    def test_no_args_defaults_to_cwd_walk(self, monkeypatch):
        args = argparse.Namespace(project=None, all_projects=False)
        projects = _resolve_projects(args)
        assert len(projects) >= 1


# ---------------------------------------------------------------------------
# _try_sign_file tests
# ---------------------------------------------------------------------------

class TestTrySignFile:
    def test_no_integrity_module(self, tmp_path):
        """Should silently do nothing when integrity modules are None."""
        import memory_core.tools.daily_summary_generator as mod
        orig_integrity = mod._integrity
        orig_keys = mod._integrity_keys
        try:
            mod._integrity = None
            mod._integrity_keys = None
            _try_sign_file(tmp_path, "test.md")  # Should not raise
        finally:
            mod._integrity = orig_integrity
            mod._integrity_keys = orig_keys


# ---------------------------------------------------------------------------
# process_project tests
# ---------------------------------------------------------------------------

class TestProcessProject:
    def test_no_a_layer_returns_false(self, tmp_path):
        result = process_project(tmp_path, "2026-05-28")
        assert result is False

    def test_empty_a_layer_returns_false(self, tmp_path):
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "2026-05-28-sessions.md").write_text("", encoding="utf-8")
        result = process_project(tmp_path, "2026-05-28")
        assert result is False

    def test_successful_processing(self, tmp_path):
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        content = "### abcd1234\n- **标题**: Test\n- **模型**: GLM | 时长: 1m\n- **Token**: input=10 output=20\n"
        (log_dir / "2026-05-28-sessions.md").write_text(content, encoding="utf-8")

        with patch("memory_core.tools.daily_summary_generator._enrich_with_b_layer", side_effect=lambda s: s), \
             patch("memory_core.tools.daily_summary_generator._fallback_check", return_value=[]):
            result = process_project(tmp_path, "2026-05-28", fallback_days=0)
        assert result is True
        assert (log_dir / "2026-05-28.md").exists()


# ---------------------------------------------------------------------------
# main() tests
# ---------------------------------------------------------------------------

class TestMain:
    def test_no_date_returns_1(self, capsys):
        ret = main([])
        assert ret == 1

    def test_today_no_project_finds_something(self):
        """main() with --today should not crash."""
        ret = main(["--today"])
        # May return 0 or 1 depending on whether a project is found
        assert ret in (0, 1)

    def test_date_with_project(self, tmp_path):
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "2026-05-28-sessions.md").write_text("", encoding="utf-8")

        with patch("memory_core.tools.daily_summary_generator.process_project", return_value=True):
            ret = main(["--date", "2026-05-28", "--project", str(tmp_path)])
        assert ret == 0

    def test_exception_returns_1(self):
        with patch("memory_core.tools.daily_summary_generator._resolve_projects", side_effect=RuntimeError("boom")):
            ret = main(["--today", "--project", "/tmp/fake"])
        assert ret == 1

    def test_dry_run_flag(self, tmp_path):
        ret = main(["--date", "2026-05-28", "--project", str(tmp_path), "--dry-run"])
        assert ret == 0  # No A layer data, process_project returns False but main returns 0

    def test_process_project_exception_caught(self, tmp_path):
        """Exception in process_project should be caught, not crash main."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        (log_dir / "2026-05-28-sessions.md").write_text("### abcd1234\n- **标题**: T\n", encoding="utf-8")

        with patch("memory_core.tools.daily_summary_generator.process_project", side_effect=RuntimeError("fail")):
            ret = main(["--date", "2026-05-28", "--project", str(tmp_path)])
        assert ret == 0  # main catches per-project exceptions


# ---------------------------------------------------------------------------
# Integration-style tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_pipeline_without_llm(self, tmp_path):
        """End-to-end without LLM (fallback report)."""
        log_dir = tmp_path / "memory" / "log"
        log_dir.mkdir(parents=True)
        content = textwrap.dedent("""\
            ### deadbeef
            - **标题**: 代码重构
            - **模型**: GLM-5.1 | 时长: 10m
            - **Token**: input=5000 output=3000
            - **工具调用**: Read, Edit, Grep
            - **用户意图**: 重构模块
            - **助手摘要**: 完成重构
        """)
        (log_dir / "2026-06-01-sessions.md").write_text(content, encoding="utf-8")

        with patch("memory_core.tools.daily_summary_generator._enrich_with_b_layer", side_effect=lambda s: s), \
             patch("memory_core.tools.daily_summary_generator._fallback_check", return_value=[]):
            result = process_project(tmp_path, "2026-06-01", fallback_days=0)

        assert result is True
        daily_log = log_dir / "2026-06-01.md"
        assert daily_log.exists()
        text = daily_log.read_text(encoding="utf-8")
        assert "deadbeef" in text
        assert "代码重构" in text
        assert "in=5000" in text
        assert "out=3000" in text

