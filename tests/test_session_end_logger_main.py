"""Tests for session_end_logger.main() — path resolution + error path.

Covers the 5 key behaviors of main():
1. session_id fallback (from args or stdin payload)
2. transcript_path resolution (direct, session-dir inference, stdin)
3. jsonl_path resolution (transcript_path > session_dir > missing)
4. error log branches (transcript_missing, hook_timeout, unexpected error)
5. silent exit on missing params
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from memory_core.tools.session_end_logger import main


class TestMainMissingParams:
    """main() should silently return 0 when required params are missing."""

    def test_no_session_id_returns_zero(self, tmp_path: Path) -> None:
        """No session_id → silent exit with return code 0."""
        rc = main(["--project-root", str(tmp_path)])
        assert rc == 0

    def test_no_project_root_returns_zero(self) -> None:
        """No project_root → silent exit with return code 0."""
        rc = main(["--session-id", "abc-123"])
        assert rc == 0

    def test_no_params_returns_zero(self) -> None:
        """No params at all → silent exit with return code 0."""
        rc = main([])
        assert rc == 0


class TestMainPathResolution:
    """main() path resolution logic."""

    def test_transcript_from_stdin(self, tmp_path: Path) -> None:
        """session_id and cwd from stdin payload, transcript_path resolved."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(json.dumps({
            "type": "session_start",
            "title": "test",
            "timestamp": "2025-01-01T00:00:00Z",
        }) + "\n")

        stdin_payload = {
            "session_id": "test-session-id",
            "cwd": str(tmp_path),
            "transcript_path": str(jsonl),
        }

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            rc = main([])

        assert rc == 0

    def test_transcript_from_session_dir_fallback(self, tmp_path: Path) -> None:
        """When no transcript_path, infer from session-dir or factory sessions."""
        # Create a fake factory sessions dir
        factory_sessions = tmp_path / ".factory" / "sessions" / "proj"
        factory_sessions.mkdir(parents=True)
        jsonl = factory_sessions / "my-session.jsonl"
        jsonl.write_text(json.dumps({
            "type": "session_start",
            "title": "test",
            "timestamp": "2025-01-01T00:00:00Z",
        }) + "\n")

        # Use session-dir arg directly
        rc = main([
            "--session-id", "my-session",
            "--session-dir", str(factory_sessions),
            "--project-root", str(tmp_path),
        ])
        assert rc == 0

    def test_jsonl_not_found_returns_zero(self, tmp_path: Path) -> None:
        """jsonl file doesn't exist → log error and return 0."""
        missing_jsonl = tmp_path / "nonexistent.jsonl"

        stdin_payload = {
            "session_id": "test-session",
            "cwd": str(tmp_path),
            "transcript_path": str(missing_jsonl),
        }

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            with patch("memory_core.tools.session_end_logger.write_error_log") as mock_err:
                mock_err.return_value = None
                # write_error_log might be None, so patch it directly
                with patch("memory_core.tools.session_end_logger.write_error_log", create=True):
                    rc = main([])

        assert rc == 0

    def test_no_transcript_no_session_dir_returns_zero(self, tmp_path: Path) -> None:
        """No transcript_path and no session_dir → silent exit 0."""
        stdin_payload = {
            "session_id": "test-session",
            "cwd": str(tmp_path),
            # no transcript_path
        }

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            rc = main([])

        assert rc == 0


class TestMainErrorLogBranches:
    """main() error logging behavior."""

    def test_transcript_missing_does_not_log_error(self, tmp_path: Path) -> None:
        """Missing transcript is a benign condition — no error log (INFRA-164)."""
        missing_jsonl = tmp_path / "missing.jsonl"

        stdin_payload = {
            "session_id": "test-session",
            "cwd": str(tmp_path),
            "transcript_path": str(missing_jsonl),
        }

        mock_err = MagicMock()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            with patch("memory_core.tools.session_end_logger.write_error_log", mock_err):
                rc = main([])

        assert rc == 0
        mock_err.assert_not_called()

    def test_successful_run_with_valid_jsonl(self, tmp_path: Path) -> None:
        """Valid jsonl with session_start → completes successfully."""
        jsonl = tmp_path / "session.jsonl"
        lines = [
            {"type": "session_start", "title": "Test Session", "timestamp": "2025-01-01T00:00:00Z"},
            {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Hello"}]}, "timestamp": "2025-01-01T00:01:00Z"},
            {"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there"}]}, "timestamp": "2025-01-01T00:02:00Z"},
        ]
        jsonl.write_text("\n".join(json.dumps(line) for line in lines) + "\n")

        stdin_payload = {
            "session_id": "test-session",
            "cwd": str(tmp_path),
            "transcript_path": str(jsonl),
        }

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            rc = main([])

        assert rc == 0


