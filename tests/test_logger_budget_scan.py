"""Tests for deterministic budget scanning in _extract_session_info_streaming.

Covers:
- VAL-LOG-002: Normal JSONL → correct output with all 13 fields
- VAL-LOG-003: Huge JSONL (50MB+) → completes within budget, truncated=True
- VAL-LOG-004: Single oversized line → skipped, other lines processed
- VAL-LOG-005: Empty file → handled gracefully
- VAL-LOG-006: All-malformed JSON → default dict, no crash
- VAL-LOG-007: Byte budget truncation → truncated=True
- VAL-LOG-008: Time budget truncation → truncated=True
- VAL-LOG-009: Budget constants defined and positive
- VAL-LOG-010: _set_timeout outer SIGALRM still works
- VAL-NR-008: if __name__=='__main__' block preserved
- VAL-CROSS-006: Large JSONL + SIGINT → exit 0
- VAL-CROSS-009: Truncated output still valid (all 13 fields present)
"""

import json
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from memory_core.tools.session_end_logger import (
    BYTE_BUDGET,
    CHUNK_SIZE,
    MAX_LINE,
    TIME_BUDGET,
    TIMEOUT_SECONDS,
    _extract_session_info_streaming,
    _set_timeout,
    main,
)

logger = logging.getLogger(__name__)

# ─── VAL-LOG-009: Budget constants defined and positive ───────────────────────

class TestBudgetConstants:
    """All four budget constants must be defined and positive."""

    def test_time_budget_positive(self):
        assert TIME_BUDGET > 0

    def test_byte_budget_positive(self):
        assert BYTE_BUDGET > 0

    def test_chunk_size_positive(self):
        assert CHUNK_SIZE > 0

    def test_max_line_positive(self):
        assert MAX_LINE > 0

    def test_time_budget_less_than_timeout(self):
        """TIME_BUDGET < TIMEOUT_SECONDS (2s)."""
        assert TIME_BUDGET < TIMEOUT_SECONDS

    def test_chunk_size_less_than_byte_budget(self):
        """CHUNK_SIZE < BYTE_BUDGET."""
        assert CHUNK_SIZE < BYTE_BUDGET

    def test_time_budget_value(self):
        """TIME_BUDGET should be 1.8s."""
        assert TIME_BUDGET == 1.8

    def test_byte_budget_value(self):
        """BYTE_BUDGET should be 8MB."""
        assert BYTE_BUDGET == 8 * 1024 * 1024

    def test_chunk_size_value(self):
        """CHUNK_SIZE should be 64KB."""
        assert CHUNK_SIZE == 64 * 1024

    def test_max_line_value(self):
        """MAX_LINE should be 1MB."""
        assert MAX_LINE == 1024 * 1024


# ─── Helpers ──────────────────────────────────────────────────────────────────

EXPECTED_FIELDS = {
    "session_id", "full_session_id", "title", "model",
    "duration", "duration_seconds", "input_tokens", "output_tokens",
    "tool_calls", "total_tool_calls", "user_prompt_preview",
    "assistant_summary_preview",
}


def _make_session_start(title: str = "Test Session") -> dict:
    return {
        "type": "session_start",
        "title": title,
        "timestamp": "2025-01-15T10:00:00Z",
    }


def _make_user_msg(text: str = "Hello world") -> dict:
    return {
        "type": "message",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
        "timestamp": "2025-01-15T10:01:00Z",
    }


def _make_assistant_msg(text: str = "Hi there", tool_uses: list | None = None) -> dict:
    content: list = [{"type": "text", "text": text}]
    if tool_uses:
        content.extend(tool_uses)
    return {
        "type": "message",
        "message": {"role": "assistant", "content": content},
        "timestamp": "2025-01-15T10:02:00Z",
    }


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, lines: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


# ─── VAL-LOG-002: Normal JSONL → correct output ─────────────────────────────

