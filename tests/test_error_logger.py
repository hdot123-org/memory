"""Dedicated unit tests for memory_core.tools.error_logger.

Covers the security-critical redaction helpers (_redact_api_keys,
_redact_context) and the write_error_log end-to-end behavior (validation,
truncation, redaction, JSONL output) that were previously only exercised
incidentally via mocks in other test modules.
"""

import json
import sys
from pathlib import Path

# Ensure repo root is importable when running from a bare checkout.
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools.error_logger import (
    MAX_MSG_LENGTH,
    VALID_ERROR_TYPES,
    _detect_calling_script,
    _redact_api_keys,
    _redact_context,
    write_error_log,
)

# Fake credential fixtures for redaction testing.
# Built from parts so the source contains no literal secret-like token;
# these are TEST DATA only and are never real credentials.
_PREFIX = "sk-"
_FAKE_KEY = _PREFIX + "abcd1234efgh"
_FAKE_KEY_A = _PREFIX + "aaaa1111bbbb"
_FAKE_KEY_B = _PREFIX + "bbbb2222cccc"
_FAKE_KEY_E = _PREFIX + "efgh5678ijkl"
_MIN_KEY = _PREFIX + "abcdefghij"   # 10 alphanumerics -- minimum that matches new pattern
_TOO_SHORT = _PREFIX + "abcdefghi"  # 9 alphanumerics -- below new threshold
_REDACTED = "[REDACTED]"            # expected output of the redaction transform


# ---------------------------------------------------------------------------
# API key redaction (security-critical)
# ---------------------------------------------------------------------------


class TestRedactApiKeys:
    """Verify sk- prefixed credential tokens are scrubbed from text."""

    def test_redacts_standard_api_key(self):
        assert _redact_api_keys("token=" + _FAKE_KEY) == "token=" + _REDACTED

    def test_redacts_key_at_start_of_string(self):
        assert _redact_api_keys(_FAKE_KEY + " failed") == _REDACTED + " failed"

    def test_redacts_multiple_keys(self):
        result = _redact_api_keys(_FAKE_KEY_A + " and " + _FAKE_KEY_B)
        assert result == _REDACTED + " and " + _REDACTED

    def test_does_not_redact_short_prefix(self):
        # Pattern requires 4+ alphanumerics after the prefix.
        assert _redact_api_keys(_TOO_SHORT) == _TOO_SHORT

    def test_minimum_length_boundary(self):
        # Exactly 4 alphanumerics after the prefix should be redacted.
        assert _redact_api_keys(_MIN_KEY) == _REDACTED

    def test_leaves_plain_text_untouched(self):
        assert _redact_api_keys("no credentials here") == "no credentials here"

    def test_empty_string(self):
        assert _redact_api_keys("") == ""


# ---------------------------------------------------------------------------
# Context redaction (recursive)
# ---------------------------------------------------------------------------


class TestRedactContext:
    """Verify recursive redaction of nested dict/list structures."""

    def test_redacts_top_level_string_value(self):
        result = _redact_context({"value": _FAKE_KEY})
        assert result == {"value": _REDACTED}

    def test_preserves_non_string_values(self):
        result = _redact_context({"count": 42, "flag": True, "none": None})
        assert result == {"count": 42, "flag": True, "none": None}

    def test_redacts_nested_dict(self):
        result = _redact_context({"outer": {"inner": _FAKE_KEY}})
        assert result == {"outer": {"inner": _REDACTED}}

    def test_redacts_string_items_in_list(self):
        result = _redact_context({"items": [_FAKE_KEY, "plain"]})
        assert result == {"items": [_REDACTED, "plain"]}

    def test_redacts_dicts_nested_in_list(self):
        result = _redact_context({"items": [{"value": _FAKE_KEY}]})
        assert result == {"items": [{"value": _REDACTED}]}

    def test_empty_context(self):
        assert _redact_context({}) == {}


# ---------------------------------------------------------------------------
# VALID_ERROR_TYPES
# ---------------------------------------------------------------------------


class TestValidErrorTypes:
    """Verify the canonical set of supported error types."""

    EXPECTED = frozenset({
        "transcript_missing",
        "hook_timeout",
        "json_parse_error",
        "directory_creation_failed",
        "file_write_failed",
        "llm_api_error",
        "llm_timeout",
        "settings_read_failed",
    })

    def test_all_expected_types_present(self):
        assert VALID_ERROR_TYPES == self.EXPECTED

    def test_max_msg_length_is_positive(self):
        assert MAX_MSG_LENGTH == 500


# ---------------------------------------------------------------------------
# write_error_log end-to-end
# ---------------------------------------------------------------------------


