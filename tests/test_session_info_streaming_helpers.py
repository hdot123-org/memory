"""Tests for _extract_session_info_streaming helper functions.

This test file covers the 5 helpers extracted from _extract_session_info_streaming:
- _parse_jsonl_timestamp
- _extract_first_user_preview
- _extract_assistant_summary_preview
- _collect_tool_uses
- _build_session_info_dict

These tests establish behavior baseline BEFORE refactoring.
"""

from collections import Counter
from datetime import datetime


class TestParseJsonlTimestamp:
    """Tests for _parse_jsonl_timestamp helper."""

    def test_valid_iso_timestamp(self):
        """Should parse valid ISO 8601 timestamp."""
        from memory_core.tools.session_end_logger import _parse_jsonl_timestamp

        ts = "2024-01-15T10:30:45.123456"
        result = _parse_jsonl_timestamp(ts)
        assert result is not None
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_z_suffix_timestamp(self):
        """Should parse timestamp with Z suffix (UTC)."""
        from memory_core.tools.session_end_logger import _parse_jsonl_timestamp

        ts = "2024-01-15T10:30:45Z"
        result = _parse_jsonl_timestamp(ts)
        assert result is not None
        assert isinstance(result, datetime)

    def test_empty_string(self):
        """Should return None for empty string."""
        from memory_core.tools.session_end_logger import _parse_jsonl_timestamp

        result = _parse_jsonl_timestamp("")
        assert result is None

    def test_invalid_timestamp(self):
        """Should return None for invalid timestamp."""
        from memory_core.tools.session_end_logger import _parse_jsonl_timestamp

        result = _parse_jsonl_timestamp("not-a-timestamp")
        assert result is None

    def test_none_value(self):
        """Should return None for None input."""
        from memory_core.tools.session_end_logger import _parse_jsonl_timestamp

        result = _parse_jsonl_timestamp(None)
        assert result is None


class TestExtractFirstUserPreview:
    """Tests for _extract_first_user_preview helper."""

    def test_simple_text_content(self):
        """Should extract text from simple content block."""
        from memory_core.tools.session_end_logger import _extract_first_user_preview

        msg = {
            "content": [
                {"type": "text", "text": "Hello, how are you?"}
            ]
        }
        result = _extract_first_user_preview(msg)
        assert result == "Hello, how are you?"

    def test_long_text_truncated(self):
        """Should truncate long text to 200 chars + '...'."""
        from memory_core.tools.session_end_logger import _extract_first_user_preview

        long_text = "A" * 250
        msg = {"content": [{"type": "text", "text": long_text}]}
        result = _extract_first_user_preview(msg)
        assert len(result) == 203  # 200 + "..."
        assert result.endswith("...")

    def test_system_reminder_stripped(self):
        """Should strip system-reminder from text."""
        from memory_core.tools.session_end_logger import _extract_first_user_preview

        msg = {
            "content": [
                {
                    "type": "text",
                    "text": "<system-reminder>Ignore this</system-reminder>Actual user message"
                }
            ]
        }
        result = _extract_first_user_preview(msg)
        assert result == "Actual user message"
        assert "<system-reminder>" not in result

    def test_empty_content(self):
        """Should return empty string for empty content."""
        from memory_core.tools.session_end_logger import _extract_first_user_preview

        msg = {"content": []}
        result = _extract_first_user_preview(msg)
        assert result == ""

    def test_none_message(self):
        """Should return empty string for None message."""
        from memory_core.tools.session_end_logger import _extract_first_user_preview

        result = _extract_first_user_preview(None)
        assert result == ""

    def test_non_list_content(self):
        """Should return empty string for non-list content."""
        from memory_core.tools.session_end_logger import _extract_first_user_preview

        msg = {"content": "string content"}
        result = _extract_first_user_preview(msg)
        assert result == ""


class TestExtractAssistantSummaryPreview:
    """Tests for _extract_assistant_summary_preview helper."""

    def test_simple_text_content(self):
        """Should extract text from simple content block."""
        from memory_core.tools.session_end_logger import _extract_assistant_summary_preview

        msg = {
            "content": [
                {"type": "text", "text": "I've completed the task successfully."}
            ]
        }
        result = _extract_assistant_summary_preview(msg)
        assert result == "I've completed the task successfully."

    def test_long_text_truncated(self):
        """Should truncate long text to 300 chars + '...'."""
        from memory_core.tools.session_end_logger import _extract_assistant_summary_preview

        long_text = "B" * 350
        msg = {"content": [{"type": "text", "text": long_text}]}
        result = _extract_assistant_summary_preview(msg)
        assert len(result) == 303  # 300 + "..."
        assert result.endswith("...")

    def test_empty_content(self):
        """Should return empty string for empty content."""
        from memory_core.tools.session_end_logger import _extract_assistant_summary_preview

        msg = {"content": []}
        result = _extract_assistant_summary_preview(msg)
        assert result == ""

    def test_none_message(self):
        """Should return empty string for None message."""
        from memory_core.tools.session_end_logger import _extract_assistant_summary_preview

        result = _extract_assistant_summary_preview(None)
        assert result == ""