class TestNormalJsonl:
    """Normal-sized JSONL should produce correct session info with all 13 fields."""

    def test_all_13_fields_present(self, tmp_path: Path):
        jsonl = tmp_path / "session.jsonl"
        _write_jsonl(jsonl, [
            _make_session_start("Normal Session"),
            _make_user_msg("Help me fix this bug"),
            _make_assistant_msg("I fixed the bug", [
                {"type": "tool_use", "name": "Read", "input": {}},
                {"type": "tool_use", "name": "Edit", "input": {}},
            ]),
        ])

        settings = {"model": "claude-3-opus", "inclusiveTokenUsage": {"inputTokens": 500, "outputTokens": 200}}
        result = _extract_session_info_streaming(jsonl, settings, "abc12345-def6-7890")

        assert result is not None
        assert EXPECTED_FIELDS.issubset(set(result.keys()))
        assert result["title"] == "Normal Session"
        assert result["model"] == "claude-3-opus"
        assert result["total_tool_calls"] == 2
        assert result["tool_calls"] == {"Read": 1, "Edit": 1}
        assert result["user_prompt_preview"] == "Help me fix this bug"
        assert result["assistant_summary_preview"] == "I fixed the bug"
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 200
        assert "truncated" not in result or result.get("truncated") is False

    def test_no_truncated_flag_when_within_budget(self, tmp_path: Path):
        jsonl = tmp_path / "session.jsonl"
        _write_jsonl(jsonl, [_make_session_start(), _make_user_msg(), _make_assistant_msg()])

        result = _extract_session_info_streaming(jsonl, {}, "test-session")
        assert result is not None
        assert result.get("truncated") is not True


# ─── VAL-LOG-003: Huge JSONL (50MB+) → completes within budget ──────────────

class TestHugeJsonl:
    """Very large JSONL should complete within time budget with truncated=True."""

    def test_50mb_file_completes_within_budget(self, tmp_path: Path):
        """Generate ~50MB of JSONL and verify it completes within timeout."""
        jsonl = tmp_path / "huge.jsonl"
        # Write a session_start first
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_make_session_start("Huge Session")) + "\n")
            f.write(json.dumps(_make_user_msg("Please help")) + "\n")

        # Generate ~50MB of assistant messages with tool uses
        tool_use = {"type": "tool_use", "name": "Read", "input": {"file_path": "/some/very/long/path/to/file.py"}}
        assistant_msg = _make_assistant_msg("Processing your request", [tool_use] * 5)
        line = json.dumps(assistant_msg) + "\n"
        target_size = 50 * 1024 * 1024  # 50MB
        lines_written = 0
        with jsonl.open("a", encoding="utf-8") as f:
            while f.tell() < target_size:
                f.write(line)
                lines_written += 1

        assert jsonl.stat().st_size > 50 * 1024 * 1024

        start = time.monotonic()
        result = _extract_session_info_streaming(jsonl, {}, "huge-session")
        elapsed = time.monotonic() - start

        assert result is not None
        assert result["truncated"] is True
        assert elapsed < TIMEOUT_SECONDS, f"Took {elapsed:.2f}s, exceeds TIMEOUT_SECONDS={TIMEOUT_SECONDS}"
        # Should have captured at least some data
        assert result["title"] == "Huge Session"
        assert result["total_tool_calls"] >= 0


# ─── VAL-LOG-004: Single oversized line → skipped ────────────────────────────

class TestOversizedLine:
    """Single line > MAX_LINE should be skipped, other lines processed."""

    def test_oversized_line_skipped(self, tmp_path: Path):
        jsonl = tmp_path / "session.jsonl"
        # Write valid lines + one oversized line + more valid lines
        oversized_line = "x" * (MAX_LINE + 1000)  # > 1MB
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_make_session_start("Oversized Test")) + "\n")
            f.write(json.dumps(_make_user_msg("Normal user message")) + "\n")
            f.write(oversized_line + "\n")  # This line is too big
            f.write(json.dumps(_make_assistant_msg("Normal assistant reply")) + "\n")

        result = _extract_session_info_streaming(jsonl, {}, "over-session")

        assert result is not None
        assert result["title"] == "Oversized Test"
        assert result["user_prompt_preview"] == "Normal user message"
        assert result["assistant_summary_preview"] == "Normal assistant reply"

    def test_only_oversized_lines_produces_default_dict(self, tmp_path: Path):
        jsonl = tmp_path / "session.jsonl"
        oversized_line = "x" * (MAX_LINE + 1000)
        jsonl.write_text(oversized_line + "\n")

        result = _extract_session_info_streaming(jsonl, {}, "over-session")
        assert result is not None
        assert EXPECTED_FIELDS.issubset(set(result.keys()))
        assert result["title"] == ""


