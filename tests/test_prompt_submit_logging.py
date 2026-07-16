"""Tests for F4: PromptSubmit real-time logging.

Covers:
- VAL-F4-001: Heartbeat entry format
- VAL-F4-002: User message preview in entry body
- VAL-F4-003: Cumulative prompt count
- VAL-F4-004: fcntl.flock exclusive lock on write
- VAL-F4-005: SIGALRM timeout protection
- VAL-F4-006: Missing prompt field graceful fallback
- VAL-F4-007: Cross-day session writes to correct date file
- VAL-F4-008: Factory payload fields consumed correctly
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest  # noqa: F401 - needed for tmp_path fixture

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_log_prompt_submit():
    """Import the function under test, handling relative imports."""
    try:
        from memory_core.tools.memory_hook_gateway import _log_prompt_submit
        return _log_prompt_submit
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from memory_core.tools.memory_hook_gateway import _log_prompt_submit
        return _log_prompt_submit


def _import_read_last_user_message():
    """Import the transcript reader helper."""
    try:
        from memory_core.tools.memory_hook_gateway import _read_last_user_message_from_transcript
        return _read_last_user_message_from_transcript
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from memory_core.tools.memory_hook_gateway import _read_last_user_message_from_transcript
        return _read_last_user_message_from_transcript


HEARTBEAT_HEADER_RE = re.compile(
    r"^#### \d{2}:\d{2}:\d{2} — [\w\-]{1,8} \[heartbeat\]"
)


def _parse_heartbeat_blocks(text: str) -> list[dict]:
    """Parse heartbeat blocks from a sessions.md file."""
    blocks: list[dict] = []
    for block in text.split("---"):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if not lines or not HEARTBEAT_HEADER_RE.match(lines[0]):
            continue
        header = lines[0]
        body = "\n".join(lines[1:])
        ts_match = re.match(r"#### (\d{2}:\d{2}:\d{2}) — ([\w\-]+)", header)
        msg_match = re.search(r"\*\*用户消息\*\*: (.+)", body)
        count_match = re.search(r"\*\*累计 prompt 数\*\*: (\d+)", body)
        blocks.append({
            "header": header,
            "timestamp": ts_match.group(1) if ts_match else None,
            "session_prefix": ts_match.group(2) if ts_match else None,
            "message": msg_match.group(1) if msg_match else None,
            "count": int(count_match.group(1)) if count_match else None,
        })
    return blocks


# ---------------------------------------------------------------------------
# VAL-F4-001: Heartbeat entry format
# ---------------------------------------------------------------------------

class TestHeartbeatFormat:
    """Test heartbeat entry format matches the spec."""

    def test_heartbeat_header_format(self, tmp_path: Path):
        """Header must be: #### {HH:MM:SS} — {session_id[:8]} [heartbeat]."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        payload = {
            "session_id": "abc12345-6789-0abc",
            "prompt": "Hello world",
        }
        log_fn(project_root, payload)

        log_dir = project_root / "memory" / "log"
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"{today}-sessions.md"
        assert log_file.exists()

        content = log_file.read_text()
        blocks = _parse_heartbeat_blocks(content)
        assert len(blocks) == 1
        assert HEARTBEAT_HEADER_RE.match(blocks[0]["header"])
        assert blocks[0]["session_prefix"] == "abc12345"

    def test_heartbeat_has_separator(self, tmp_path: Path):
        """Each heartbeat block must end with --- separator."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        payload = {"session_id": "sess001", "prompt": "test"}
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        content = log_file.read_text()
        assert content.rstrip().endswith("---")


# ---------------------------------------------------------------------------
# VAL-F4-002: User message preview in entry body
# ---------------------------------------------------------------------------

class TestUserMessagePreview:
    """Test user message is truncated to 100 characters."""

    def test_short_prompt_shows_full(self, tmp_path: Path):
        """Short prompts show entirely in the preview."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        prompt = "Write a function to add two numbers"
        payload = {"session_id": "sess001", "prompt": prompt}
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        blocks = _parse_heartbeat_blocks(log_file.read_text())
        assert blocks[0]["message"] == prompt

    def test_long_prompt_truncated_to_100(self, tmp_path: Path):
        """Prompts longer than 100 chars are truncated."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        prompt = "x" * 200
        payload = {"session_id": "sess001", "prompt": prompt}
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        blocks = _parse_heartbeat_blocks(log_file.read_text())
        assert blocks[0]["message"] == "x" * 100
        assert len(blocks[0]["message"]) == 100


# ---------------------------------------------------------------------------
# VAL-F4-003: Cumulative prompt count
# ---------------------------------------------------------------------------

class TestCumulativePromptCount:
    """Test that prompt count increments monotonically per session."""

    def test_first_event_is_count_1(self, tmp_path: Path):
        """First prompt-submit for a session should have count 1."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        payload = {"session_id": "sess-001", "prompt": "first"}
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        blocks = _parse_heartbeat_blocks(log_file.read_text())
        assert blocks[0]["count"] == 1

    def test_count_increments_for_same_session(self, tmp_path: Path):
        """Multiple events for same session increment count."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        sid = "sess-001"

        log_fn(project_root, {"session_id": sid, "prompt": "first"})
        log_fn(project_root, {"session_id": sid, "prompt": "second"})
        log_fn(project_root, {"session_id": sid, "prompt": "third"})

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        blocks = _parse_heartbeat_blocks(log_file.read_text())
        assert len(blocks) == 3
        assert blocks[0]["count"] == 1
        assert blocks[1]["count"] == 2
        assert blocks[2]["count"] == 3

    def test_count_resets_for_new_session(self, tmp_path: Path):
        """New session_id should start count at 1."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path

        log_fn(project_root, {"session_id": "sess-aaa", "prompt": "a"})
        log_fn(project_root, {"session_id": "sess-aaa", "prompt": "b"})
        log_fn(project_root, {"session_id": "sess-bbb", "prompt": "c"})

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        blocks = _parse_heartbeat_blocks(log_file.read_text())
        assert len(blocks) == 3
        assert blocks[0]["count"] == 1
        assert blocks[1]["count"] == 2
        assert blocks[2]["count"] == 1  # new session