class TestWriteErrorLog:
    """End-to-end behavior of write_error_log against a temp project root."""

    def test_writes_valid_entry_and_returns_true(self, tmp_path: Path):
        result = write_error_log(
            project_root=str(tmp_path),
            error_type="transcript_missing",
            context={"session_id": "abc123"},
            error_msg="transcript file not found",
        )

        assert result is True

        log_dir = tmp_path / "memory" / "log"
        files = list(log_dir.glob("*-errors.jsonl"))
        assert len(files) == 1

        line = files[0].read_text(encoding="utf-8").strip()
        entry = json.loads(line)

        assert entry["type"] == "transcript_missing"
        assert entry["msg"] == "transcript file not found"
        assert entry["ctx"] == {"session_id": "abc123"}
        assert entry["project"] == str(tmp_path.resolve())
        assert "ts" in entry and entry["ts"]
        assert "script" in entry and entry["script"]

    def test_rejects_invalid_error_type(self, tmp_path: Path):
        result = write_error_log(
            project_root=str(tmp_path),
            error_type="not_a_real_type",
            context={},
            error_msg="boom",
        )

        assert result is False
        # No log file should be created.
        assert not (tmp_path / "memory" / "log").exists()

    def test_creates_log_directory_if_missing(self, tmp_path: Path):
        assert not (tmp_path / "memory" / "log").exists()

        result = write_error_log(
            project_root=str(tmp_path),
            error_type="file_write_failed",
            context={},
            error_msg="disk full",
        )

        assert result is True
        assert (tmp_path / "memory" / "log").is_dir()

    def test_redacts_api_key_in_message(self, tmp_path: Path):
        msg = "request failed with " + _FAKE_KEY
        result = write_error_log(
            project_root=str(tmp_path),
            error_type="llm_api_error",
            context={},
            error_msg=msg,
        )

        assert result is True
        entry = _read_single_entry(tmp_path)
        assert _FAKE_KEY not in entry["msg"]
        assert _REDACTED in entry["msg"]

    def test_redacts_api_key_in_context(self, tmp_path: Path):
        result = write_error_log(
            project_root=str(tmp_path),
            error_type="settings_read_failed",
            context={"value": _FAKE_KEY, "nested": {"data": _FAKE_KEY_E}},
            error_msg="could not read settings",
        )

        assert result is True
        entry = _read_single_entry(tmp_path)
        assert entry["ctx"]["value"] == _REDACTED
        assert entry["ctx"]["nested"]["data"] == _REDACTED

    def test_truncates_overlong_message(self, tmp_path: Path):
        long_msg = "x" * (MAX_MSG_LENGTH + 200)

        result = write_error_log(
            project_root=str(tmp_path),
            error_type="json_parse_error",
            context={},
            error_msg=long_msg,
        )

        assert result is True
        entry = _read_single_entry(tmp_path)
        assert len(entry["msg"]) == MAX_MSG_LENGTH

    def test_appends_to_existing_file(self, tmp_path: Path):
        write_error_log(
            project_root=str(tmp_path),
            error_type="hook_timeout",
            context={},
            error_msg="first",
        )
        write_error_log(
            project_root=str(tmp_path),
            error_type="hook_timeout",
            context={},
            error_msg="second",
        )

        files = list((tmp_path / "memory" / "log").glob("*-errors.jsonl"))
        assert len(files) == 1
        lines = [ln for ln in files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_returns_false_on_unresolvable_root(self):
        # A path containing a null byte cannot be resolved.
        result = write_error_log(
            project_root="/nonexistent\x00root",
            error_type="transcript_missing",
            context={},
            error_msg="bad path",
        )
        assert result is False


# ---------------------------------------------------------------------------
# _detect_calling_script graceful degradation (SILENT_SWALLOW regression)
# ---------------------------------------------------------------------------


class TestDetectCallingScript:
    """Verify stack-detection failures degrade gracefully and are logged."""

    def test_returns_unknown_when_stack_raises(self, monkeypatch):
        """inspect.stack() raising must still yield "unknown" (no swallow crash)."""
        def _boom(*args, **kwargs):
            raise RuntimeError("simulated stack failure")

        monkeypatch.setattr(
            "memory_core.tools.error_logger.inspect.stack", _boom
        )

        assert _detect_calling_script() == "unknown"

    def test_logs_debug_record_when_stack_raises(self, monkeypatch, caplog):
        """The previously-swallowed exception must now emit a debug log record."""
        def _boom(*args, **kwargs):
            raise RuntimeError("simulated stack failure")

        monkeypatch.setattr(
            "memory_core.tools.error_logger.inspect.stack", _boom
        )

        with caplog.at_level("DEBUG", logger="memory_core.tools.error_logger"):
            _detect_calling_script()

        debug_records = [
            r for r in caplog.records if r.levelname == "DEBUG"
            and "_detect_calling_script" in r.message
        ]
        assert debug_records, "expected a DEBUG log record for the swallowed exception"


# ---------------------------------------------------------------------------
# _try_sign_file graceful degradation (SILENT_SWALLOW regression)
# ---------------------------------------------------------------------------


class TestTrySignFile:
    """Verify incremental-signing failures degrade gracefully and are logged."""

    def test_swallows_exception_without_re_raise(self, monkeypatch, tmp_path):
        """sign_project_incremental raising must not propagate."""
        from memory_core.tools import error_logger

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated signing failure")

        monkeypatch.setattr(
            error_logger._integrity, "sign_project_incremental", _boom
        )

        # Should return None without raising.
        error_logger._try_sign_file(tmp_path, "memory/log/test-errors.jsonl")

    def test_logs_debug_record_when_signing_fails(self, monkeypatch, tmp_path, caplog):
        """The previously-swallowed exception must now emit a debug log record."""
        from memory_core.tools import error_logger

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated signing failure")

        monkeypatch.setattr(
            error_logger._integrity, "sign_project_incremental", _boom
        )

        with caplog.at_level("DEBUG", logger="memory_core.tools.error_logger"):
            error_logger._try_sign_file(tmp_path, "memory/log/test-errors.jsonl")

        debug_records = [
            r for r in caplog.records if r.levelname == "DEBUG"
            and "_try_sign_file" in r.message
        ]
        assert debug_records, "expected a DEBUG log record for the swallowed exception"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_single_entry(root: Path) -> dict:
    """Read and parse the single JSONL entry written under root."""
    files = list((root / "memory" / "log").glob("*-errors.jsonl"))
    assert len(files) == 1, f"expected exactly one log file, found {len(files)}"
    lines = [ln for ln in files[0].read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    return json.loads(lines[0])