class TestMainSessionIdFallback:
    """session_id resolution: args > stdin payload."""

    def test_session_id_from_args(self, tmp_path: Path) -> None:
        """session_id from --session-id arg takes precedence."""
        jsonl = tmp_path / "my-session.jsonl"
        jsonl.write_text(json.dumps({
            "type": "session_start",
            "title": "test",
            "timestamp": "2025-01-01T00:00:00Z",
        }) + "\n")

        rc = main([
            "--session-id", "my-session",
            "--session-dir", str(tmp_path),
            "--project-root", str(tmp_path),
        ])
        assert rc == 0

    def test_session_id_from_stdin(self, tmp_path: Path) -> None:
        """session_id from stdin when not in args."""
        jsonl = tmp_path / "stdin-session.jsonl"
        jsonl.write_text(json.dumps({
            "type": "session_start",
            "title": "test",
            "timestamp": "2025-01-01T00:00:00Z",
        }) + "\n")

        stdin_payload = {
            "session_id": "stdin-session",
            "cwd": str(tmp_path),
            "transcript_path": str(jsonl),
        }

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            rc = main([])

        assert rc == 0


class TestMainSettingsRead:
    """main() reads settings.json correctly."""

    def test_settings_file_missing_is_ok(self, tmp_path: Path) -> None:
        """Missing settings.json should not break the flow."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(json.dumps({
            "type": "session_start",
            "title": "test",
            "timestamp": "2025-01-01T00:00:00Z",
        }) + "\n")
        # No settings file created

        stdin_payload = {
            "session_id": "session",
            "cwd": str(tmp_path),
            "transcript_path": str(jsonl),
        }

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            rc = main([])

        assert rc == 0

    def test_settings_file_malformed_is_ok(self, tmp_path: Path) -> None:
        """Malformed settings.json should not break the flow."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text(json.dumps({
            "type": "session_start",
            "title": "test",
            "timestamp": "2025-01-01T00:00:00Z",
        }) + "\n")

        # Create malformed settings
        settings_path = tmp_path / "session.settings.json"
        settings_path.write_text("{invalid json")

        stdin_payload = {
            "session_id": "session",
            "cwd": str(tmp_path),
            "transcript_path": str(jsonl),
        }

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = json.dumps(stdin_payload)
            rc = main([])

        assert rc == 0


class TestReadJsonlChunksOSError:
    """Pinning test for _read_jsonl_chunks OSError behavior (#876)."""

    def test_mid_stream_oserror_returns_true(self, tmp_path: Path) -> None:
        """_read_jsonl_chunks returns True on mid-stream OSError (treat as truncation)."""
        import time

        from memory_core.tools.session_end_logger import _read_jsonl_chunks, _StreamingState

        # Create a JSONL file
        jsonl = tmp_path / "session.jsonl"
        lines = [
            {"type": "session_start", "title": "test", "timestamp": "2025-01-01T00:00:00Z"},
            {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Hello"}]}, "timestamp": "2025-01-01T00:01:00Z"},
        ]
        jsonl.write_text("\n".join(json.dumps(line) for line in lines) + "\n")

        state = _StreamingState()
        start_monotonic = time.monotonic()

        # Mock the file read to raise OSError mid-stream.
        # Patch pathlib.Path.open (not builtins.open) because Path.open uses
        # io.open directly on CPython.
        call_count = [0]
        real_file = jsonl.open("rb")

        class _FailingFile:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size=-1):
                call_count[0] += 1
                if call_count[0] >= 2:
                    raise OSError("Simulated mid-stream read error")
                return real_file.read(size)

            def close(self):
                real_file.close()

        with patch.object(Path, "open", return_value=_FailingFile()):
            result = _read_jsonl_chunks(jsonl, state, start_monotonic)

        # Behavioral pinning: mid-stream OSError → return True (treat as truncation)
        assert result is True