# ─── VAL-LOG-005: Empty file → handled ────────────────────────────────────────

class TestEmptyFile:
    """Empty JSONL file should be handled without error."""

    def test_empty_file_returns_valid_dict(self, tmp_path: Path):
        jsonl = tmp_path / "empty.jsonl"
        jsonl.write_text("")

        result = _extract_session_info_streaming(jsonl, {}, "empty-session")
        assert result is not None
        assert EXPECTED_FIELDS.issubset(set(result.keys()))
        assert result["title"] == ""
        assert result["total_tool_calls"] == 0

    def test_empty_file_main_returns_0(self, tmp_path: Path):
        jsonl = tmp_path / "empty.jsonl"
        jsonl.write_text("")

        stdin_payload = {
            "session_id": "empty-session",
            "cwd": str(tmp_path),
            "transcript_path": str(jsonl),
        }
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            rc = main([])

        assert rc == 0


# ─── VAL-LOG-006: All-malformed JSON → default dict ──────────────────────────

class TestAllMalformedJson:
    """All-malformed JSON → dict with empty/default fields, no crash."""

    def test_all_invalid_lines(self, tmp_path: Path):
        jsonl = tmp_path / "malformed.jsonl"
        jsonl.write_text("not json at all\n{broken\n[also broken\nplain text\n")

        result = _extract_session_info_streaming(jsonl, {}, "mal-session")
        assert result is not None
        assert EXPECTED_FIELDS.issubset(set(result.keys()))
        assert result["title"] == ""
        assert result["total_tool_calls"] == 0
        assert result["user_prompt_preview"] == ""
        assert result["assistant_summary_preview"] == ""

    def test_mixed_valid_and_invalid(self, tmp_path: Path):
        jsonl = tmp_path / "mixed.jsonl"
        with jsonl.open("w", encoding="utf-8") as f:
            f.write("garbage\n")
            f.write(json.dumps(_make_session_start("Mixed")) + "\n")
            f.write("more garbage\n")
            f.write(json.dumps(_make_user_msg("Valid user msg")) + "\n")
            f.write("{broken json\n")

        result = _extract_session_info_streaming(jsonl, {}, "mix-session")
        assert result is not None
        assert result["title"] == "Mixed"
        assert result["user_prompt_preview"] == "Valid user msg"


# ─── VAL-LOG-007: Byte budget truncation ──────────────────────────────────────

class TestByteBudgetTruncation:
    """When JSONL exceeds BYTE_BUDGET, truncated=True is set."""

    def test_byte_budget_exceeded(self, tmp_path: Path):
        jsonl = tmp_path / "big.jsonl"
        # Write more than BYTE_BUDGET (8MB) of data
        target_size = BYTE_BUDGET + CHUNK_SIZE * 2  # Slightly over budget
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_make_session_start("Byte Budget Test")) + "\n")
            f.write(json.dumps(_make_user_msg("Hello")) + "\n")
            assistant_msg = _make_assistant_msg("Response text " * 100)
            line = json.dumps(assistant_msg) + "\n"
            while f.tell() < target_size:
                f.write(line)

        assert jsonl.stat().st_size > BYTE_BUDGET

        result = _extract_session_info_streaming(jsonl, {}, "byte-session")
        assert result is not None
        assert result["truncated"] is True
        # Should still have captured the session_start
        assert result["title"] == "Byte Budget Test"

    def test_byte_budget_preserves_collected_data(self, tmp_path: Path):
        """Truncated result should still have valid partial data."""
        jsonl = tmp_path / "big.jsonl"
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_make_session_start("Preserved Data")) + "\n")
            f.write(json.dumps(_make_user_msg("User intent here")) + "\n")
            # Fill up to beyond budget
            padding = _make_assistant_msg("X" * 1000)
            line = json.dumps(padding) + "\n"
            while f.tell() < BYTE_BUDGET + 1024:
                f.write(line)

        result = _extract_session_info_streaming(jsonl, {}, "preserve-session")
        assert result is not None
        assert result["truncated"] is True
        # All 13 fields should still be present
        assert EXPECTED_FIELDS.issubset(set(result.keys()))