class TestCollectToolUses:
    """Tests for _collect_tool_uses helper."""

    def test_single_tool_use(self):
        """Should count single tool use."""
        from memory_core.tools.session_end_logger import _collect_tool_uses

        content = [
            {"type": "tool_use", "name": "Read", "input": {}}
        ]
        counter, total = _collect_tool_uses(content)
        assert counter == Counter({"Read": 1})
        assert total == 1

    def test_multiple_tool_uses(self):
        """Should count multiple tool uses."""
        from memory_core.tools.session_end_logger import _collect_tool_uses

        content = [
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "tool_use", "name": "Write", "input": {}},
            {"type": "tool_use", "name": "Read", "input": {}},
        ]
        counter, total = _collect_tool_uses(content)
        assert counter == Counter({"Read": 2, "Write": 1})
        assert total == 3

    def test_mixed_content_blocks(self):
        """Should only count tool_use blocks, ignore others."""
        from memory_core.tools.session_end_logger import _collect_tool_uses

        content = [
            {"type": "text", "text": "I'll help you"},
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "thinking", "text": "Let me think"},
        ]
        counter, total = _collect_tool_uses(content)
        assert counter == Counter({"Read": 1})
        assert total == 1

    def test_empty_content(self):
        """Should return empty counter for empty content."""
        from memory_core.tools.session_end_logger import _collect_tool_uses

        counter, total = _collect_tool_uses([])
        assert counter == Counter()
        assert total == 0

    def test_none_content(self):
        """Should return empty counter for None content."""
        from memory_core.tools.session_end_logger import _collect_tool_uses

        counter, total = _collect_tool_uses(None)
        assert counter == Counter()
        assert total == 0

    def test_missing_name_field(self):
        """Should use 'Unknown' for tool_use without name."""
        from memory_core.tools.session_end_logger import _collect_tool_uses

        content = [
            {"type": "tool_use", "input": {}}
        ]
        counter, total = _collect_tool_uses(content)
        assert counter == Counter({"Unknown": 1})
        assert total == 1


class TestBuildSessionInfoDict:
    """Tests for _build_session_info_dict helper."""

    def test_complete_session_info(self):
        """Should build complete session info dict with all fields."""
        from memory_core.tools.session_end_logger import _build_session_info_dict

        result = _build_session_info_dict(
            session_id="abc12345-def6-7890-abcd-ef1234567890",
            title="Test Session",
            model="claude-3-opus",
            start_time=datetime(2024, 1, 15, 10, 0, 0),
            end_time=datetime(2024, 1, 15, 10, 30, 0),
            user_prompt_preview="Help me with code",
            assistant_summary_preview="I've fixed the bug",
            tool_calls=Counter({"Read": 5, "Write": 2}),
            total_tool_calls=7,
            settings={"model": "claude-3-opus", "inclusiveTokenUsage": {"inputTokens": 1000, "outputTokens": 500}},
        )

        assert result["session_id"] == "abc12345"
        assert result["full_session_id"] == "abc12345-def6-7890-abcd-ef1234567890"
        assert result["title"] == "Test Session"
        assert result["model"] == "claude-3-opus"
        assert result["duration"] == "30m0s"
        assert result["duration_seconds"] == 1800
        assert result["input_tokens"] == 1000
        assert result["output_tokens"] == 500
        assert result["tool_calls"] == {"Read": 5, "Write": 2}
        assert result["total_tool_calls"] == 7
        assert result["user_prompt_preview"] == "Help me with code"
        assert result["assistant_summary_preview"] == "I've fixed the bug"

    def test_short_session_id_truncation(self):
        """Should truncate session_id to first 8 chars."""
        from memory_core.tools.session_end_logger import _build_session_info_dict

        result = _build_session_info_dict(
            session_id="short",
            title="",
            model="unknown",
            start_time=None,
            end_time=None,
            user_prompt_preview="",
            assistant_summary_preview="",
            tool_calls=Counter(),
            total_tool_calls=0,
            settings={},
        )
        assert result["session_id"] == "short"  # shorter than 8, kept as-is
        assert result["full_session_id"] == "short"

    def test_no_duration(self):
        """Should handle missing start/end time."""
        from memory_core.tools.session_end_logger import _build_session_info_dict

        result = _build_session_info_dict(
            session_id="abc12345",
            title="",
            model="unknown",
            start_time=None,
            end_time=None,
            user_prompt_preview="",
            assistant_summary_preview="",
            tool_calls=Counter(),
            total_tool_calls=0,
            settings={},
        )
        assert result["duration"] == "0s"
        assert result["duration_seconds"] == 0

    def test_token_usage_fallback(self):
        """Should fallback to tokenUsage if inclusiveTokenUsage missing."""
        from memory_core.tools.session_end_logger import _build_session_info_dict

        result = _build_session_info_dict(
            session_id="abc12345",
            title="",
            model="unknown",
            start_time=None,
            end_time=None,
            user_prompt_preview="",
            assistant_summary_preview="",
            tool_calls=Counter(),
            total_tool_calls=0,
            settings={"tokenUsage": {"inputTokens": 100, "outputTokens": 50}},
        )
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50

    def test_empty_tool_calls_dict(self):
        """Should return empty dict for tool_calls."""
        from memory_core.tools.session_end_logger import _build_session_info_dict

        result = _build_session_info_dict(
            session_id="abc12345",
            title="",
            model="unknown",
            start_time=None,
            end_time=None,
            user_prompt_preview="",
            assistant_summary_preview="",
            tool_calls=Counter(),
            total_tool_calls=0,
            settings={},
        )
        assert result["tool_calls"] == {}
        assert result["total_tool_calls"] == 0