# ---------------------------------------------------------------------------
# VAL-F4-004: fcntl.flock exclusive lock on write
# ---------------------------------------------------------------------------

class TestFileLock:
    """Test that exclusive_lock is used for exclusive locking."""

    def test_source_uses_exclusive_lock(self):
        """Source code must use exclusive_lock for file locking."""
        import inspect
        log_fn = _import_log_prompt_submit()
        source = inspect.getsource(log_fn)
        assert "exclusive_lock" in source

    def test_source_uses_with_statement(self):
        """exclusive_lock should be used in a with statement."""
        import inspect
        log_fn = _import_log_prompt_submit()
        source = inspect.getsource(log_fn)
        assert "with" in source
        assert "exclusive_lock" in source


# ---------------------------------------------------------------------------
# VAL-F4-005: SIGALRM timeout protection
# ---------------------------------------------------------------------------

class TestTimeoutProtection:
    """Test 2-second SIGALRM timeout."""

    def test_source_sets_alarm(self):
        """Source code must set SIGALRM."""
        import inspect
        log_fn = _import_log_prompt_submit()
        source = inspect.getsource(log_fn)
        assert "signal.alarm" in source or "SIGALRM" in source

    def test_source_restores_handler(self):
        """Source code must restore old signal handler."""
        import inspect
        log_fn = _import_log_prompt_submit()
        source = inspect.getsource(log_fn)
        assert "signal.signal" in source


# ---------------------------------------------------------------------------
# VAL-F4-006: Missing prompt field graceful fallback
# ---------------------------------------------------------------------------