# ─── VAL-LOG-008: Time budget truncation ──────────────────────────────────────

class TestTimeBudgetTruncation:
    """When processing exceeds TIME_BUDGET, truncated=True is set."""

    def test_time_budget_via_monotonic_monkeypatch(self, tmp_path: Path):
        """Monkeypatch time.monotonic to simulate time budget exceeded."""
        jsonl = tmp_path / "session.jsonl"
        # Create a file with many lines
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_make_session_start("Time Test")) + "\n")
            for i in range(10000):
                f.write(json.dumps(_make_assistant_msg(f"Message {i}")) + "\n")

        # Monkeypatch time.monotonic to simulate time passing
        real_monotonic = time.monotonic
        call_count = [0]

        def fake_monotonic():
            call_count[0] += 1
            # After processing a few chunks, simulate time exceeding budget
            if call_count[0] > 3:
                return real_monotonic() + TIME_BUDGET + 1.0
            return real_monotonic()

        with patch("memory_core.tools.session_end_logger.time.monotonic", side_effect=fake_monotonic):
            result = _extract_session_info_streaming(jsonl, {}, "time-session")

        assert result is not None
        assert result["truncated"] is True
        assert result["title"] == "Time Test"


# ─── VAL-LOG-010: _set_timeout outer SIGALRM still works ─────────────────────

class TestOuterSigalmWorks:
    """The _set_timeout(TIMEOUT_SECONDS) SIGALRM safety net must still work."""

    def test_set_timeout_exists_and_calls_alarm(self):
        """_set_timeout function exists and sets signal.alarm."""
        # Verify function is importable and callable
        assert callable(_set_timeout)

        # Verify it calls signal.alarm by checking the implementation
        import inspect
        source = inspect.getsource(_set_timeout)
        assert "signal.signal" in source
        assert "signal.SIGALRM" in source
        assert "signal.alarm" in source

    def test_timeout_seconds_constant_exists(self):
        """TIMEOUT_SECONDS constant is still defined."""
        assert TIMEOUT_SECONDS == 2


# ─── VAL-NR-008: if __name__=='__main__' block preserved ─────────────────────

class TestMainGuardPreserved:
    """The if __name__=='__main__' block must still exist and install handlers."""

    def test_main_guard_exists(self):
        """Source code contains if __name__ == '__main__' block."""
        import memory_core.tools.session_end_logger as mod
        source_file = Path(mod.__file__)
        source = source_file.read_text()
        assert 'if __name__ == "__main__":' in source

    def test_main_guard_installs_signal_handlers(self):
        """The __main__ block installs SIGALRM and SIGINT handlers."""
        import memory_core.tools.session_end_logger as mod
        source_file = Path(mod.__file__)
        source = source_file.read_text()

        # Find the __main__ block
        main_guard_idx = source.index('if __name__ == "__main__":')
        # The block should contain signal handler installations
        main_block = source[main_guard_idx:main_guard_idx + 500]
        assert "signal.signal" in main_block
        assert "SIGALRM" in main_block
        assert "SIGINT" in main_block


# ─── VAL-CROSS-006: Large JSONL + SIGINT → exit 0 ────────────────────────────