class TestMissingPromptFallback:
    """Test fallback when payload lacks prompt field."""

    def test_no_prompt_uses_transcript(self, tmp_path: Path):
        """When payload lacks prompt, read from transcript_path."""
        log_fn = _import_log_prompt_submit()

        # Create a transcript file
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            json.dumps({"role": "user", "content": "transcript message"}) + "\n"
        )

        project_root = tmp_path / "project"
        project_root.mkdir()

        payload = {
            "session_id": "sess001",
            "transcript_path": str(transcript),
        }
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        blocks = _parse_heartbeat_blocks(log_file.read_text())
        assert "transcript message" in blocks[0]["message"]

    def test_no_prompt_no_transcript_fallback_text(self, tmp_path: Path):
        """When no prompt and no transcript, write fallback text."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        payload = {"session_id": "sess001"}
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        content = log_file.read_text()
        assert "no prompt captured" in content

    def test_transcript_reader_returns_last_user(self, tmp_path: Path):
        """Transcript reader returns the last user message."""
        reader = _import_read_last_user_message()
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            json.dumps({"role": "assistant", "content": "hi"}) + "\n"
            + json.dumps({"role": "user", "content": "msg1"}) + "\n"
            + json.dumps({"role": "assistant", "content": "bye"}) + "\n"
            + json.dumps({"role": "user", "content": "msg2"}) + "\n"
        )
        result = reader(str(transcript))
        assert result == "msg2"

    def test_transcript_reader_returns_none_for_no_user(self, tmp_path: Path):
        """Transcript reader returns None if no user messages."""
        reader = _import_read_last_user_message()
        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            json.dumps({"role": "assistant", "content": "hi"}) + "\n"
        )
        result = reader(str(transcript))
        assert result is None

    def test_transcript_reader_returns_none_for_missing_file(self, tmp_path: Path):
        """Transcript reader returns None for non-existent file."""
        reader = _import_read_last_user_message()
        result = reader(str(tmp_path / "nonexistent.jsonl"))
        assert result is None

    def test_transcript_reader_returns_none_for_empty_path(self, tmp_path: Path):
        """Transcript reader returns None for None/empty path."""
        reader = _import_read_last_user_message()
        assert reader(None) is None
        assert reader("") is None


# ---------------------------------------------------------------------------
# VAL-F4-007: Cross-day session writes to correct date file
# ---------------------------------------------------------------------------

class TestCrossDaySession:
    """Test that midnight crossover writes to correct date file."""

    @staticmethod
    def _make_fixed_datetime(dt: datetime):
        """Create a datetime subclass whose .now() returns a fixed time."""
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(
                    dt.year, dt.month, dt.day,
                    dt.hour, dt.minute, dt.second,
                )

            def astimezone(self, tz=None):
                return self

        return FixedDatetime

    def test_writes_to_date_specific_file(self, tmp_path: Path):
        """Events write to file matching the current date."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path

        fixed_time = datetime(2025, 6, 15, 10, 30, 0)
        FixedDt = self._make_fixed_datetime(fixed_time)

        with patch("memory_core.tools.memory_hook_gateway.datetime", FixedDt):
            log_fn(project_root, {"session_id": "sess001", "prompt": "day1"})

        log_file1 = project_root / "memory" / "log" / "2025-06-15-sessions.md"
        assert log_file1.exists()

    def test_second_event_after_midnight_new_file(self, tmp_path: Path):
        """After midnight, a new date file is created."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path

        time_1 = datetime(2025, 1, 15, 23, 59, 50)
        FixedDt1 = self._make_fixed_datetime(time_1)

        with patch("memory_core.tools.memory_hook_gateway.datetime", FixedDt1):
            log_fn(project_root, {"session_id": "sess001", "prompt": "before midnight"})

        time_2 = datetime(2025, 1, 16, 0, 1, 0)
        FixedDt2 = self._make_fixed_datetime(time_2)

        with patch("memory_core.tools.memory_hook_gateway.datetime", FixedDt2):
            log_fn(project_root, {"session_id": "sess001", "prompt": "after midnight"})

        log_file_d1 = project_root / "memory" / "log" / "2025-01-15-sessions.md"
        log_file_d2 = project_root / "memory" / "log" / "2025-01-16-sessions.md"

        assert log_file_d1.exists()
        assert log_file_d2.exists()

        # D1 has 1 entry, D2 has 1 entry
        blocks_d1 = _parse_heartbeat_blocks(log_file_d1.read_text())
        blocks_d2 = _parse_heartbeat_blocks(log_file_d2.read_text())
        assert len(blocks_d1) == 1
        assert len(blocks_d2) == 1


# ---------------------------------------------------------------------------
# VAL-F4-008: Factory payload fields consumed correctly
# ---------------------------------------------------------------------------

class TestFactoryPayload:
    """Test full Factory payload is handled correctly."""

    def test_full_payload_processed(self, tmp_path: Path):
        """Complete Factory payload with all fields works without error."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        payload = {
            "session_id": "factory-session-abc123",
            "prompt": "Please review the code",
            "cwd": str(tmp_path),
            "transcript_path": str(tmp_path / "transcript.jsonl"),
            "surface_id": "cmux-surface-001",
            "workspace_id": "ws-001",
            "extra_field": "should be ignored",
        }
        # Should not raise
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        assert log_file.exists()

        blocks = _parse_heartbeat_blocks(log_file.read_text())
        assert len(blocks) == 1
        assert blocks[0]["session_prefix"] == "factory-"
        assert "Please review the code" in blocks[0]["message"]

    def test_session_id_truncated_to_8_chars(self, tmp_path: Path):
        """Session ID prefix in heartbeat is first 8 chars."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        payload = {"session_id": "abcdefgh-1234-5678", "prompt": "test"}
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        content = log_file.read_text()
        assert "abcdefgh" in content

    def test_empty_prompt_uses_fallback(self, tmp_path: Path):
        """Empty string prompt should be treated as missing."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        payload = {"session_id": "sess001", "prompt": ""}
        log_fn(project_root, payload)

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = project_root / "memory" / "log" / f"{today}-sessions.md"
        content = log_file.read_text()
        assert "no prompt captured" in content

    def test_creates_log_directory_if_missing(self, tmp_path: Path):
        """Log directory is created if it doesn't exist."""
        log_fn = _import_log_prompt_submit()
        project_root = tmp_path
        payload = {"session_id": "sess001", "prompt": "test"}
        log_fn(project_root, payload)

        log_dir = project_root / "memory" / "log"
        assert log_dir.exists()
        assert log_dir.is_dir()