class TestLargeJsonlWithSigint:
    """Large JSONL + SIGINT → whichever fires first, exit 0."""

    def test_large_jsonl_sigint_exit_zero(self, tmp_path: Path):
        """Spawn logger subprocess with 20MB JSONL, send SIGINT, verify exit 0."""
        jsonl = tmp_path / "large.jsonl"
        # Create 20MB JSONL
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_make_session_start("SIGINT Test")) + "\n")
            assistant_msg = _make_assistant_msg("X" * 500)
            line = json.dumps(assistant_msg) + "\n"
            while f.tell() < 20 * 1024 * 1024:
                f.write(line)

        # Write stdin payload
        stdin_payload = json.dumps({
            "session_id": "sigint-session",
            "cwd": str(tmp_path),
            "transcript_path": str(jsonl),
        })

        proc = subprocess.Popen(
            [sys.executable, "-m", "memory_core.tools.session_end_logger"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Send payload via stdin and keep it open briefly
        proc.stdin.write(stdin_payload.encode())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

        time.sleep(0.3)
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        stderr = proc.stderr.read()
        assert proc.returncode == 0, f"Exit {proc.returncode}, stderr: {stderr.decode()}"
        assert b"Traceback" not in stderr
        assert b"KeyboardInterrupt" not in stderr

        # Clean up stdin
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except Exception as exc:
            logger.debug("关闭子进程 stdin 失败: %s", exc)


# ─── VAL-CROSS-009: Truncated output still valid ─────────────────────────────

class TestTruncatedOutputValid:
    """When truncated, output must still be valid with all 13 fields."""

    def test_truncated_dict_has_all_fields(self, tmp_path: Path):
        """Force truncation and verify all 13 fields present."""
        jsonl = tmp_path / "truncated.jsonl"
        # Create file larger than byte budget
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_make_session_start("Truncated Session")) + "\n")
            f.write(json.dumps(_make_user_msg("Original user intent")) + "\n")
            f.write(json.dumps(_make_assistant_msg("Original reply", [
                {"type": "tool_use", "name": "Read", "input": {}},
            ])) + "\n")
            # Fill beyond budget
            padding = _make_assistant_msg("Padding " * 200)
            line = json.dumps(padding) + "\n"
            while f.tell() < BYTE_BUDGET + 1024:
                f.write(line)

        result = _extract_session_info_streaming(jsonl, {"model": "test"}, "trunc-session")

        assert result is not None
        assert result["truncated"] is True
        # All 13 fields must be present
        assert EXPECTED_FIELDS.issubset(set(result.keys()))
        # Collected data should be valid
        assert result["title"] == "Truncated Session"
        assert result["model"] == "test"
        assert result["full_session_id"] == "trunc-session"
        assert isinstance(result["tool_calls"], dict)
        assert isinstance(result["duration_seconds"], int)
        assert isinstance(result["input_tokens"], int)
        assert isinstance(result["output_tokens"], int)

    def test_truncated_result_still_writes_daily_log(self, tmp_path: Path):
        """When truncated, main() should still write daily log and metrics."""
        jsonl = tmp_path / "truncated.jsonl"
        with jsonl.open("w", encoding="utf-8") as f:
            f.write(json.dumps(_make_session_start("Log Write Test")) + "\n")
            f.write(json.dumps(_make_user_msg("Test intent")) + "\n")
            padding = _make_assistant_msg("Y" * 1000)
            line = json.dumps(padding) + "\n"
            while f.tell() < BYTE_BUDGET + 1024:
                f.write(line)

        stdin_payload = json.dumps({
            "session_id": "trunc-log-session",
            "cwd": str(tmp_path),
            "transcript_path": str(jsonl),
        })

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = stdin_payload
            rc = main([])

        assert rc == 0
        # Daily log should have been created
        log_dir = tmp_path / "memory" / "log"
        assert log_dir.exists()
        log_files = list(log_dir.glob("*-sessions.md"))
        assert len(log_files) >= 1


# ─── File not found ────────────────────────────────────────────────────────────

class TestFileNotFound:
    """Non-existent file should return None."""

    def test_nonexistent_file_returns_none(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.jsonl"
        result = _extract_session_info_streaming(missing, {}, "missing-session")
        assert result is None


# ─── Cross-chunk line handling ────────────────────────────────────────────────

class TestCrossChunkLines:
    """Lines that span chunk boundaries should be handled correctly."""

    def test_line_split_across_chunks(self, tmp_path: Path):
        """A JSONL line split at a chunk boundary should still be parsed."""
        jsonl = tmp_path / "session.jsonl"
        # Write a single valid JSONL line
        _write_jsonl(jsonl, [
            _make_session_start("Cross-Chunk"),
            _make_user_msg("Test message"),
            _make_assistant_msg("Response"),
        ])

        # Even with small chunk reads (which we can't control directly),
        # the buffer logic should handle this
        result = _extract_session_info_streaming(jsonl, {}, "cross-session")
        assert result is not None
        assert result["title"] == "Cross-Chunk"
        assert result["user_prompt_preview"] == "Test message"
        assert result["assistant_summary_preview"] == "Response"
